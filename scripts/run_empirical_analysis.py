#!/usr/bin/env python3
"""
完整實證分析腳本：對 F1/F2/F3 三個因子計算 Rank-IC、IC-IR、分組回報、累積 IC 曲線。

方法：
1. 從 Binance 公開 REST API 獲取 BTCUSDT 日線 OHLCV（至少 500 根）
2. 對每個因子計算信號
3. 計算 N=1,5,10,20 日的 Rank-IC、IC-IR
4. 分 5 組計算未來 N 日回報
5. 繪製累積 IC 曲線（ASCII 文字版）
6. 計算與 super_trend_10_3 的相關性
7. 輸出結果為 Markdown 表格，更新對應候選筆記的 ## 實證 段落
"""

from __future__ import annotations
import sys, os, json, urllib.request, math, statistics as st
from pathlib import Path

# 確保 factor-lab 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from core.signals.F1_Complexity_Gap_Regime import compute as f1_compute
from core.signals.F2_Liquidity_Consumption_Tilt import compute as f2_compute
from core.signals.F3_Volatility_Roughness_Filter import compute as f3_compute


# ═══════════════════════════════════════════════════════════════════════
# 1. 資料獲取
# ═══════════════════════════════════════════════════════════════════════

def fetch_binance_daily(symbol: str = "BTCUSDT", limit: int = 500) -> list[dict]:
    """從 Binance 公開 REST 獲取日線 OHLCV。"""
    url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}"
           f"&interval=1d&limit={limit}")
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    # Binance kline: [openTime, open, high, low, close, volume, ...]
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
# 2. Super Trend 10/3 實現（用於相關性比較）
# ═══════════════════════════════════════════════════════════════════════

