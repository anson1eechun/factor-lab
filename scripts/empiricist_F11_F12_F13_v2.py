#!/usr/bin/env python3
"""
Phase 2 v2: F11/F12/F13 Backtest — fixed spread sharpe + sign flip
"""
import sys
sys.path.insert(0, "/home/anson/factor-lab")

import pandas as pd
import numpy as np
from core.adapters.crypto import CryptoAdapter
from core.signals.F11_volatility_compression_indicator import factor as f11_factor
from core.signals.F12_bayesian_drift_uncertainty_signal import factor as f12_factor
from core.signals.F13_tail_event_asymmetry_ratio import factor as f13_factor

HORIZONS = [1, 5, 10, 20]
IC_IR_THRESHOLD = 0.3
IC_MIN = 0.02
SHARPE_THRESHOLD = 1.0

# ── Data ──
print("Fetching BTC/USDT daily data...")
adapter = CryptoAdapter()
df = adapter.get_ohlcv("BTC/USDT", "1d", limit=1500)
ret = df["close"].pct_change().astype(float)
print(f"Data: {len(df)} rows\n")


def compute_rolling_ic(signal, returns, horizon, roll_window=60):
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
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 50:
        return None, np.nan
    try:
        labels = pd.qcut(s, n_groups, labels=False, duplicates="drop")
    except ValueError:
        return None, np.nan
    if labels.nunique() < 2:
        return None, np.nan
    groups = fr.groupby(labels).mean()
    spread = groups.iloc[-1] - groups.iloc[0]
    return groups, spread


def spread_sharpe(signal, returns, horizon):
    """Q5-Q1 spread strategy Sharpe (daily rebalance approximation)"""
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

    q5_idx = labels == labels.max()
    q1_idx = labels == labels.min()

    # The daily-forward return of Q5 long / Q1 short
    # Each horizon we long Q5 and short Q1, hold for h days
    q5_ret = fr[q5_idx]
    q1_ret = fr[q1_idx]

    # Align by timestamp (same bucket) — use index intersection
    common = q5_ret.index.intersection(q1_ret.index)
    if len(common) < 30:
        return np.nan

    spread_ret = q5_ret[common] - q1_ret[common]
    mu = spread_ret.mean()
    sigma = spread_ret.std()
    if sigma == 0:
        return np.nan
    return mu / sigma * np.sqrt(365 / horizon)


def full_evaluation(factor_fn, name, negate=False):
    print(f"\n{'='*60}")
    neg_label = " (NEGATED)" if negate else ""
    print(f"  {name}{neg_label}")
    print(f"{'='*60}")

    base_sig = factor_fn(df)
    if negate:
        base_sig = -base_sig
    if base_sig.isna().all():
        print("  FAIL: All NaN")
        return None

    valid = base_sig.notna().sum()
    print(f"  Valid obs: {valid}/{len(base_sig)}")

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
        sp_sh = spread_sharpe(base_sig, ret, h)

        sp_str = f"{spread:+.6f}" if not np.isnan(spread) else "NaN"
        sh_str = f"{sp_sh:+.4f}" if not np.isnan(sp_sh) else "NaN"
        print(f"{h:>6} {mean_ic:>+8.4f} {ic_ir:>+8.4f} {sp_str:>10} {sh_str:>9}")

        results[h] = {"ic": mean_ic, "ic_ir": ic_ir, "spread": spread, "spread_sh": sp_sh}
        if ic_ir > best_ic_ir:
            best_ic_ir = ic_ir
            best_h = h

    if not results:
        return None

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

    return {"name": name + neg_label, "results": results, "all_pass": all_pass,
            "best_ic_ir": best_ic_ir, "best_h": best_h, "negated": negate}


# ── Run: original + negated for each ──
all_eval = []

# F11: only original (IC is already positive, just needs param tuning)
r = full_evaluation(f11_factor, "F11: Volatility Compression Indicator")
if r: all_eval.append(r)

# F12: BDUS — original (negative IC) + negated (positive IC)
r = full_evaluation(f12_factor, "F12: Bayesian Drift Uncertainty Signal")
if r: all_eval.append(r)
r = full_evaluation(f12_factor, "F12: Bayesian Drift Uncertainty Signal", negate=True)
if r: all_eval.append(r)

# F13: TEAR — original + negated
r = full_evaluation(f13_factor, "F13: Tail-Event Asymmetry Ratio")
if r: all_eval.append(r)
r = full_evaluation(f13_factor, "F13: Tail-Event Asymmetry Ratio", negate=True)
if r: all_eval.append(r)

# ── Summary ──
print(f"\n{'='*60}")
print(f"  PHASE 2 SUMMARY")
print(f"{'='*60}")
for r in all_eval:
    status = "✅ PASS" if r["all_pass"] else "❌ FAIL"
    print(f"  {status}  {r['name']}  (best IC-IR={r['best_ic_ir']:.4f} at H={r['best_h']})")

pass_count = sum(1 for r in all_eval if r["all_pass"])
print(f"\n  Passed: {pass_count}/{len(all_eval)}")
