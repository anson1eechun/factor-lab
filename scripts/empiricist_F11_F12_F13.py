#!/usr/bin/env python3
"""
Phase 2: F11/F12/F13 Batch Backtest
Rank-IC + IC-IR + 分組回報 + 市場中性多空策略
BTC/USDT 日線, Binance 公開 API
"""
import sys
sys.path.insert(0, "/home/anson/factor-lab")

import pandas as pd
import numpy as np
from itertools import product
from core.adapters.crypto import CryptoAdapter
from core.signals.F11_volatility_compression_indicator import factor as f11_factor
from core.signals.F12_bayesian_drift_uncertainty_signal import factor as f12_factor
from core.signals.F13_tail_event_asymmetry_ratio import factor as f13_factor

# ── Config ──
HORIZONS = [1, 5, 10, 20]
IC_IR_THRESHOLD = 0.3
IC_MIN = 0.02
SHARPE_THRESHOLD = 1.0
FEE = 0.0009

# ── Data ──
print("Fetching BTC/USDT daily data...")
adapter = CryptoAdapter()
df = adapter.get_ohlcv("BTC/USDT", "1d", limit=1500)
if df.empty:
    print("ERROR: No data fetched")
    sys.exit(1)
ret = df["close"].pct_change().astype(float)
print(f"Data: {len(df)} rows")
print(f"First: {df.index[0]}, Last: {df.index[-1]}\n")


def compute_rolling_ic(signal, returns, horizon, roll_window=60):
    """Compute rolling Rank IC series for IC-IR estimation"""
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < roll_window:
        return None

    ic_series = pd.Series(np.nan, index=s.index)
    for i in range(roll_window - 1, len(s) - horizon):
        win_s = s.iloc[i - roll_window + 1:i + 1]
        win_fr = fr.iloc[i - roll_window + 1:i + 1]
        ic_series.iloc[i] = win_s.rank().corr(win_fr.rank(), method="pearson")

    return ic_series.dropna()


def compute_group_returns(signal, returns, horizon, n_groups=5):
    """Quantile group forward returns"""
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 50:
        return None, np.nan
    labels = pd.qcut(s, n_groups, labels=False, duplicates="drop")
    if labels.nunique() < 2:
        return None, np.nan
    groups = fr.groupby(labels).mean()
    spread = groups.iloc[-1] - groups.iloc[0]
    return groups, spread


def market_neutral_sharpe(signal, returns, horizon):
    """Q5-Q1 spread strategy Sharpe"""
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 100:
        return np.nan

    try:
        labels = pd.qcut(s, 5, labels=False, duplicates="drop")
    except ValueError:
        return np.nan

    if labels.nunique() < 2:
        return np.nan

    long_sig = labels == labels.max()
    short_sig = labels == labels.min()
    strat_ret = fr[long_sig].mean() - fr[short_sig].mean()
    strat_std = (fr[long_sig] - fr[short_sig].mean()).std()
    # Not quite right for spread — use daily returns
    if strat_std == 0:
        return np.nan

    # Approximate: Q5 return - Q1 return at each horizon
    q5_ret = fr[long_sig]
    q1_ret = fr[short_sig]
    # Align by index
    common_idx = q5_ret.index.intersection(q1_ret.index)
    if len(common_idx) < 30:
        return np.nan
    spread_ret = q5_ret[common_idx] - q1_ret[common_idx]
    s = spread_ret.mean() / spread_ret.std() * np.sqrt(365 / horizon) if spread_ret.std() > 0 else 0
    return s


def full_evaluation(factor_fn, name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    base_sig = factor_fn(df)
    if base_sig.isna().all():
        print("  FAIL: All NaN")
        return None

    print(f"  Valid obs: {base_sig.notna().sum()}/{len(base_sig)}")

    # ── Multi-horizon IC ──
    print(f"\n{'H':>6} {'IC':>8} {'IC-IR':>8} {'Q5-Q1':>10} {'SprdSh':>9}")
    print("-" * 48)
    results = {}
    best_ic_ir = -999
    best_h = None

    for h in HORIZONS:
        rolling_ic = compute_rolling_ic(base_sig, ret, h)
        if rolling_ic is None or len(rolling_ic) < 30:
            print(f"{h:>6} {'no_data':>8}")
            continue

        mean_ic = rolling_ic.mean()
        ic_ir = mean_ic / rolling_ic.std() if rolling_ic.std() > 0 else 0
        _, spread = compute_group_returns(base_sig, ret, h)
        sp_sh = market_neutral_sharpe(base_sig, ret, h)

        sp_str = f"{spread:+.6f}" if not np.isnan(spread) else "NaN"
        sh_str = f"{sp_sh:+.4f}" if not np.isnan(sp_sh) else "NaN"
        print(f"{h:>6} {mean_ic:>+8.4f} {ic_ir:>+8.4f} {sp_str:>10} {sh_str:>9}")

        results[h] = {"ic": mean_ic, "ic_ir": ic_ir, "spread": spread, "spread_sh": sp_sh}
        if ic_ir > best_ic_ir:
            best_ic_ir = ic_ir
            best_h = h

    if not results:
        return None

    # ── Quality Gates (H5) ──
    h5 = results.get(5, {})
    h5_ic = h5.get("ic", np.nan)
    h5_ir = h5.get("ic_ir", np.nan)
    h5_sp_sh = h5.get("spread_sh", np.nan)

    gates = [
        ("|Rank-IC| ≥ 0.02", abs(h5_ic) if not np.isnan(h5_ic) else 0, IC_MIN),
        ("IC-IR ≥ 0.3", h5_ir if not np.isnan(h5_ir) else 0, IC_IR_THRESHOLD),
        ("Spread Sharpe ≥ 1.0", h5_sp_sh if not np.isnan(h5_sp_sh) else 0, SHARPE_THRESHOLD),
    ]

    print(f"\n  Quality Gates (H5):")
    all_pass = True
    for gname, val, thr in gates:
        ok = val >= thr
        mark = "✅" if ok else "❌"
        print(f"    {mark} {gname}: {val:.4f} vs {thr}")
        if not ok:
            all_pass = False

    return {
        "name": name,
        "results": results,
        "all_pass": all_pass,
        "best_ic_ir": best_ic_ir,
        "best_h": best_h,
    }


# ── Run ──
all_eval = []

for fac_fn, fac_name in [
    (f11_factor, "F11: Volatility Compression Indicator"),
    (f12_factor, "F12: Bayesian Drift Uncertainty Signal"),
    (f13_factor, "F13: Tail-Event Asymmetry Ratio"),
]:
    result = full_evaluation(fac_fn, fac_name)
    if result:
        all_eval.append(result)

# ── Summary ──
print(f"\n{'='*60}")
print(f"  PHASE 2 SUMMARY")
print(f"{'='*60}")
for r in all_eval:
    status = "✅ PASS" if r["all_pass"] else "❌ FAIL"
    print(f"  {status}  {r['name']}  (best IC-IR={r['best_ic_ir']:.4f} at H={r['best_h']})")

pass_count = sum(1 for r in all_eval if r["all_pass"])
print(f"\n  Passed: {pass_count}/{len(all_eval)}")
