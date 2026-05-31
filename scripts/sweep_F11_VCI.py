#!/usr/bin/env python3
"""
F11 VCI Parameter Sweep
Grid: short_window × long_window × smoothing_halflife
Goal: find params that push IC-IR past 0.3 threshold.
"""
import sys
sys.path.insert(0, "/home/anson/factor-lab")

import pandas as pd
import numpy as np
from itertools import product
from core.adapters.crypto import CryptoAdapter
from core.signals.F11_volatility_compression_indicator import factor as f11_factor

HORIZONS = [1, 5, 10, 20]
IC_IR_THRESHOLD = 0.3
IC_MIN = 0.02

# ── Param grid ──
SHORT_WINDOWS = [3, 5, 7, 10, 15]
LONG_WINDOWS  = [15, 20, 30, 40, 60]
HL_VALUES     = [2, 3, 5, 10]

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


def quintile_monotonicity(signal, returns, horizon):
    """Spearman corr between quintile rank (0-4) and mean forward return. >0 = monotonic."""
    m = signal.notna()
    fwd = returns.shift(-horizon)
    m &= fwd.notna()
    s, fr = signal[m], fwd[m]
    if len(s) < 50:
        return np.nan
    try:
        labels = pd.qcut(s, 5, labels=False, duplicates="drop")
    except ValueError:
        return np.nan
    if labels.nunique() < 3:
        return np.nan
    grouped = fr.groupby(labels).mean()
    return grouped.reset_index().corr(method="spearman").iloc[0, 1]


def long_short_strategy(signal, returns, horizon):
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

    pos = np.zeros(len(s))
    pos[labels == labels.max()] = 1.0
    pos[labels == labels.min()] = -1.0

    strat_ret = pd.Series(pos * fr.values, index=s.index)
    n_trades = (labels.diff() != 0).sum()
    mu = strat_ret.mean()
    sigma = strat_ret.std()
    if sigma == 0:
        return np.nan, mu * 365 / horizon, n_trades
    sharpe = (mu / sigma) * np.sqrt(365 / horizon)
    ann_ret = mu * (365 / horizon)
    return sharpe, ann_ret, n_trades


# ── Sweep ──
total = len(SHORT_WINDOWS) * len(LONG_WINDOWS) * len(HL_VALUES)
results = []
count = 0

for sw, lw, hl in product(SHORT_WINDOWS, LONG_WINDOWS, HL_VALUES):
    if sw >= lw:
        continue  # short window must be < long window
    count += 1

    try:
        sig = f11_factor(df, short_window=sw, long_window=lw, smoothing_halflife=hl)
    except Exception:
        continue

    valid_n = sig.notna().sum()
    if valid_n < 200:
        continue

    best_ic_ir = -999
    best_h = None
    h5_ic = np.nan
    h5_ir = np.nan
    h5_sp_sh = np.nan
    h5_ar = np.nan
    h5_tr = 0
    h5_mono = np.nan

    for h in HORIZONS:
        rolling_ic = compute_rolling_ic(sig, ret, h)
        if rolling_ic is None or len(rolling_ic) < 30:
            continue
        mean_ic = rolling_ic.mean()
        ic_ir = mean_ic / rolling_ic.std() if rolling_ic.std() > 0 else 0
        sp_sh, ann_ret_val, n_tr = long_short_strategy(sig, ret, h)

        if h == 5:
            h5_ic = mean_ic
            h5_ir = ic_ir
            h5_sp_sh = sp_sh
            h5_ar = ann_ret_val
            h5_tr = n_tr
            h5_mono = quintile_monotonicity(sig, ret, h)

        if ic_ir > best_ic_ir:
            best_ic_ir = ic_ir
            best_h = h

    results.append({
        "sw": sw, "lw": lw, "hl": hl,
        "valid": valid_n,
        "h5_ic": h5_ic, "h5_ir": h5_ir,
        "h5_sp_sh": h5_sp_sh, "h5_ar": h5_ar, "h5_tr": h5_tr,
        "h5_mono": h5_mono,
        "best_ic_ir": best_ic_ir, "best_h": best_h,
    })