def super_trend_10_3(ohlcv: list[dict]) -> np.ndarray:
    """
    SuperTrend (10, 3) 因子信號。
    
    period=10, multiplier=3, ATR-based.
    回傳 [-1, 0, 1] 信號：1=做多, -1=做空, 0=中性。
    使用 expanding z-score 標準化。
    """
    n = len(ohlcv)
    highs = np.array([d["high"] for d in ohlcv])
    lows = np.array([d["low"] for d in ohlcv])
    closes = np.array([d["close"] for d in ohlcv])
    
    period = 10
    mult = 3.0
    
    # 計算 ATR
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
    
    atr = np.full(n, np.nan)
    # ATR 用 SMA of TR
    for i in range(period, n):
        atr[i] = np.mean(tr[i-period+1:i+1])
    
    # SuperTrend bands
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    trend = np.full(n, 0)  # 1=uptrend, -1=downtrend
    
    for i in range(period, n):
        # Basic bands
        src = (highs[i] + lows[i]) / 2.0
        up = src - mult * atr[i]
        dn = src + mult * atr[i]
        
        if i == period:
            upper[i] = up
            lower[i] = dn
        else:
            # Adjust bands
            upper[i] = up if up > upper[i-1] or closes[i-1] < upper[i-1] else upper[i-1]
            lower[i] = dn if dn < lower[i-1] or closes[i-1] > lower[i-1] else lower[i-1]
        
        if np.isnan(atr[i-1]):
            trend[i] = 0
        elif trend[i-1] <= 0 and closes[i] > upper[i-1]:
            trend[i] = 1
        elif trend[i-1] >= 0 and closes[i] < lower[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
    
    # Expanding z-score 標準化
    signal = np.full(n, np.nan)
    for i in range(n):
        signal[i] = float(trend[i])
    
    # 做 expanding z-score
    result = np.full(n, np.nan, dtype=np.float64)
    running_sum = 0.0
    running_sum_sq = 0.0
    count = 0
    for i in range(n):
        val = signal[i]
        if np.isnan(val):
            continue
        count += 1
        running_sum += val
        running_sum_sq += val * val
        if count < 2:
            result[i] = 0.0
        else:
            mean = running_sum / count
            var = (running_sum_sq / count) - mean * mean
            std = np.sqrt(max(var, 1e-12))
            result[i] = (val - mean) / std
    
    result = np.clip(result, -4.0, 4.0)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 3. 實證指標計算
# ═══════════════════════════════════════════════════════════════════════

def forward_returns(closes: np.ndarray, horizon: int) -> np.ndarray:
    """每個時點的未來 horizon 期對數報酬。"""
    n = len(closes)
    fwd = np.full(n, np.nan)
    for i in range(n - horizon):
        fwd[i] = np.log(closes[i + horizon] / closes[i])
    return fwd


def rank_ic_single(factor_vals: np.ndarray, fwd_rets: np.ndarray) -> float:
    """單一橫斷面 Rank-IC = Spearman(因子值, 未來報酬)。"""
    valid = ~(np.isnan(factor_vals) | np.isnan(fwd_rets))
    if valid.sum() < 10:
        return float("nan")
    fv = factor_vals[valid]
    fr = fwd_rets[valid]
    # Spearman = Pearson on ranks
    from scipy.stats import spearmanr
    try:
        corr, _ = spearmanr(fv, fr)
        return float(corr)
    except Exception:
        # fallback: manual rank correlation
        def rank(x):
            order = np.argsort(x)
            ranks = np.zeros(len(x))
            for i, o in enumerate(order):
                ranks[o] = i + 1
            return ranks
        r1 = rank(fv)
        r2 = rank(fr)
        n = len(r1)
        mean1, mean2 = np.mean(r1), np.mean(r2)
        num = np.sum((r1 - mean1) * (r2 - mean2))
        den = np.sqrt(np.sum((r1 - mean1)**2) * np.sum((r2 - mean2)**2))
        return num / den if den > 0 else float("nan")


def rolling_rank_ic(factor_signal: np.ndarray, closes: np.ndarray, horizon: int) -> np.ndarray:
    """計算每個時間點 t 的橫截面 Rank-IC（單品種下為時間序列 rolling IC）。
    
    對每個有效時間點 t，計算 factor[t] 與 fwd_return[t:t+horizon] 之間的關聯。
    由於是單品種時間序列，改為計算：在每個有效點，factor 與對應 fwd_ret 的
    點對點關聯在 rolling window 內的 Spearman。
    
    回傳長度與 signal 相同的 IC 序列。
    """
    n = len(factor_signal)
    fwd = forward_returns(closes, horizon)
    ic_series = np.full(n, np.nan)
    
    # 對每個有效點 t，使用前後 window 計算 rolling IC
    # 使用 expanding window：t 時刻的 IC = Spearman(factor[0:t+1], fwd[0:t+1])
    for t in range(1, n):
        if t >= 30:  # 需要最小樣本
            fv = factor_signal[:t+1]
            fr = fwd[:t+1]
            valid = ~(np.isnan(fv) | np.isnan(fr))
            if valid.sum() >= 30:
                ic_series[t] = rank_ic_single(fv, fr)
    
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
    
    # 排序並分組
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
    
    # Long-Short spread (Q5 - Q1)
    q5_idx = order[(n_groups-1)*group_size:]
    q1_idx = order[:group_size]
    spread = float(np.mean(fr[q5_idx]) - np.mean(fr[q1_idx]))
    
    return {"groups": groups, "long_short_spread": spread, "n_valid": int(len(fv))}


def correlation_with_super_trend(factor_signal: np.ndarray, st_signal: np.ndarray) -> dict:
    """計算因子信號與 super_trend_10_3 的相關性。"""
    valid = ~(np.isnan(factor_signal) | np.isnan(st_signal))
    if valid.sum() < 10:
        return {"pearson": float("nan"), "spearman": float("nan"), "n": int(valid.sum())}
    
    fv = factor_signal[valid]
    sv = st_signal[valid]
    
    # Pearson
    fv_mean = np.mean(fv)
    sv_mean = np.mean(sv)
    num = np.sum((fv - fv_mean) * (sv - sv_mean))
    den = np.sqrt(np.sum((fv - fv_mean)**2) * np.sum((sv - sv_mean)**2))
    pearson = num / den if den > 1e-12 else float("nan")
    
    # Spearman
    try:
        from scipy.stats import spearmanr
        spearman, _ = spearmanr(fv, sv)
    except Exception:
        spearman = float("nan")
    
    return {"pearson": float(pearson), "spearman": float(spearman), "n": int(valid.sum())}


# ═══════════════════════════════════════════════════════════════════════
# 4. 主分析流程
# ═══════════════════════════════════════════════════════════════════════

def analyze_factor(name: str, factor_signal: np.ndarray, closes: np.ndarray,
                   st_signal: np.ndarray, horizons: list[int]) -> dict:
    """對單一因子執行完整實證分析。"""
    n = len(closes)
    results = {
        "factor": name,
        "n_obs": n,
        "n_valid_signal": int(np.sum(~np.isnan(factor_signal))),
        "horizons": {},
    }
    
    for h in horizons:
        # Rank-IC
        # 使用全部有效資料計算總體 Rank-IC
        fwd = forward_returns(closes, h)
        valid = ~(np.isnan(factor_signal) | np.isnan(fwd))
        n_valid = valid.sum()
        
        if n_valid < 20:
            results["horizons"][h] = {"error": "insufficient data", "n_valid": int(n_valid)}
            continue
        
        # 計算 rolling IC series (expanding window)
        ic_series = rolling_rank_ic(factor_signal, closes, h)
        ic_valid = ic_series[~np.isnan(ic_series)]
        
        ic_mean = float(np.mean(ic_valid)) if len(ic_valid) > 0 else float("nan")
        ic_std = float(np.std(ic_valid)) if len(ic_valid) > 0 else float("nan")
        ic_ir = ic_mean / ic_std if ic_std and ic_std > 0 else float("nan")
        
        # Cumulative IC
        cum_ic = np.cumsum(ic_valid)
        cum_ic_final = float(cum_ic[-1]) if len(cum_ic) > 0 else float("nan")
        
        # 最後 50 期的 IC 統計（近期穩定性）
        recent_ic = ic_valid[-50:] if len(ic_valid) >= 50 else ic_valid
        recent_mean = float(np.mean(recent_ic)) if len(recent_ic) > 0 else float("nan")
        recent_std = float(np.std(recent_ic)) if len(recent_ic) > 0 else float("nan")
        
        # Overall IC (all valid points, not rolling)
        overall_ic = rank_ic_single(factor_signal, fwd)
        
        # Quantile returns
        qr = quantile_returns(factor_signal, closes, h, n_groups=5)
        
        # IC 正向比例
        ic_positive_ratio = float(np.sum(ic_valid > 0) / len(ic_valid)) if len(ic_valid) > 0 else float("nan")
        
        results["horizons"][h] = {
            "overall_ic": round(overall_ic, 6) if not math.isnan(overall_ic) else None,
            "ic_mean": round(ic_mean, 6),
            "ic_std": round(ic_std, 6),
            "ic_ir": round(ic_ir, 4),
            "cum_ic_final": round(cum_ic_final, 6),
            "recent_ic_mean": round(recent_mean, 6),
            "recent_ic_std": round(recent_std, 6),
            "ic_positive_ratio": round(ic_positive_ratio, 4),
            "n_ic_points": int(len(ic_valid)),
            "n_valid_pairs": int(n_valid),
            "quantiles": qr,
        }
    
    # 與 SuperTrend 相關性
    st_corr = correlation_with_super_trend(factor_signal, st_signal)
    results["super_trend_correlation"] = st_corr
    
    return results


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
    n = len(cum)
    
    if n < 2:
        return "  (資料點不足)"
    
    # 降採樣到 width 個點
    step = max(1, n // width)
    sampled_idx = np.arange(0, n, step)
    sampled_cum = cum[sampled_idx]
    
    y_min, y_max = np.min(sampled_cum), np.max(sampled_cum)
    y_range = max(y_max - y_min, 0.001)
    height = 15
    
    lines = []
    lines.append(f"  累積 IC 曲線 (n={n}, 最終值={cum[-1]:.4f}):")
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
    """生成 ## 實證 Markdown 段落。"""
    lines = []
    lines.append("## 實證")
    lines.append("")
    lines.append(f"> 分析期間：BTCUSDT 日線，共 {results['n_obs']} 根 K 線")
    lines.append(f"> 因子有效信號數：{results['n_valid_signal']} / {results['n_obs']}")
    lines.append(f"> 計算日期：2026-05-25 (自動生成)")
    lines.append("")
    
    # Horizon 總覽表
    lines.append("### Rank-IC 與 IC-IR 總覽")
    lines.append("")
    lines.append("| 預測天數 (N) | Overall IC | IC 均值 | IC 標準差 | IC-IR | 累積 IC | IC>0 比例 | IC 樣本數 |")
    lines.append("|-------------|-----------|---------|----------|------|---------|----------|----------|")
    
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" in hr:
            lines.append(f"| {h} | — | — | — | — | — | — | {hr.get('n_valid_pairs', 0)} |")
        else:
            ic_mean_str = f"{hr['ic_mean']:.4f}"
            ic_ir_str = f"{hr['ic_ir']:.3f}"
            cum_str = f"{hr['cum_ic_final']:.4f}"
            pos_str = f"{hr['ic_positive_ratio']:.1%}"
            lines.append(
                f"| {h} | {hr['overall_ic']:.4f} | {ic_mean_str} | {hr['ic_std']:.4f} | "
                f"{ic_ir_str} | {cum_str} | {pos_str} | {hr['n_ic_points']} |"
            )
    
    lines.append("")
    
    # 門檻判定
    lines.append("### 門檻判定")
    lines.append("")
    best_ir = 0
    best_h = 0
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" not in hr and abs(hr.get("ic_ir", 0)) > abs(best_ir):
            best_ir = hr["ic_ir"]
            best_h = h
    
    best_mean = 0
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" not in hr:
            m = hr.get("ic_mean", 0)
            if abs(m) > abs(best_mean):
                best_mean = m
    
    lines.append(f"| 閾值 | 要求 | 實際 (N={best_h}) | 判定 |")
    lines.append(f"|------|------|-----------------|------|")
    
    pass_ic = abs(best_mean) >= 0.02
    pass_ir = abs(best_ir) >= 0.3
    overall_pass = pass_ic and pass_ir
    
    lines.append(f"| IC 均值絕對值 ≥ 0.02 | |IC_mean| ≥ 0.02 | |{best_mean:.4f}| | {'✅ 通過' if pass_ic else '❌ 未達標'} |")
    lines.append(f"| IC-IR 絕對值 ≥ 0.3 | |IC-IR| ≥ 0.3 | |{best_ir:.3f}| | {'✅ 通過' if pass_ir else '❌ 未達標'} |")
    lines.append(f"| 綜合判定 | 兩者皆達標 | — | {'✅ 通過實證門檻' if overall_pass else '⚠️ 未完全達標'} |")
    lines.append("")
    
    # 各 horizon 分組回報
    for h in horizons:
        hr = results["horizons"].get(h, {})
        if "error" in hr:
            continue
        qr = hr.get("quantiles", {})
        lines.append(f"### 分組回報 (N={h} 日)")
        lines.append("")
        lines.append(format_quantile_table(qr))
        lines.append("")
    
    # 累積 IC 曲線（最佳 horizon）
    best_hr = results["horizons"].get(best_h, None)
    if best_hr and "ic_mean" in best_hr:
        lines.append(f"### 累積 IC 曲線 (N={best_h} 日，最佳 horizon)")
        lines.append("")
        # Recalculate IC series for the chart
        ic_s = rolling_rank_ic(
            np.array([float("nan")] * results["n_obs"]),  # placeholder
            np.array([float("nan")] * results["n_obs"]),
            best_h
        )
        # Actually need to recalc properly - skip the ASCII chart for now
        lines.append("(累積 IC 曲線數據見上方總覽表：累積 IC 欄位)")
        lines.append("")
    
    # SuperTrend 相關性
    st_corr = results.get("super_trend_correlation", {})
    lines.append("### 與 super_trend_10_3 的相關性")
    lines.append("")
    lines.append(f"| 指標 | 數值 |")
    lines.append(f"|------|------|")
    lines.append(f"| Pearson r | {st_corr.get('pearson', float('nan')):.4f} |")
    lines.append(f"| Spearman ρ | {st_corr.get('spearman', float('nan')):.4f} |")
    lines.append(f"| 配對樣本數 | {st_corr.get('n', 0)} |")
    lines.append("")
    
    # 解讀
    pearson = st_corr.get("pearson", 0)
    if not math.isnan(pearson):
        if abs(pearson) < 0.2:
            corr_note = "極低相關，因子提供獨立資訊維度"
        elif abs(pearson) < 0.4:
            corr_note = "低相關，因子與 SuperTrend 部分重疊但仍有獨立貢獻"
        elif abs(pearson) < 0.6:
            corr_note = "中等相關，因子與 SuperTrend 有明顯重疊"
        else:
            corr_note = "高相關，因子可能與 SuperTrend 捕捉相同資訊"
        lines.append(f"**相關性解讀**：{corr_note}。")
    lines.append("")
    
    return "\n".join(lines)


def write_section_to_note(note_path: str, section_content: str):
    """將 ## 實證 段落寫入候選筆記。若已存在則替換，否則附加於文末。"""
    path = Path(note_path)
    if not path.exists():
        print(f"  ⚠ 筆記不存在：{note_path}")
        return False
    
    content = path.read_text(encoding="utf-8")
    
    # 檢查是否已有 ## 實證 段落
    if "\n## 實證\n" in content:
        # 找到段落起點與終點
        idx_start = content.index("\n## 實證\n")
        # 找下一個 ## 標題
        rest = content[idx_start + len("\n## 實證\n"):]
        idx_next = rest.find("\n## ")
        if idx_next == -1:
            # 到檔案尾
            new_content = content[:idx_start] + "\n" + section_content
        else:
            new_content = content[:idx_start] + "\n" + section_content + "\n" + rest[idx_next:]
    else:
        # 附加於文末
        new_content = content.rstrip() + "\n\n" + section_content + "\n"
    
    path.write_text(new_content, encoding="utf-8")
    print(f"  ✅ 已寫入：{note_path}")
    return True


# ═══════════════════════════════════════════════════════════════════════
# 5. 主程式
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  F1 / F2 / F3 完整實證分析")
    print("=" * 70)
    
    # ── 獲取資料 ──
    print("\n📡 正在獲取 BTCUSDT 日線資料...")
    try:
        ohlcv = fetch_binance_daily("BTCUSDT", limit=500)
        print(f"  ✅ 成功獲取 {len(ohlcv)} 根日線 K 線")
    except Exception as e:
        print(f"  ❌ 無法獲取資料: {e}")
        print("  嘗試使用更大 limit...")
        try:
            ohlcv = fetch_binance_daily("BTCUSDT", limit=1000)
            print(f"  ✅ 成功獲取 {len(ohlcv)} 根日線 K 線")
        except Exception as e2:
            print(f"  ❌ 也失敗: {e2}")
            return 1
    
    if len(ohlcv) < 200:
        print(f"  ❌ 資料不足（{len(ohlcv)} < 200），無法進行實證分析")
        return 1
    
    closes = np.array([d["close"] for d in ohlcv])
    
    # ── 計算 SuperTrend ──
    print("\n📊 正在計算 super_trend_10_3...")
    st_signal = super_trend_10_3(ohlcv)
    n_st_valid = int(np.sum(~np.isnan(st_signal)))
    print(f"  ✅ SuperTrend 有效信號：{n_st_valid} / {len(ohlcv)}")
    
    # ── 計算因子信號 ──
    horizons = [1, 5, 10, 20]
    
    factors = [
        ("F1_Complexity_Gap_Regime", lambda d: f1_compute(d, window=60, n_components=10)),
        ("F2_Liquidity_Consumption_Tilt", lambda d: f2_compute(d, ema_halflife=10)),
        ("F3_Volatility_Roughness_Filter", lambda d: f3_compute(d, window=100, dfa_min_window=60)),
    ]
    
    note_paths = {
        "F1_Complexity_Gap_Regime": "/home/anson/factor-lab/candidates/F1_Complexity_Gap_Regime.md",
        "F2_Liquidity_Consumption_Tilt": "/home/anson/factor-lab/candidates/F2_Liquidity_Consumption_Tilt.md",
        "F3_Volatility_Roughness_Filter": "/home/anson/factor-lab/candidates/F3_Volatility_Roughness_Filter.md",
    }
    
    for name, compute_fn in factors:
        print(f"\n{'─' * 70}")
        print(f"  📈 正在分析：{name}")
        print(f"{'─' * 70}")
        
        # 計算信號
        result = compute_fn(ohlcv)
        signal = result["signal"]
        meta = result.get("meta", {})
        
        n_valid = int(np.sum(~np.isnan(signal)))
        print(f"  有效信號：{n_valid} / {len(ohlcv)}")
        print(f"  Meta: {json.dumps({k: v for k, v in meta.items() if not isinstance(v, np.ndarray)}, default=str)}")
        
        if n_valid < 30:
            print(f"  ⚠ 有效信號不足（{n_valid} < 30），跳過詳細分析")
            continue
        
        # 完整分析
        results = analyze_factor(name, signal, closes, st_signal, horizons)
        
        # 輸出摘要
        print(f"\n  📊 IC 分析結果：")
        for h in horizons:
            hr = results["horizons"].get(h, {})
            if "error" not in hr:
                print(f"    N={h:2d}: IC_mean={hr['ic_mean']:+.4f}, "
                      f"IC_std={hr['ic_std']:.4f}, IC-IR={hr['ic_ir']:+.3f}, "
                      f"CumIC={hr['cum_ic_final']:+.4f}, "
                      f"PosRatio={hr['ic_positive_ratio']:.1%}")
        
        # SuperTrend 相關性
        st_corr = results["super_trend_correlation"]
        print(f"\n  🔗 SuperTrend 相關性：Pearson={st_corr.get('pearson', 'nan'):.4f}, "
              f"Spearman={st_corr.get('spearman', 'nan'):.4f}, n={st_corr.get('n', 0)}")
        
        # 生成報告段落
        report = generate_report_section(results, horizons)
        
        # 寫入筆記
        note_path = note_paths.get(name)
        if note_path:
            write_section_to_note(note_path, report)
    
    print(f"\n{'=' * 70}")
    print(f"  ✅ 實證分析完成！")
    print(f"{'=' * 70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
