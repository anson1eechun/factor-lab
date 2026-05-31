#!/usr/bin/env python3
"""
Phase 2 v3: F11/F12/F13 Backtest — fixed spread sharpe + summary
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


def compute_spread_strategy(signal, returns, horizon, n_groups=5):
    """
    Q5-Q1 spread strategy: long top quintile, short bottom quintile.
    Rebalance daily, hold for 'horizon' days.
    Returns (annualized_sharpe, annualized_return, n_rebalances)
    """
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 100:
        return np.nan, np.nan, 0
    try:
        labels = pd.qcut(s, n_groups, labels=False, duplicates="drop")
    except ValueError:
        return np.nan, np.nan, 0
    if labels.nunique() < 2:
        return np.nan, np.nan, 0

    # Each row is one rebalance: long Q5, short Q1
    q5_mask = labels == labels.max()
    q1_mask = labels == labels.min()

    # For each day, compute the Q5-Q1 spread return that realized
    # We construct a position-weighted return series:
    # position = +1 for Q5 days, -1 for Q1 days, 0 otherwise
    position = pd.Series(0.0, index=s.index)
    position[q5_mask] = 1.0 / q5_mask.sum()
    position[q1_mask] = -1.0 / q1_mask.sum()

    # Equal-weight the signals: normalize so total long = total short
    long_sum = position[position > 0].sum()
    short_sum = -position[position < 0].sum()
    if long_sum > 0 and short_sum > 0:
        position[position > 0] /= long_sum
        position[position < 0] /= abs(short_sum)

    # Daily return = position * forward return
    daily_ret = (position.values * fr.values)

    mu = daily_ret.mean()
    sigma = daily_ret.std()
    if sigma == 0:
        return np.nan, np.nan, (q5_mask.sum() + q1_mask.sum())

    sharpe = mu / sigma * np.sqrt(365)
    ann_ret = mu * 365
    n_trades = q5_mask.sum() + q1_mask.sum()
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

    print(f"\n{'H':>6} {'IC':>8} {'IC-IR':>8} {'Q5-Q1':>10} {'SprdSh':>9} {'AnnRet':>9}")
    print("-" * 58)
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
        sp_sh, ann_ret, n_tr = compute_spread_strategy(base_sig, ret, h)

        sh_str = f"{sp_sh:+.4f}" if not np.isnan(sp_sh) else "NaN"
        ar_str = f"{ann_ret:+.1%}" if not np.isnan(ann_ret) else "NaN"
        # Simple Q5-Q1 mean spread
        m = base_sig.notna()
        fwd = ret.shift(-h)
        m &= fwd.notna()
        s2, fr2 = base_sig[m], fwd[m]
        try:
            labels2 = pd.qcut(s2, 5, labels=False, duplicates="drop")
            grp = fr2.groupby(labels2).mean()
            spread_val = grp.iloc[-1] - grp.iloc[0] if len(grp) >= 2 else np.nan
        except:
            spread_val = np.nan
        sp_str = f"{spread_val:+.6f}" if not np.isnan(spread_val) else "NaN"

        print(f"{h:>6} {mean_ic:>+8.4f} {ic_ir:>+8.4f} {sp_str:>10} {sh_str:>9} {ar_str:>9}")

        results[h] = {"ic": mean_ic, "ic_ir": ic_ir, "spread": spread_val,
                       "spread_sh": sp_sh, "ann_ret": ann_ret}
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


# ── Run ──
all_eval = []

# F11
r = full_evaluation(f11_factor, "F11: VCI")
if r: all_eval.append(r)

# F12 original + negated
r = full_evaluation(f12_factor, "F12: BDUS")
if r: all_eval.append(r)
r = full_evaluation(f12_factor, "F12: BDUS", negate=True)
if r: all_eval.append(r)

# F13 original + negated
r = full_evaluation(f13_factor, "F13: TEAR")
if r: all_eval.append(r)
r = full_evaluation(f13_factor, "F13: TEAR", negate=True)
if r: all_eval.append(r)

# ── Summary ──
print(f"\n{'='*60}")
print(f"  PHASE 2 SUMMARY")
print(f"{'='*60}")
for r in all_eval:
    status = "✅ PASS" if r["all_pass"] else "❌ FAIL"
    h5 = r["results"].get(5, {})
    print(f"  {status}  {r['name']}")
    print(f"         IC-IR={r['best_ic_ir']:.4f}@H={r['best_h']}  "
          f"H5: IC={h5.get('ic',np.nan):+.4f} IR={h5.get('ic_ir',np.nan):+.4f} "
          f"SpSh={h5.get('spread_sh',np.nan):+.2f}")

pass_count = sum(1 for r in all_eval if r["all_pass"])
print(f"\n  Passed: {pass_count}/{len(all_eval)}")
