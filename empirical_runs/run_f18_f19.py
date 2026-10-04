"""
Empirical analysis for F18 (Gap-Drift Reconciliation Spread) and
F19 (Higher-High Lower-Low Asymmetry).

- Multi-horizon Rank-IC (1/5/10/20d)
- 5-group position-weighted long-short strategy at H=5
- Sharpe annualised by sqrt(365/h)
- Monotonicity, NaN ratio, look-ahead and subperiod robustness
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path("/home/anson/factor-lab")
sys.path.insert(0, str(ROOT))

from core.adapters.crypto import CryptoAdapter
from core.signals.F18_Gap_Drift_Reconciliation_Spread import factor as f18_factor
from core.signals.F19_Higher_High_Lower_Low_Asymmetry import factor as f19_factor

OUT_DIR = ROOT / "empirical_runs"
DATA_PARQUET = OUT_DIR / "btcusdt_1d_1500.pkl"
HORIZONS = [1, 5, 10, 20]
GROUPS = 5


def fetch_data() -> pd.DataFrame:
    if DATA_PARQUET.exists():
        df = pd.read_pickle(DATA_PARQUET)
    else:
        a = CryptoAdapter()
        df = a.get_ohlcv("BTCUSDT", timeframe="1d", limit=1500)
        df.to_pickle(DATA_PARQUET)
    # Normalise index to DatetimeIndex if needed
    if "timestamp" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        ts = pd.to_datetime(df["timestamp"], unit="ms" if df["timestamp"].iloc[0] > 1e11 else "s",
                            errors="coerce")
        if ts.isna().all():
            ts = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.set_index(ts).drop(columns=["timestamp"])
        df.index.name = "datetime"
    return df


def preprocess_signal(s: pd.Series) -> pd.Series:
    """winsorize 1%/99% -> z-score -> clip ±3."""
    s = s.copy()
    lo, hi = s.quantile(0.01), s.quantile(0.99)
    s = s.clip(lower=lo, upper=hi)
    mu, sd = s.mean(), s.std()
    if sd == 0 or np.isnan(sd):
        return s * 0
    z = (s - mu) / sd
    return z.clip(-3, 3)


def fwd_return(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def horizon_ic_table(signal: pd.Series, close: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    rows = []
    for h in horizons:
        fr = fwd_return(close, h)
        # Rolling per-window IC doesn't make sense for single asset.
        # We compute one full-sample spearman + a rolling spearman series
        # for IC std/IC-IR/positive-rate diagnostics.
        df = pd.concat([signal.rename("s"), fr.rename("r")], axis=1).dropna()
        if len(df) < 30:
            rows.append({"horizon": h, "rank_ic": np.nan, "ic_std": np.nan,
                         "ic_ir": np.nan, "ic_pos_pct": np.nan, "n": len(df)})
            continue
        full_ic, _ = stats.spearmanr(df["s"], df["r"])

        # Rolling 60d IC for std / IR / >0%
        win = 60
        rolling_ics = []
        s_arr = df["s"].values
        r_arr = df["r"].values
        for i in range(win, len(df) + 1):
            ic, _ = stats.spearmanr(s_arr[i - win : i], r_arr[i - win : i])
            if not (ic is None or (isinstance(ic, float) and math.isnan(ic))):
                rolling_ics.append(ic)
        rolling_ics = np.array(rolling_ics)
        if len(rolling_ics) > 0:
            ic_mean_r = rolling_ics.mean()
            ic_std_r = rolling_ics.std(ddof=1) if len(rolling_ics) > 1 else np.nan
            ic_ir = ic_mean_r / ic_std_r if ic_std_r and ic_std_r > 0 else np.nan
            pos_pct = float((rolling_ics > 0).mean())
        else:
            ic_std_r = np.nan
            ic_ir = np.nan
            pos_pct = np.nan
        rows.append({
            "horizon": h,
            "rank_ic": full_ic,        # full-sample spearman
            "ic_std": ic_std_r,        # 60d rolling IC std
            "ic_ir": ic_ir,            # 60d IC mean / std
            "ic_pos_pct": pos_pct,
            "n": int(len(df)),
        })
    return pd.DataFrame(rows)


def grouped_position_weighted(signal: pd.Series, close: pd.Series, h: int = 5,
                              groups: int = GROUPS) -> dict:
    fr = fwd_return(close, h)
    df = pd.concat([signal.rename("s"), fr.rename("r")], axis=1).dropna()
    if len(df) < groups * 5:
        return {}
    try:
        labels = pd.qcut(df["s"], groups, labels=False, duplicates="drop")
    except Exception:
        return {}
    df["g"] = labels
    grp_stats = []
    for g in sorted(df["g"].dropna().unique()):
        sub = df[df["g"] == g]
        ann = sub["r"].mean() * (365.0 / h)
        cum = (1 + sub["r"]).prod() - 1
        grp_stats.append({"group": int(g), "mean_ret": sub["r"].mean(),
                          "annualized": ann, "cum_ret": cum, "n": len(sub)})
    grp_df = pd.DataFrame(grp_stats).sort_values("group").reset_index(drop=True)

    g_max = int(df["g"].max())
    g_min = int(df["g"].min())
    pos = pd.Series(0.0, index=df.index)
    pos[df["g"] == g_max] = 1.0
    pos[df["g"] == g_min] = -1.0
    strat = pos * df["r"]
    n_eff = len(strat)
    mean_r = strat.mean()
    std_r = strat.std(ddof=1)
    ann_ret = mean_r * (365.0 / h)
    ann_sharpe = (mean_r / std_r) * math.sqrt(365.0 / h) if std_r and std_r > 0 else np.nan

    # Max drawdown of cumulative strategy returns (non-overlapping approx)
    cum = (1 + strat).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()

    # Turnover proxy: position changes
    turnover = (pos.diff().abs() > 0).sum() / max(1, n_eff) * 365  # per year

    # Monotonicity: rank corr between group rank and group mean ret
    mono_corr, _ = stats.spearmanr(grp_df["group"], grp_df["mean_ret"])
    return {
        "group_table": grp_df,
        "long_short": {
            "ann_ret": ann_ret,
            "ann_sharpe": ann_sharpe,
            "max_dd": max_dd,
            "turnover_per_year": turnover,
            "mean_per_period": mean_r,
            "std_per_period": std_r,
            "n_obs": n_eff,
            "q5_minus_q1_mean": grp_df.iloc[-1]["mean_ret"] - grp_df.iloc[0]["mean_ret"],
            "q5_minus_q1_ann": grp_df.iloc[-1]["annualized"] - grp_df.iloc[0]["annualized"],
        },
        "monotonicity_corr": mono_corr,
    }


def subperiod_ic(signal: pd.Series, close: pd.Series, h: int = 5) -> dict:
    fr = fwd_return(close, h)
    df = pd.concat([signal.rename("s"), fr.rename("r")], axis=1).dropna()
    if len(df) < 200:
        return {"first": np.nan, "second": np.nan}
    mid = len(df) // 2
    first = df.iloc[:mid]
    second = df.iloc[mid:]

    def ir(sub):
        win = 60
        ics = []
        s_arr = sub["s"].values
        r_arr = sub["r"].values
        for i in range(win, len(sub) + 1):
            ic, _ = stats.spearmanr(s_arr[i - win : i], r_arr[i - win : i])
            if ic == ic:
                ics.append(ic)
        a = np.array(ics)
        if len(a) < 2:
            return np.nan
        return a.mean() / a.std(ddof=1) if a.std(ddof=1) > 0 else np.nan

    return {"first": ir(first), "second": ir(second)}


def lookahead_check(raw_signal_func, ohlcv: pd.DataFrame) -> bool:
    """Confirm signal at t does not depend on t's close: signal_t should be
    derivable from data up to and including t-1 (after shift). Check that the
    signal series is at least .shift(1)-aligned (NaN at first non-warmup index)."""
    s = raw_signal_func(ohlcv)
    # all signal functions in F18/F19 perform a .shift(1) at the end.
    # We re-derive: compute on truncated frame, check stability.
    # If truncating last row doesn't change earlier non-NaN values → no look-ahead.
    truncated = ohlcv.iloc[:-1].copy()
    s_full = s.iloc[:-1]
    s_trunc = raw_signal_func(truncated)
    # Compare last 50 overlap entries
    overlap = s_full.dropna().index.intersection(s_trunc.dropna().index)
    if len(overlap) < 10:
        return False
    diffs = (s_full.loc[overlap] - s_trunc.loc[overlap]).abs()
    return bool(diffs.max() < 1e-10)


def format_table(grp_df: pd.DataFrame) -> str:
    rows = []
    rows.append("| 組別 | 平均報酬 | 年化 | 累積總報酬 |")
    rows.append("|------|---------|------|-----------|")
    g_min = grp_df["group"].min()
    g_max = grp_df["group"].max()
    for _, r in grp_df.iterrows():
        label = f"Q{int(r['group']) + 1}"
        suffix = ""
        if r["group"] == g_min:
            suffix = " (最低)"
        elif r["group"] == g_max:
            suffix = " (最高)"
        rows.append(f"| {label}{suffix} | {r['mean_ret']*100:.3f}% | {r['annualized']*100:.2f}% | {r['cum_ret']*100:.2f}% |")
    q5_q1 = grp_df.iloc[-1]["mean_ret"] - grp_df.iloc[0]["mean_ret"]
    q5_q1_ann = grp_df.iloc[-1]["annualized"] - grp_df.iloc[0]["annualized"]
    q5_q1_cum = grp_df.iloc[-1]["cum_ret"] - grp_df.iloc[0]["cum_ret"]
    rows.append(f"| Q5-Q1 spread | {q5_q1*100:.3f}% | {q5_q1_ann*100:.2f}% | {q5_q1_cum*100:.2f}% |")
    return "\n".join(rows)


def render_markdown(name: str, code: str, info: dict) -> str:
    ic_tab = info["ic_table"]
    lines = []
    lines.append("## 實證 (empiricist)\n")
    lines.append("### 數據範圍")
    lines.append(f"- 標的：BTCUSDT")
    lines.append(f"- 頻率：日線")
    lines.append(f"- 期間：{info['date_start']} ~ {info['date_end']}（{info['n_valid']} 筆有效訊號觀測，總 {info['n_rows']} 根 K 線）\n")

    lines.append("### 預測力指標（多 horizon, full-sample Spearman + 60d rolling 統計）")
    lines.append("| Horizon | Rank-IC | IC Std (60d) | IC-IR (60d) | IC>0% |")
    lines.append("|---------|---------|--------------|-------------|-------|")
    for _, r in ic_tab.iterrows():
        ic = r["rank_ic"]; ic_std = r["ic_std"]; ic_ir = r["ic_ir"]; pos = r["ic_pos_pct"]
        lines.append(f"| {int(r['horizon'])} 日 | {ic:+.4f} | {ic_std:.4f} | {ic_ir:+.3f} | {pos*100:.1f}% |")
    lines.append("")

    lines.append("### 分組回報（5 組，5 日 horizon，position-weighted）")
    lines.append(format_table(info["grp_df"]))
    lines.append("")

    ls = info["long_short"]
    lines.append("### Long-Short 策略績效 (H=5, position-weighted)")
    lines.append(f"- 平均單期報酬：{ls['mean_per_period']*100:.4f}%（{ls['n_obs']} 期）")
    lines.append(f"- 年化報酬：{ls['ann_ret']*100:.2f}%")
    lines.append(f"- 年化 Sharpe：{ls['ann_sharpe']:.3f}")
    lines.append(f"- 最大回撤：{ls['max_dd']*100:.2f}%")
    lines.append(f"- 換手率（pos 變動估計）：{ls['turnover_per_year']:.1f} 次/年\n")

    lines.append("### 穩健性檢查")
    lines.append("| 檢查項 | 結果 |")
    lines.append("|-------|------|")
    la = "✅" if info["lookahead_pass"] else "❌"
    lines.append(f"| 前視偏誤（截斷重算一致性） | {la} |")
    sp = info["subperiod"]
    lines.append(f"| 子期 IC-IR (前/後, H=5) | {sp['first']:.3f} / {sp['second']:.3f} |")
    mono = info["monotonicity_corr"]
    mono_pass = "✅" if mono >= 0.7 else ("⚠️" if mono >= 0.3 else "❌")
    lines.append(f"| Monotonicity (group rank vs mean ret Spearman) | {mono:+.3f} {mono_pass} |")
    lines.append(f"| 訊號 NaN 佔比 | {info['nan_ratio']*100:.2f}% |")
    lines.append("")

    lines.append("### 問題與發現")
    findings = info["findings"]
    for f in findings:
        lines.append(f"- {f}")
    lines.append("")
    lines.append(f"_實證 run 產物：`empirical_runs/{code}_results.json`_")
    return "\n".join(lines)


def analyse_factor(name: str, code: str, signal_func, ohlcv: pd.DataFrame) -> dict:
    raw_signal = signal_func(ohlcv)
    sig = preprocess_signal(raw_signal.dropna())
    sig = sig.reindex(ohlcv.index)
    close = ohlcv["close"]

    ic_tab = horizon_ic_table(sig, close)
    g_info = grouped_position_weighted(sig, close, h=5)
    sp = subperiod_ic(sig, close, h=5)
    la_pass = lookahead_check(signal_func, ohlcv)
    nan_ratio = float(raw_signal.isna().mean())

    findings = []
    h5_row = ic_tab[ic_tab["horizon"] == 5].iloc[0]
    if abs(h5_row["rank_ic"]) < 0.02:
        findings.append(f"H=5 Rank-IC ({h5_row['rank_ic']:+.4f}) 未達 |IC|>0.02 門檻。")
    if h5_row["ic_ir"] != h5_row["ic_ir"] or abs(h5_row["ic_ir"]) < 0.3:
        findings.append(f"H=5 60d rolling IC-IR ({h5_row['ic_ir']:.3f}) 未達 0.3 門檻。")
    if g_info and g_info["long_short"]["ann_sharpe"] < 0.5:
        findings.append(f"Long-Short Sharpe ({g_info['long_short']['ann_sharpe']:.3f}) 未達 0.5 門檻。")
    if g_info and g_info["long_short"]["max_dd"] < -0.30:
        findings.append(f"最大回撤 {g_info['long_short']['max_dd']*100:.1f}% 超過 -30%。")
    if g_info and g_info["monotonicity_corr"] < 0.3:
        findings.append(f"Monotonicity rank correlation 過低 ({g_info['monotonicity_corr']:.3f})，分組響應非單調。")
    # IC sign consistency across horizons
    signs = np.sign(ic_tab["rank_ic"].values)
    if len(set(signs)) > 1:
        findings.append("不同 horizon 的 Rank-IC 出現符號反轉，可能存在快速衰減或反轉效應。")
    # IC decay
    icr = ic_tab.set_index("horizon")["rank_ic"]
    if abs(icr.get(20, np.nan)) > abs(icr.get(1, np.nan)) * 1.5:
        findings.append("IC 在 20 日反而強於 1 日 → 訊號偏長期效應或存在 horizon 偏好。")
    if not findings:
        findings.append("無顯著異常，訊號於 5 日 horizon 上表現符合預期方向。")

    sig_valid = sig.dropna()
    info = {
        "n_rows": len(ohlcv),
        "n_valid": int(sig_valid.shape[0]),
        "date_start": str(ohlcv.index.min().date()),
        "date_end": str(ohlcv.index.max().date()),
        "ic_table": ic_tab,
        "grp_df": g_info.get("group_table", pd.DataFrame()),
        "long_short": g_info.get("long_short", {}),
        "monotonicity_corr": g_info.get("monotonicity_corr", np.nan),
        "subperiod": sp,
        "lookahead_pass": la_pass,
        "nan_ratio": nan_ratio,
        "findings": findings,
    }
    return info


def main():
    ohlcv = fetch_data()
    print(f"OHLCV: {len(ohlcv)} rows, {ohlcv.index.min()} → {ohlcv.index.max()}")
    print(f"columns={list(ohlcv.columns)}")

    results = {}
    for name, code, func in [
        ("F18 Gap-Drift Reconciliation Spread", "F18", f18_factor),
        ("F19 Higher-High Lower-Low Asymmetry", "F19", f19_factor),
    ]:
        print(f"\n=== {name} ===")
        info = analyse_factor(name, code, func, ohlcv)
        print(info["ic_table"].to_string(index=False))
        if not info["grp_df"].empty:
            print(info["grp_df"].to_string(index=False))
        print({k: v for k, v in info["long_short"].items()})
        print(f"monotonicity={info['monotonicity_corr']:.3f}, lookahead_ok={info['lookahead_pass']}, nan%={info['nan_ratio']*100:.2f}, subperiod={info['subperiod']}")

        md = render_markdown(name, code, info)
        (OUT_DIR / f"{code}_empirical.md").write_text(md)
        # Persist a JSON dump (excluding DataFrames)
        json_dump = {
            "n_rows": info["n_rows"],
            "n_valid": info["n_valid"],
            "date_start": info["date_start"],
            "date_end": info["date_end"],
            "ic_table": info["ic_table"].to_dict(orient="records"),
            "grp_table": info["grp_df"].to_dict(orient="records"),
            "long_short": info["long_short"],
            "monotonicity_corr": info["monotonicity_corr"],
            "subperiod": info["subperiod"],
            "lookahead_pass": info["lookahead_pass"],
            "nan_ratio": info["nan_ratio"],
            "findings": info["findings"],
        }
        (OUT_DIR / f"{code}_results.json").write_text(
            json.dumps(json_dump, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
        )
        results[code] = info

    print("\n--- DONE ---")


if __name__ == "__main__":
    main()
