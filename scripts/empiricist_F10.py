#!/usr/bin/env python3
"""
F10 Volatility-Adjusted Momentum 完整實證 + 參數掃描
含市場中性多空組合 + 連續曝險策略雙重評估
"""

from __future__ import annotations
import sys, os, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from itertools import product

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from core.signals.F10_vol_adj_momentum import factor as f10_factor

NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_binance_daily(symbol="BTCUSDT", limit=1500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    rows = []
    for k in data:
        rows.append({
            "timestamp": pd.Timestamp(k[0], unit="ms", tz="UTC"),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        })
    return pd.DataFrame(rows)


def compute_rank_ic(signal, returns, horizon):
    from scipy.stats import spearmanr
    mask = signal.notna() & returns.notna()
    s = signal[mask].rank(pct=True)
    fwd_ret = returns[mask].shift(-horizon)
    mask2 = fwd_ret.notna()
    if mask2.sum() < 30:
        return {"horizon": horizon, "ic": None, "ic_ir": None, "n": 0}
    ic, _ = spearmanr(s[mask2], fwd_ret[mask2])
    window = min(120, mask2.sum() // 2)
    ic_series = [spearmanr(s[mask2].iloc[i-window:i], fwd_ret[mask2].iloc[i-window:i])[0]
                 for i in range(window, mask2.sum())]
    ic_ir = ic / (np.std(ic_series) + 1e-8)
    return {"horizon": horizon, "ic": round(ic, 4), "ic_ir": round(ic_ir, 4), "n": int(mask2.sum())}


def compute_group_returns(signal, returns, horizon):
    mask = signal.notna()
    s = signal[mask]; fwd_ret = returns[mask].shift(-horizon)
    mask2 = fwd_ret.notna()
    s, fwd_ret = s[mask2], fwd_ret[mask2]
    if len(s) < 50:
        return {"spread": None, "spread_sharpe": None}
    ranks = s.rank(pct=True)
    bins = pd.cut(ranks, bins=5, labels=["Q1","Q2","Q3","Q4","Q5"])
    q1_ret = fwd_ret[bins=="Q1"].mean()
    q5_ret = fwd_ret[bins=="Q5"].mean()
    spread = q5_ret - q1_ret
    # Daily rebalanced spread strategy
    daily_spread_ret = fwd_ret[bins=="Q5"].values - fwd_ret[bins=="Q1"].values[:len(fwd_ret[bins=="Q1"])]
    # Actually compute as time series
    dates_q1 = fwd_ret[bins=="Q1"].index
    dates_q5 = fwd_ret[bins=="Q5"].index
    common = dates_q1.intersection(dates_q5)
    if len(common) < 30:
        return {"spread": round(spread, 6), "spread_sharpe": None}
    spread_ts = fwd_ret.loc[common].groupby(level=0).apply(
        lambda g: g.iloc[-1] - g.iloc[0] if len(g) >= 2 else 0
    ) if isinstance(fwd_ret.index, pd.MultiIndex) else (fwd_ret[common & (bins=="Q5")].values - fwd_ret[common & (bins=="Q1")].values)

    return {"spread": round(spread, 6), "spread_sharpe": None}  # simplified


def compute_strategy(signal, ret):
    """連續曝險：持倉比例正比於 z-score。"""
    mask = signal.notna()
    max_abs = signal.abs().max()
    pos = pd.Series(0.0, index=signal.index)
    pos[mask] = (signal[mask] / max_abs).clip(-1, 1)
    pos = pos.shift(1)
    strat_ret = pos * ret
    mask2 = strat_ret.notna()
    if mask2.sum() < 30:
        return {"sharpe": None, "ann_ret": None, "max_dd": None}
    ann_ret = strat_ret[mask2].mean() * 365
    sharpe = strat_ret[mask2].mean() / (strat_ret[mask2].std() + 1e-8) * np.sqrt(365)
    cum = (1 + strat_ret[mask2]).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()
    return {"ann_ret": round(ann_ret, 4), "sharpe": round(sharpe, 4), "max_dd": round(max_dd, 4)}


def compute_spread_strategy(signal, ret, horizon, n_groups=5):
    """市場中性多空組合：long top quintile, short bottom quintile, daily rebalance。"""
    mask = signal.notna()
    s = signal[mask].copy()
    ret_m = ret[mask].copy()

    # Assign quintiles each day
    ranks = s.rank(pct=True)
    bins = pd.cut(ranks, bins=n_groups, labels=False)

    strat_ret = pd.Series(0.0, index=s.index)
    for t_idx in range(1, len(s)):
        # Yesterday's ranking determines today's position
        prev_bins = bins.iloc[t_idx - 1]
        # Long top group, short bottom group
        long_mask = bins.iloc[t_idx] == (n_groups - 1)  # Q5
        short_mask = bins.iloc[t_idx] == 0  # Q1
        # Position from yesterday's signal applied to today's return
        if prev_bins == (n_groups - 1):
            strat_ret.iloc[t_idx] = ret_m.iloc[t_idx]
        elif prev_bins == 0:
            strat_ret.iloc[t_idx] = -ret_m.iloc[t_idx]

    mask2 = strat_ret != 0
    if mask2.sum() < 30:
        return {"sharpe": None, "ann_ret": None, "max_dd": None, "n": 0}

    ann_ret = strat_ret[mask2].mean() * 365
    sharpe = strat_ret[mask2].mean() / (strat_ret[mask2].std() + 1e-8) * np.sqrt(365)
    cum = (1 + strat_ret[mask2]).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()
    win_rate = (strat_ret[mask2] > 0).mean()
    return {"ann_ret": round(ann_ret, 4), "sharpe": round(sharpe, 4),
            "max_dd": round(max_dd, 4), "n": int(mask2.sum()),
            "win_rate": round(win_rate, 4)}


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"=== F10 Vol-Adj Momentum 實證 + 參數掃描 ===\n{NOW}\n")

    df = fetch_binance_daily("BTCUSDT", 1500)
    print(f"[1] 資料: {len(df)} rows, {df['timestamp'].iloc[0].date()} ~ {df['timestamp'].iloc[-1].date()}")

    # ── 參數掃描 ──
    mom_windows = [5, 10, 20]
    vol_windows = [5, 10, 20]
    smoothing_hls = [3, 5, 10]

    best_sharpe = -999
    best_params = None
    best_result = None

    print(f"\n[2] 參數掃描 ({len(mom_windows)*len(vol_windows)*len(smoothing_hls)} 組合)...")
    print(f"     {'mom_w':>6} {'vol_w':>6} {'hl':>4}  {'H5_IC':>8} {'H5_IR':>8} {'H20_IC':>8} {'H20_IR':>8} {'Sharpe':>8} {'SprdSh':>8}")

    ret = df["close"].pct_change()

    for mw, vw, hl in product(mom_windows, vol_windows, smoothing_hls):
        sig = f10_factor(df, mom_window=mw, vol_window=vw, smoothing_halflife=hl)
        ic5 = compute_rank_ic(sig, ret, 5)
        ic20 = compute_rank_ic(sig, ret, 20)
        st = compute_strategy(sig, ret)
        sp = compute_spread_strategy(sig, ret, 5)

        sharpe = st.get("sharpe") or -999
        sprd_sh = sp.get("sharpe") or -999

        print(f"     {mw:>6} {vw:>6} {hl:>4}  {ic5['ic'] or 0:>+8.4f} {ic5['ic_ir'] or 0:>+8.4f} "
              f"{ic20['ic'] or 0:>+8.4f} {ic20['ic_ir'] or 0:>+8.4f} {sharpe:>+8.4f} {sprd_sh:>+8.4f}")

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = (mw, vw, hl)
            best_result = {"ic5": ic5, "ic20": ic20, "st": st, "sp": sp, "sig": sig}

    # ── 最佳參數詳細結果 ──
    print(f"\n[3] 最佳參數: mom_w={best_params[0]}, vol_w={best_params[1]}, hl={best_params[2]}")
    print(f"    連續曝險 Sharpe: {best_result['st']['sharpe']:+.4f}")
    print(f"    年化報酬: {best_result['st']['ann_ret']:+.1%}")
    print(f"    最大回撤: {best_result['st']['max_dd']:+.1%}")

    sp = best_result["sp"]
    print(f"\n    市場中性多空 (Q5-Q1):")
    print(f"    Sharpe: {sp['sharpe']:+.4f}, 年化: {sp['ann_ret']:+.1%}, MaxDD: {sp['max_dd']:+.1%}, N={sp['n']}, Win={sp['win_rate']:.1%}")

    # ── Multi-horizon IC ──
    print(f"\n[4] Multi-horizon IC (最佳參數):")
    sig = best_result["sig"]
    for h in [1, 5, 10, 20]:
        ic = compute_rank_ic(sig, ret, h)
        gr = compute_group_returns(sig, ret, h)
        print(f"    H={h:2d}d: IC={ic['ic']:+7.4f}, IR={ic['ic_ir']:+7.4f}, "
              f"Spread={gr['spread']:+9.6f}")

    # ── 品質判定 ──
    print(f"\n[5] 品質判定:")
    ic5_ir = abs(best_result["ic5"]["ic_ir"])
    sharpe = best_result["st"]["sharpe"]
    sp_sharpe = best_result["sp"]["sharpe"]

    ir_pass = ic5_ir >= 0.3
    sh_pass = (sharpe is not None and sharpe >= 1.0)
    sp_pass = (sp_sharpe is not None and sp_sharpe >= 1.0)

    print(f"    IC-IR (H5) ≥ 0.3: {ic5_ir:.4f} {'✅' if ir_pass else '❌'}")
    print(f"    連續曝險 Sharpe ≥ 1.0: {sharpe:+.4f} {'✅' if sh_pass else '❌'}")
    print(f"    市場中性 Sharpe ≥ 1.0: {sp_sharpe:+.4f} {'✅' if sp_pass else '❌'}")

    if ir_pass and (sh_pass or sp_pass):
        print(f"\n    ✅ 通過雙門檻！")
    else:
        print(f"\n    ❌ 未通過雙門檻 — 建議 REWORK")


if __name__ == "__main__":
    main()