print(f"Tested {len(results)} / {total} valid combinations\n")

# ── Sort by H5 IC-IR descending ──
results.sort(key=lambda x: x["h5_ir"] if not np.isnan(x["h5_ir"]) else -999, reverse=True)

print(f"{'Rank':>4} {'sw':>4} {'lw':>4} {'hl':>4} {'valid':>6} "
      f"{'H5_IC':>8} {'H5_IR':>8} {'H5_Sh':>8} {'H5_AR':>8} {'H5_Tr':>6} {'H5_Mono':>8} {'BestIR':>8} {'BestH':>6}")
print("-" * 96)

for i, r in enumerate(results[:25]):
    ir_str = f"{r['h5_ir']:+.4f}" if not np.isnan(r['h5_ir']) else "NaN"
    sh_str = f"{r['h5_sp_sh']:+.3f}" if not np.isnan(r['h5_sp_sh']) else "NaN"
    ar_str = f"{r['h5_ar']:+.1%}" if not np.isnan(r['h5_ar']) else "NaN"
    mo_str = f"{r['h5_mono']:+.3f}" if not np.isnan(r['h5_mono']) else "NaN"
    bi_str = f"{r['best_ic_ir']:+.4f}" if not np.isnan(r['best_ic_ir']) else "NaN"
    print(f"{i+1:>4} {r['sw']:>4} {r['lw']:>4} {r['hl']:>4} {r['valid']:>6} "
          f"{r['h5_ic']:>+8.4f} {ir_str:>8} {sh_str:>8} {ar_str:>8} {r['h5_tr']:>6} {mo_str:>8} {bi_str:>8} {r['best_h']:>6}")

# ── Gates summary ──
print(f"\n{'='*60}")
print("GATE SUMMARY (H5)")
print(f"{'='*60}")
passed_ic = sum(1 for r in results if not np.isnan(r["h5_ic"]) and abs(r["h5_ic"]) >= IC_MIN)
passed_ir = sum(1 for r in results if not np.isnan(r["h5_ir"]) and r["h5_ir"] >= IC_IR_THRESHOLD)
passed_both = sum(1 for r in results if not np.isnan(r["h5_ic"]) and not np.isnan(r["h5_ir"])
                  and abs(r["h5_ic"]) >= IC_MIN and r["h5_ir"] >= IC_IR_THRESHOLD)
print(f"  |IC| ≥ 0.02:     {passed_ic}/{len(results)}")
print(f"  IC-IR ≥ 0.3:     {passed_ir}/{len(results)}")
print(f"  Both gates:      {passed_both}/{len(results)}")
print(f"  Baseline (5,20,3): IR=0.238")  # from v5

# ── Best by IC-IR ──
if results:
    best = results[0]
    print(f"\n  Best (H5 IR): sw={best['sw']}, lw={best['lw']}, hl={best['hl']} "
          f"→ IR={best['h5_ir']:.4f}, IC={best['h5_ic']:+.4f}, "
          f"Sh={best['h5_sp_sh']:.3f}, Mono={best['h5_mono']:+.3f}")

# ── Quintile monotonicity top ──
results_by_mono = sorted(results, key=lambda x: x["h5_mono"] if not np.isnan(x["h5_mono"]) else -999, reverse=True)
print(f"\n{'='*60}")
print("TOP 10 BY QUINTILE MONOTONICITY")
print(f"{'='*60}")
for i, r in enumerate(results_by_mono[:10]):
    print(f"  {i+1}. sw={r['sw']:>3} lw={r['lw']:>3} hl={r['hl']:>3}  "
          f"IR={r['h5_ir']:+.4f}  Mono={r['h5_mono']:+.3f}")
