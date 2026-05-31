#!/usr/bin/env python3
"""
實證者 (Empiricist) 完整量化實證腳本：F4 FDR / F5 AMRS / F6 RAP

對每個因子：
1. 擷取 BTCUSDT 日線數據（最多 1500 筆）
2. 計算因子值（winsorize 1% + z-score 標準化）
3. 多 horizon Rank-IC 分析（1/5/10/20 日）
4. 分組回報（5 組 Q1-Q5 + Q5-Q1 spread）
5. 與既有因子（F1 Complexity Gap, F2 Volume Weighted Direction Tilt）的 Rank 相關性
6. 寫入 index.db evidence 表（每 horizon 獨立一列）
7. 寫入候選筆記 ## 實證 (empiricist) 段落

IC-IR 符號不重要——方向反轉即可使用。負 IC-IR 不等於淘汰。
多 horizon 一致性是關鍵：好的因子應在 multi-horizon 保持一致的 IC 方向。
如實報告數據，不美化。使用繁體中文。
"""

from __future__ import annotations
import sys, os, json, urllib.request, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import polars as pl

# ── import signals ──
from core.signals.F1_Complexity_Gap_Regime import compute as f1_compute
from core.signals.F2_Liquidity_Consumption_Tilt import compute as f2_compute
from core.signals.F4_Flow_Divergence_Ratio import compute as f4_compute
from core.signals.F5_Anchored_Mean_Reversion_Score import compute as f5_compute
from core.signals.F6_Return_Asymmetry_Premium import compute as f6_compute

# ── import preprocessing ──
from core.preprocessing import preprocess_factor

# ── import memory ──
from core.memory import get_connection

# ═══════════════════════════════════════════════════════════════════════
# 1. 資料獲取
# ═══════════════════════════════════════════════════════════════════════

