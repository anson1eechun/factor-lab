#!/usr/bin/env python3
"""
Phase 2 v5: F11/F12/F13 Backtest — single-asset long-short strategy
Position: +1 when signal in Q5, -1 when signal in Q1, 0 otherwise
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


def long_short_strategy(signal, returns, horizon):
    """
    Single-asset long-short: long when top quintile, short when bottom quintile.
    Hold for 'horizon' days. Daily rebalancing implied.
    Returns (annualized_sharpe, annualized_return, n_trades)
    """
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 100:
        return np.nan, np.nan, 0

    try:
        labels = pd.qcut(s, 5, labels=False, duplicates="drop")
    except ValueError:
        return np.nan, np.nan, 0

    if labels.nunique() < 2:
        return np.nan, np.nan, 0

    # Position: +1 for Q5, -1 for Q1, 0 otherwise
    pos = np.zeros(len(s))
    pos[labels == labels.max()] = 1.0
    pos[labels == labels.min()] = -1.0

    # Strategy return = position * forward return (at horizon h)
    strat_ret = pd.Series(pos * fr.values, index=s.index)
    n_trades = (labels.diff() != 0).sum()

    mu = strat_ret.mean()
    sigma = strat_ret.std()
    if sigma == 0:
        return np.nan, mu * 365 / horizon, n_trades

    # Annualized: scale by sqrt(365/h)
    sharpe = (mu / sigma) * np.sqrt(365 / horizon)
    ann_ret = mu * (365 / horizon)
    return sharpe, ann_ret, n_trades


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

    print(f"\n{'H':>6} {'IC':>8} {'IC-IR':>8} {'SprdSh':>9} {'AnnRet':>9} {'Trades':>7}")
    print("-" * 51)
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
        sp_sh, ann_ret_val, n_tr = long_short_strategy(base_sig, ret, h)

        sh_str = f"{sp_sh:+.4f}" if not np.isnan(sp_sh) else "NaN"
        ar_str = f"{ann_ret_val:+.1%}" if not np.isnan(ann_ret_val) else "NaN"
        print(f"{h:>6} {mean_ic:>+8.4f} {ic_ir:>+8.4f} {sh_str:>9} {ar_str:>9} {n_tr:>7}")

        results[h] = {"ic": mean_ic, "ic_ir": ic_ir,
                       "spread_sh": sp_sh, "ann_ret": ann_ret_val, "trades": n_tr}
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
        ("LS Sharpe ≥ 1.0", h5_sp_sh if not np.isnan(h5_sp_sh) else 0, SHARPE_THRESHOLD),
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


# ── Run ──
all_eval = []

r = full_evaluation(f11_factor, "F11: VCI")
if r: all_eval.append(r)

r = full_evaluation(f12_factor, "F12: BDUS")
if r: all_eval.append(r)
r = full_evaluation(f12_factor, "F12: BDUS", negate=True)
if r: all_eval.append(r)

r = full_evaluation(f13_factor, "F13: TEAR")
if r: all_eval.append(r)
r = full_evaluation(f13_factor, "F13: TEAR", negate=True)
if r: all_eval.append(r)

print(f"\n{'='*60}")
print(f"  PHASE 2 SUMMARY")
print(f"{'='*60}")
for r in all_eval:
    status = "✅ PASS" if r["all_pass"] else "❌ FAIL"
    h5 = r["results"].get(5, {})
    print(f"  {status}  {r['name']}")
    print(f"         IC-IR={r['best_ic_ir']:.4f}@H={r['best_h']}  "
          f"H5: IR={h5.get('ic_ir',np.nan):+.4f} "
          f"Sh={h5.get('spread_sh',np.nan):+.2f} AR={h5.get('ann_ret',np.nan):+.1%} "
          f"Tr={h5.get('trades',0)}")

pass_count = sum(1 for r in all_eval if r["all_pass"])
print(f"\n  Passed: {pass_count}/{len(all_eval)}")
