"""Compute IC-IR for F17 TFI factor across multiple forward horizons."""
import sys
sys.path.insert(0, "/home/anson/factor-lab/core")

import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from signals.F17_trade_flow_imbalance import factor as f17_factor
from adapters.crypto import CryptoAdapter

# Load long history
adapter = CryptoAdapter()
df = adapter.get_ohlcv("BTCUSDT", timeframe="1d", limit=1000)
print(f"OHLCV: {len(df)} rows, "
      f"{pd.to_datetime(df['timestamp'], unit='ms').iloc[0].strftime('%Y-%m-%d')} to "
      f"{pd.to_datetime(df['timestamp'], unit='ms').iloc[-1].strftime('%Y-%m-%d')}")

# Compute signal (OHLCV proxy)
signal = f17_factor(df, tfi_source="ohlcv")
print(f"Signal: {len(signal)} values, {signal.isna().sum()} NaN\n")

close = df["close"].astype(float)

# IC-IR across horizons
print(f"{'Horizon':<10} {'N':>5} {'Rank IC':>10} {'p-val':>8} {'t-stat':>8} {'RollIC':>10} {'RollStd':>10} {'IR':>6}")
print("-" * 75)

for horizon in [1, 3, 5, 10, 20]:
    fwd_ret = close.shift(-horizon) / close - 1
    mask = signal.notna() & fwd_ret.notna()
    s = signal[mask].values
    r = fwd_ret[mask].values
    n = len(s)

    if n < 20:
        continue

    ic, ic_pval = spearmanr(s, r)
    t_stat = ic * np.sqrt(n - 2) / np.sqrt(max(1e-10, 1 - ic**2))

    # Rolling 60-day IC
    roll_n = 60
    roll_ics = []
    for i in range(roll_n, n):
        ic_w, _ = spearmanr(s[i - roll_n:i], r[i - roll_n:i])
        roll_ics.append(ic_w)

    if roll_ics:
        roll_ic_mean = np.mean(roll_ics)
        roll_ic_std = np.std(roll_ics)
        roll_ir = roll_ic_mean / roll_ic_std if roll_ic_std > 0 else 0
    else:
        roll_ic_mean = roll_ic_std = roll_ir = 0

    print(f"h={horizon:2d}d     {n:>5} {ic:>+10.4f} {ic_pval:>8.4f} {t_stat:>+8.2f} "
          f"{roll_ic_mean:>+10.4f} {roll_ic_std:>10.4f} {roll_ir:>6.2f}")

# Directional accuracy
print()
print("Directional accuracy (signal sign == return sign):")
for horizon in [1, 3, 5, 10, 20]:
    fwd_ret = close.shift(-horizon) / close - 1
    mask = signal.notna() & fwd_ret.notna()
    s = signal[mask]
    r = fwd_ret[mask]
    hit = (np.sign(s) == np.sign(r)).sum()
    total = len(s)
    print(f"  h={horizon:2d}d: {hit}/{total} = {hit / total * 100:.1f}%")

# Compare with F8 and F10 for context
print()
print("--- Comparison baseline: F10 (Vol-Adj Momentum) ---")
try:
    from signals.F10_vol_adj_momentum import factor as f10_factor
    signal_f10 = f10_factor(df)
    for horizon in [1, 5, 10, 20]:
        fwd_ret = close.shift(-horizon) / close - 1
        mask = signal_f10.notna() & fwd_ret.notna()
        s = signal_f10[mask].values
        r = fwd_ret[mask].values
        n = len(s)
        if n >= 20:
            ic, pval = spearmanr(s, r)
            print(f"  F10 h={horizon:2d}d: IC={ic:+.4f}, p={pval:.4f}, N={n}")
except Exception as e:
    print(f"  F10 comparison failed: {e}")