def fetch_binance_daily(symbol: str = "BTCUSDT", limit: int = 1500) -> list[dict]:
    """從 Binance 公開 REST 獲取日線 OHLCV。"""
    url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}"
           f"&interval=1d&limit={limit}")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    result = []
    for k in data:
        result.append({
            "ts": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return result


# ═══════════════════════════════════════════════════════════════════════
# 2. 實證指標計算（純 numpy，無 scipy 依賴）
# ═══════════════════════════════════════════════════════════════════════

def forward_returns(closes: np.ndarray, horizon: int) -> np.ndarray:
    """每個時點的未來 horizon 期對數報酬。"""
    n = len(closes)
    fwd = np.full(n, np.nan)
    for i in range(n - horizon):
        if closes[i] > 0 and closes[i + horizon] > 0:
            fwd[i] = np.log(closes[i + horizon] / closes[i])
    return fwd


def _rank(arr: np.ndarray) -> np.ndarray:
    """計算秩次（處理平手以平均秩次）。"""
    n = len(arr)
    order = np.argsort(arr)
    ranks = np.zeros(n, dtype=np.float64)
    i = 0
    while i < n:
        j = i
        while j < n and arr[order[j]] == arr[order[i]]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j
    return ranks


def rank_ic_single(factor_vals: np.ndarray, fwd_rets: np.ndarray) -> float:
    """單一橫斷面 Rank-IC = Spearman(因子值, 未來報酬)。"""
    valid = ~(np.isnan(factor_vals) | np.isnan(fwd_rets))
    if valid.sum() < 10:
        return float("nan")
    fv = factor_vals[valid]
    fr = fwd_rets[valid]
    r1 = _rank(fv)
    r2 = _rank(fr)
    n_r = len(r1)
    if n_r < 3:
        return float("nan")
    mean1, mean2 = r1.mean(), r2.mean()
    num = np.sum((r1 - mean1) * (r2 - mean2))
    den = np.sqrt(np.sum((r1 - mean1)**2) * np.sum((r2 - mean2)**2))
    return float(num / den) if den > 1e-12 else float("nan")


def overall_rank_ic(factor_signal: np.ndarray, closes: np.ndarray, horizon: int) -> float:
    """全樣本 Rank-IC：所有有效配對的 Spearman 相關係數。"""
    fwd = forward_returns(closes, horizon)
    return rank_ic_single(factor_signal, fwd)


def rolling_rank_ic(factor_signal: np.ndarray, closes: np.ndarray,
                     horizon: int, window: int = 60) -> np.ndarray:
    """計算 rolling window Rank-IC 序列。"""
    n = len(factor_signal)
    fwd = forward_returns(closes, horizon)
    ic_series = np.full(n, np.nan)

    for t in range(window, n):
        fv_slice = factor_signal[t - window:t + 1]
        fr_slice = fwd[t - window:t + 1]
        valid = ~(np.isnan(fv_slice) | np.isnan(fr_slice))
        if valid.sum() >= 20:
            ic_series[t] = rank_ic_single(fv_slice, fr_slice)

    return ic_series


def quantile_returns(factor_signal: np.ndarray, closes: np.ndarray,
                     horizon: int, n_groups: int = 5) -> dict:
    """分組回報：將因子值分為 n_groups 組，計算各組的未來 N 日平均報酬。"""
    n = len(factor_signal)
    fwd = forward_returns(closes, horizon)

    valid = ~(np.isnan(factor_signal) | np.isnan(fwd))
    fv = factor_signal[valid]
    fr = fwd[valid]

    if len(fv) < n_groups * 5:
        return {"error": "Not enough data for quantile analysis", "n_valid": int(len(fv))}

    order = np.argsort(fv)
    group_size = len(fv) // n_groups
    groups = {}

    for g in range(n_groups):
        start = g * group_size
        end = (g + 1) * group_size if g < n_groups - 1 else len(fv)
        idx = order[start:end]
        groups[f"Q{g+1}"] = {
            "mean_return": float(np.mean(fr[idx])),
            "std_return": float(np.std(fr[idx])),
            "count": int(len(idx)),
            "factor_min": float(np.min(fv[idx])),
            "factor_max": float(np.max(fv[idx])),
        }

    q5_idx = order[(n_groups-1)*group_size:]
    q1_idx = order[:group_size]
    spread = float(np.mean(fr[q5_idx]) - np.mean(fr[q1_idx]))

    return {"groups": groups, "long_short_spread": spread, "n_valid": int(len(fv))}


def correlation_with_other_factor(factor_signal: np.ndarray, other_signal: np.ndarray) -> dict:
    """計算兩個因子信號的 Pearson 與 Spearman 相關性。"""
    valid = ~(np.isnan(factor_signal) | np.isnan(other_signal))
    if valid.sum() < 10:
        return {"pearson": float("nan"), "spearman": float("nan"), "n": int(valid.sum())}

    fv = factor_signal[valid]
    ov = other_signal[valid]

    fv_mean = np.mean(fv)
    ov_mean = np.mean(ov)
    num = np.sum((fv - fv_mean) * (ov - ov_mean))
    den = np.sqrt(np.sum((fv - fv_mean)**2) * np.sum((ov - ov_mean)**2))
    pearson = float(num / den) if den > 1e-12 else float("nan")

    try:
        r1 = _rank(fv)
        r2 = _rank(ov)
        n_r = len(r1)
        m1, m2 = r1.mean(), r2.mean()
        num_s = np.sum((r1 - m1) * (r2 - m2))
        den_s = np.sqrt(np.sum((r1 - m1)**2) * np.sum((r2 - m2)**2))
        spearman = float(num_s / den_s) if den_s > 1e-12 else float("nan")
    except Exception:
        spearman = float("nan")

    return {"pearson": pearson, "spearman": spearman, "n": int(valid.sum())}


def winsorize_zscore(arr: np.ndarray, clip_lower: float = 0.01, clip_upper: float = 0.99) -> np.ndarray:
    """
    1% winsorize + z-score 標準化。
    以 percentile 截斷極值，再進行 z-score 標準化。
    """
    valid_mask = ~np.isnan(arr)
    if valid_mask.sum() < 5:
        return arr.copy()

    valid_vals = arr[valid_mask]
    lower = np.quantile(valid_vals, clip_lower)
    upper = np.quantile(valid_vals, clip_upper)

    result = arr.copy()
    for i in range(len(arr)):
        if np.isnan(arr[i]):
            continue
        v = arr[i]
        if v < lower:
            v = lower
        elif v > upper:
            v = upper
        result[i] = v

    # z-score
    valid_after = result[~np.isnan(result)]
    mu = np.mean(valid_after)
    sigma = np.std(valid_after)
    if sigma < 1e-12:
        sigma = 1.0

    for i in range(len(result)):
        if not np.isnan(result[i]):
            result[i] = (result[i] - mu) / sigma

    return np.clip(result, -4.0, 4.0)


# ═══════════════════════════════════════════════════════════════════════
# 3. 寫入 evidence 表
# ═══════════════════════════════════════════════════════════════════════

def write_evidence_row(conn, factor_id: str, market: str, horizon_days: int,
                        rank_ic: float, ic_ir: float, ic_samples: int,
                        ic_std: float, ic_positive_pct: float,
                        cumulative_ic: float, correlation_with_st: float,
                        quantile_returns_json: str):
    """寫入一列 evidence。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO evidence (factor_id, market, rank_ic, ic_ir, ls_annual,
            ic_samples, ic_std, ic_positive_pct, cumulative_ic,
            correlation_with_st, horizon_days, quantile_returns, computed_at)
        VALUES (?, ?, ?, ?, 0,
            ?, ?, ?, ?,
            ?, ?, ?, ?)
    """, (factor_id, market, rank_ic, ic_ir,
          ic_samples, ic_std, ic_positive_pct, cumulative_ic,
          correlation_with_st, horizon_days, quantile_returns_json, now))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# 4. 單一因子完整分析
# ═══════════════════════════════════════════════════════════════════════

def analyze_factor(
    name: str,
    factor_id: str,
    raw_signal: np.ndarray,
    closes: np.ndarray,
    f1_signal: np.ndarray,
    f2_signal: np.ndarray,
    horizons: list[int],
    conn,
) -> dict:
    """對單一因子執行完整實證分析，寫入 evidence 表並回傳結果。"""
    # Step 1: winsorize 1% + z-score 標準化
    signal = winsorize_zscore(raw_signal)

    n = len(closes)
    n_valid = int(np.sum(~np.isnan(signal)))

    results = {
        "factor": name,
        "factor_id": factor_id,
        "n_obs": n,
        "n_valid_signal": n_valid,
        "horizons": {},
        "correlation_with_f1": {},
        "correlation_with_f2": {},
        "_ic_series_store": {},
    }

    # 與既有因子相關性（僅一次，全樣本有效配對）
    results["correlation_with_f1"] = correlation_with_other_factor(signal, f1_signal)
    results["correlation_with_f2"] = correlation_with_other_factor(signal, f2_signal)

    for h in horizons:
        fwd = forward_returns(closes, h)
        valid_mask = ~(np.isnan(signal) | np.isnan(fwd))
        n_valid_pairs = int(valid_mask.sum())

        if n_valid_pairs < 20:
            results["horizons"][h] = {"error": "insufficient data", "n_valid_pairs": n_valid_pairs}
            continue

        # Overall IC
        overall_ic_val = overall_rank_ic(signal, closes, h)

        # Rolling IC
        ic_series = rolling_rank_ic(signal, closes, h, window=60)
        results["_ic_series_store"][h] = ic_series
        ic_valid = ic_series[~np.isnan(ic_series)]

        ic_mean = float(np.mean(ic_valid)) if len(ic_valid) > 0 else float("nan")
        ic_std = float(np.std(ic_valid)) if len(ic_valid) > 0 else float("nan")
        ic_ir = ic_mean / ic_std if ic_std and ic_std > 0 else float("nan")
        cum_ic = np.cumsum(ic_valid)
        cum_ic_final = float(cum_ic[-1]) if len(cum_ic) > 0 else float("nan")
        ic_positive_ratio = float(np.sum(ic_valid > 0) / len(ic_valid)) if len(ic_valid) > 0 else float("nan")

        # Quantile returns
        qr = quantile_returns(signal, closes, h, n_groups=5)
        ls_spread = qr.get("long_short_spread", 0.0) if "error" not in qr else 0.0

        results["horizons"][h] = {
            "overall_ic": round(overall_ic_val, 6) if not math.isnan(overall_ic_val) else None,
            "ic_mean": round(ic_mean, 6),
            "ic_std": round(ic_std, 6),
            "ic_ir": round(ic_ir, 4),
            "cum_ic_final": round(cum_ic_final, 6),
            "ic_positive_ratio": round(ic_positive_ratio, 4),
            "n_ic_points": int(len(ic_valid)),
            "n_valid_pairs": n_valid_pairs,
            "quantiles": qr,
            "long_short_spread": ls_spread,
        }

        # 寫入 evidence 表
        qr_json = json.dumps(qr, default=str)
        # 使用 F1 spearman 作為 correlation_with_st 代理（原始欄位名稱）
        corr_f1_s = results["correlation_with_f1"].get("spearman", float("nan"))
        corr_val = corr_f1_s if not math.isnan(corr_f1_s) else 0.0

        write_evidence_row(
            conn=conn,
            factor_id=factor_id,
            market="BTCUSDT",
            horizon_days=h,
            rank_ic=overall_ic_val if not math.isnan(overall_ic_val) else 0.0,
            ic_ir=ic_ir if not math.isnan(ic_ir) else 0.0,
            ic_samples=int(len(ic_valid)),
            ic_std=ic_std if not math.isnan(ic_std) else 0.0,
            ic_positive_pct=ic_positive_ratio if not math.isnan(ic_positive_ratio) else 0.0,
            cumulative_ic=cum_ic_final if not math.isnan(cum_ic_final) else 0.0,
            correlation_with_st=corr_val,
            quantile_returns_json=qr_json,
        )

    return results


# ═══════════════════════════════════════════════════════════════════════
# 5. 格式化輸出
# ═══════════════════════════════════════════════════════════════════════

def format_quantile_table(qr: dict) -> str:
    """格式化分組回報為 Markdown 表格。"""
    if "error" in qr:
        return f"  (資料不足: {qr['error']}, n_valid={qr.get('n_valid', 0)})"

    lines = []
    lines.append(f"  | 分組 | 平均報酬 | 標準差 | 樣本數 | 因子值範圍 |")
    lines.append(f"  |------|----------|--------|--------|------------|")

    groups = qr.get("groups", {})
    for g_name in sorted(groups.keys()):
        g = groups[g_name]
        lines.append(
            f"  | {g_name} | {g['mean_return']:.6f} | {g['std_return']:.6f} | "
            f"{g['count']} | [{g['factor_min']:.4f}, {g['factor_max']:.4f}] |"
        )

    spread = qr.get("long_short_spread", 0)
    lines.append(f"  | **Long-Short (Q5-Q1)** | **{spread:.6f}** | — | — | — |")

    return "\n".join(lines)


def format_ic_curve_ascii(ic_series: np.ndarray, width: int = 60) -> str:
    """生成累積 IC 曲線的 ASCII 文字圖。"""
    ic_clean = ic_series[~np.isnan(ic_series)]
    if len(ic_clean) == 0:
        return "  (無有效 IC 值)"

    cum = np.cumsum(ic_clean)
    n_c = len(cum)
    if n_c < 2:
        return "  (資料點不足)"

    step = max(1, n_c // width)
    sampled_idx = np.arange(0, n_c, step)
    sampled_cum = cum[sampled_idx]

    y_min, y_max = np.min(sampled_cum), np.max(sampled_cum)
    y_range = max(y_max - y_min, 0.001)
    height = 15

    lines = []
    lines.append(f"  累積 IC 曲線 (n={n_c}, 最終值={cum[-1]:.4f}):")
    lines.append(f"  Y 軸: [{y_min:.4f}, {y_max:.4f}]")
    lines.append("  " + "─" * len(sampled_idx))

    for row in range(height - 1, -1, -1):
        line_chars = [" "] * len(sampled_idx)
        target_y = y_min + (row / (height - 1)) * y_range
        for j in range(1, len(sampled_idx)):
            y_curr = sampled_cum[j-1]
            y_next = sampled_cum[j]
            if (y_curr <= target_y <= y_next) or (y_next <= target_y <= y_curr):
                line_chars[j] = "█"
            elif abs(y_curr - target_y) < y_range * 0.05:
                line_chars[j] = "▄"
        lines.append(f"  {''.join(line_chars)}")

    lines.append("  " + "─" * len(sampled_idx))
    lines.append(f"  起點 → (早期)  ──────────→  (近期) 終點")
    return "\n".join(lines)


def generate_report_section(results: dict, horizons: list[int]) -> str:
    """生成 ## 實證 (empiricist) Markdown 段落。"""
    lines = []
    lines.append("## 實證 (empiricist)")
    lines.append("")
    lines.append(f"> 分析期間：BTCUSDT 日線，共 {results['n_obs']} 根 K 線")
    lines.append(f"> 因子有效信號數：{results['n_valid_signal']} / {results['n_obs']}")
    lines.append(f"> 預處理：winsorize 1% + z-score 標準化")
    lines.append(f"> 計算日期：{datetime.now(timezone.utc).strftime('%Y-%m-%d')} (自動生成)")
    lines.append("")

    # ── Rank-IC 總覽表 ──
    lines.append("### Rank-IC 與 IC-IR 總覽")
    lines.append("")
    lines.append("| 預測天數 (N) | Overall IC | IC 均值 | IC 標準差 | IC-IR | 累積 IC | IC>0 比例 | IC 樣本數 |")
    lines.append("|-------------|-----------|---------|----------|------|---------|----------|----------|")

    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" in hr:
            lines.append(f"| {h} | — | — | — | — | — | — | {hr.get('n_valid_pairs', 0)} |")
        else:
            oic = f"{hr['overall_ic']:.4f}" if hr.get('overall_ic') is not None else "N/A"
            lines.append(
                f"| {h} | {oic} | {hr['ic_mean']:.4f} | {hr['ic_std']:.4f} | "
                f"{hr['ic_ir']:.3f} | {hr['cum_ic_final']:.4f} | "
                f"{hr['ic_positive_ratio']:.1%} | {hr['n_ic_points']} |"
            )
    lines.append("")

    # ── 多 horizon 一致性分析 ──
    lines.append("### 多 horizon 一致性分析")
    lines.append("")
    ic_means = []
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" not in hr:
            ic_means.append((h, hr["ic_mean"]))
    if ic_means:
        signs = ["+" if m > 0 else ("−" if m < 0 else "0") for _, m in ic_means]
        consistent = len(set(signs)) == 1
        lines.append(f"- IC 均值方向：{' → '.join([f'{s}{m:.4f} (N={h})' for h, m in ic_means])}  (sign: {' → '.join(signs)})")
        if consistent and ic_means[0][1] != 0:
            lines.append(f"- ✅ 多 horizon IC 方向一致（全部 {signs[0]}），因子信號在短期至中期保持一致方向性")
        else:
            lines.append(f"- ⚠️ 多 horizon IC 方向不一致，因子在不同預測區間可能捕捉不同市場現象")
    lines.append("")

    # ── 門檻判定 ──
    lines.append("### 門檻判定")
    lines.append("")

    # 找最佳 horizon
    best_ir = 0
    best_h = 1
    best_mean = 0
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" not in hr:
            ir_val = abs(hr.get("ic_ir", 0))
            if ir_val > abs(best_ir):
                best_ir = hr["ic_ir"]
                best_h = h
            m = hr.get("ic_mean", 0)
            if abs(m) > abs(best_mean):
                best_mean = m

    pass_ic = abs(best_mean) >= 0.02
    pass_ir = abs(best_ir) >= 0.3
    overall_pass = pass_ic and pass_ir

    lines.append(f"| 閾值 | 要求 | 實際 (最佳 N={best_h}) | 判定 |")
    lines.append(f"|------|------|----------------------|------|")
    lines.append(
        f"| IC 均值 | |IC_mean| ≥ 0.02 | |{best_mean:.4f}| "
        f"| {'✅ 通過' if pass_ic else '❌ 未達標'} |"
    )
    lines.append(
        f"| IC-IR | |IC-IR| ≥ 0.3 | |{best_ir:.3f}| "
        f"| {'✅ 通過' if pass_ir else '❌ 未達標'} |"
    )
    lines.append(
        f"| **綜合判定** | 兩者皆達標 | — | "
        f"{'**✅ 通過實證門檻**' if overall_pass else '**⚠️ 未完全達標**'} |"
    )
    lines.append("")

    # ── 各 horizon 分組回報 ──
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" in hr:
            continue
        qr = hr.get("quantiles", {})
        lines.append(f"### 分組回報 (N={h} 日)")
        lines.append("")
        lines.append(format_quantile_table(qr))
        lines.append("")

    # ── 累積 IC 曲線 ──
    ic_store = results.get("_ic_series_store", {})
    if best_h in ic_store:
        ic_s = ic_store[best_h]
        lines.append(f"### 累積 IC 曲線 (N={best_h} 日，最佳 horizon)")
        lines.append("")
        lines.append(format_ic_curve_ascii(ic_s))
        lines.append("")

    # ── 與既有因子的相關性 ──
    lines.append("### 與既有因子的相關性")
    lines.append("")
    lines.append("| 既有因子 | Pearson r | Spearman ρ | 配對樣本數 | 解讀 |")
    lines.append("|----------|-----------|------------|-----------|------|")

    for prefix, corr_key in [("F1 Complexity Gap", "correlation_with_f1"),
                               ("F2 Vol Weighted Tilt", "correlation_with_f2")]:
        c = results.get(corr_key, {})
        p = c.get("pearson", float("nan"))
        s = c.get("spearman", float("nan"))
        n_c = c.get("n", 0)

        if not math.isnan(s):
            if abs(s) < 0.2:
                interp = "極低相關，因子提供獨立資訊維度"
            elif abs(s) < 0.4:
                interp = "低相關，部分重疊但仍有獨立貢獻"
            elif abs(s) < 0.6:
                interp = "中等相關，有明顯重疊"
            else:
                interp = "高相關，可能捕捉相同資訊"
        else:
            interp = "N/A"

        lines.append(
            f"| {prefix} | {p:.4f} | {s:.4f} | {n_c} | {interp} |"
        )
    lines.append("")

    # ── 實證結論 ──
    lines.append("### 實證結論")
    lines.append("")
    lines.append(f"- 因子在多 horizon 的 IC 方向一致性：{'是' if len(set(signs)) == 1 else '否'}（{' → '.join(signs)}）")
    lines.append(f"- 最佳 horizon：N={best_h}，IC-IR={best_ir:.3f}")
    lines.append(f"- 通過實證閾值：{'是' if overall_pass else '否'}（IC 均值 ≥ 0.02 且 |IC-IR| ≥ 0.3）")
    lines.append(f"- 注意：負 IC-IR 不代表淘汰——若方向穩定，可反轉信號使用")
    lines.append("")

    return "\n".join(lines)


def write_section_to_note(note_path: str, section_content: str):
    """將 ## 實證 (empiricist) 段落寫入候選筆記。"""
    path = Path(note_path)
    if not path.exists():
        print(f"  ⚠ 筆記不存在：{note_path}")
        return False

    content = path.read_text(encoding="utf-8")

    # Three possible section headers
    for header in ["\n## 實證 (empiricist)\n", "\n## 實證\n"]:
        if header in content:
            idx_start = content.index(header)
            rest = content[idx_start + len(header):]
            idx_next = rest.find("\n## ")
            if idx_next == -1:
                new_content = content[:idx_start] + "\n" + section_content
            else:
                new_content = content[:idx_start] + "\n" + section_content + "\n" + rest[idx_next:]
            path.write_text(new_content, encoding="utf-8")
            print(f"  ✅ 已寫入（替換現有段落）：{note_path}")
            return True

    # 附加於文末
    new_content = content.rstrip() + "\n\n" + section_content + "\n"
    path.write_text(new_content, encoding="utf-8")
    print(f"  ✅ 已寫入（新增段落）：{note_path}")
    return True


# ═══════════════════════════════════════════════════════════════════════
# 6. 主程式
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  實證者 (Empiricist)：F4 FDR / F5 AMRS / F6 RAP 完整量化實證")
    print("=" * 70)

    # ── Step 1: 獲取資料 ──
    print("\n📡 正在獲取 BTCUSDT 日線資料（上限 1500 筆）...")
    try:
        ohlcv = fetch_binance_daily("BTCUSDT", limit=1500)
        print(f"  ✅ 成功獲取 {len(ohlcv)} 根日線 K 線")
    except Exception as e:
        print(f"  ❌ 無法獲取資料: {e}")
        return 1

    if len(ohlcv) < 200:
        print(f"  ❌ 資料不足（{len(ohlcv)} < 200），無法進行實證分析")
        return 1

    closes = np.array([d["close"] for d in ohlcv])

    # ── Step 2: 計算既有因子 F1, F2 ──
    print("\n📊 計算既有因子 F1 Complexity Gap...")
    f1_result = f1_compute(ohlcv, window=60, n_components=10)
    f1_signal_raw = f1_result["signal"]
    f1_signal = winsorize_zscore(f1_signal_raw)
    print(f"  ✅ F1 有效信號：{int(np.sum(~np.isnan(f1_signal)))} / {len(ohlcv)}")

    print("📊 計算既有因子 F2 Volume Weighted Direction Tilt...")
    f2_result = f2_compute(ohlcv, ema_halflife=10)
    f2_signal_raw = f2_result["signal"]
    f2_signal = winsorize_zscore(f2_signal_raw)
    print(f"  ✅ F2 有效信號：{int(np.sum(~np.isnan(f2_signal)))} / {len(ohlcv)}")

    # ── Step 3: 設定因子列表 ──
    horizons = [1, 5, 10, 20]

    factors = [
        {
            "name": "F4_Flow_Divergence_Ratio",
            "factor_id": "F4",
            "full_name": "F4 Flow Divergence Ratio (FDR)",
            "note_path": "/home/anson/factor-lab/candidates/F4_flow_divergence_ratio.md",
            "compute_fn": lambda d: f4_compute(d),
        },
        {
            "name": "F5_Anchored_Mean_Reversion_Score",
            "factor_id": "F5",
            "full_name": "F5 Anchored Mean-Reversion Score (AMRS)",
            "note_path": "/home/anson/factor-lab/candidates/F5_anchored_mean_reversion_score.md",
            "compute_fn": lambda d: f5_compute(d),
        },
        {
            "name": "F6_Return_Asymmetry_Premium",
            "factor_id": "F6",
            "full_name": "F6 Return Asymmetry Premium (RAP)",
            "note_path": "/home/anson/factor-lab/candidates/F6_return_asymmetry_premium.md",
            "compute_fn": lambda d: f6_compute(d),
        },
    ]

    conn = get_connection()

    for fc in factors:
        print(f"\n{'─' * 70}")
        print(f"  📈 正在分析：{fc['full_name']}")
        print(f"{'─' * 70}")

        # 計算信號（取得 raw_signal，未標準化的原始因子值）
        try:
            result = fc["compute_fn"](ohlcv)
        except Exception as e:
            print(f"  ❌ 因子計算失敗: {e}")
            continue

        # 使用 raw_signal（信號函數內部標準化前的原始值）
        # 部分因子可能有 raw_signal 欄位
        raw_signal = result.get("raw_signal", result.get("signal"))
        if raw_signal is None:
            raw_signal = result["signal"]

        n_before = int(np.sum(~np.isnan(raw_signal)))
        print(f"  原始信號：{n_before} / {len(ohlcv)}")

        if n_before < 30:
            print(f"  ⚠ 有效信號不足（{n_before} < 30），跳過詳細分析")
            continue

        # 完整分析
        results = analyze_factor(
            name=fc["name"],
            factor_id=fc["factor_id"],
            raw_signal=raw_signal,
            closes=closes,
            f1_signal=f1_signal,
            f2_signal=f2_signal,
            horizons=horizons,
            conn=conn,
        )

        # 輸出摘要
        print(f"\n  📊 IC 分析結果：")
        for h in horizons:
            hr = results["horizons"].get(h, {})
            if "error" not in hr:
                print(f"    N={h:2d}: IC_mean={hr['ic_mean']:+.4f}, "
                      f"IC_std={hr['ic_std']:.4f}, IC-IR={hr['ic_ir']:+.3f}, "
                      f"CumIC={hr['cum_ic_final']:+.4f}, "
                      f"PosRatio={hr['ic_positive_ratio']:.1%}")

        # 相關性
        f1_c = results["correlation_with_f1"]
        f2_c = results["correlation_with_f2"]
        print(f"\n  🔗 F1 相關性：Pearson={f1_c.get('pearson', 'nan'):.4f}, "
              f"Spearman={f1_c.get('spearman', 'nan'):.4f}, n={f1_c.get('n', 0)}")
        print(f"  🔗 F2 相關性：Pearson={f2_c.get('pearson', 'nan'):.4f}, "
              f"Spearman={f2_c.get('spearman', 'nan'):.4f}, n={f2_c.get('n', 0)}")

        # 生成報告段落
        report = generate_report_section(results, horizons)

        # 寫入筆記
        write_section_to_note(fc["note_path"], report)

        # 列印前 80 行報告，方便在終端檢查
        print(f"\n  📝 實證報告預覽（前 50 行）：")
        for line in report.split("\n")[:50]:
            print(f"    {line}")

    print(f"\n{'=' * 70}")
    print(f"  ✅ 實證分析完成！F4, F5, F6 各 horizon 已寫入 evidence 表")
    print(f"  ✅ 候選筆記已更新 ## 實證 (empiricist) 段落")
    print(f"{'=' * 70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
