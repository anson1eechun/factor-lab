"""IC-IR: Real TFI (cached aggTrades) vs OHLCV Proxy — same date range comparison."""
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from pathlib import Path
import sys
sys.path.insert(0, "/home/anson/factor-lab/core")

from adapters.crypto import CryptoAdapter

# 1. Load cached real TFI
cache_file = Path("/home/anson/factor-lab/data/aggTrades/daily_tfi.parquet")
cached = pd.read_parquet(cache_file)
cached = cached.set_index("date").sort_index()
print(f"Real TFI cache: {len(cached)} days, "
      f"{cached.index[0].strftime('%Y-%m-%d')} to {cached.index[-1].strftime('%Y-%m-%d')}")
print(f"  TFI raw: mean={cached['tfi_raw'].mean():+.5f}, std={cached['tfi_raw'].std():.5f}")
print(f"  Daily volume: mean={cached['total_vol'].mean()/1e3:.0f}K BTC, "
      f"median={cached['total_vol'].median()/1e3:.0f}K BTC")
buy_ratio = cached['buy_vol'].sum() / cached['total_vol'].sum() * 100
print(f"  Buy ratio: mean={buy_ratio:.1f} pct")

# 2. Load matching OHLCV
adapter = CryptoAdapter()
df = adapter.get_ohlcv("BTCUSDT", timeframe="1d", limit=200)
dates = pd.to_datetime(df["timestamp"], unit="ms")

# Compute OHLCV proxy TFI
high, low, close_arr = df["high"], df["low"], df["close"]
hl_range = high - low
clv = pd.Series(0.5, index=range(len(df)))
mask = hl_range > 0
clv[mask] = (close_arr[mask] - low[mask]) / hl_range[mask]
proxy_tfi = 2.0 * clv - 1.0

# 3. Align: match dates between cache and OHLCV
close_series = pd.Series(close_arr.values, index=dates)
proxy_series = pd.Series(proxy_tfi.values, index=dates)

aligned = []
for idx in cached.index:
    if idx in close_series.index:
        aligned.append({
            "date": idx,
            "real_tfi": cached.loc[idx, "tfi_raw"],
            "proxy_tfi": proxy_series.loc[idx],
            "close": close_series.loc[idx],
        })

aligned_df = pd.DataFrame(aligned).set_index("date")
print(f"\nAligned days: {len(aligned_df)}")

# 4. Correlation between real TFI and proxy TFI
corr = spearmanr(aligned_df["real_tfi"], aligned_df["proxy_tfi"])
print(f"Spearman rho (real vs proxy): {corr.statistic:+.4f} (p={corr.pvalue:.4f})")

# 5. IC-IR: real TFI vs forward returns
def print_icir(label, tfi_series, close_series):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(f"{'Horizon':<10} {'N':>5} {'Rank IC':>10} {'p-val':>8} {'t-stat':>8}")
    print("-" * 50)

    for horizon in [1, 3, 5, 10, 20]:
        fwd_ret = close_series.shift(-horizon) / close_series - 1
        mask = tfi_series.notna() & fwd_ret.notna()
        s = tfi_series[mask].values
        r = fwd_ret[mask].values
        n = len(s)
        if n < 10:
            continue
        ic, pval = spearmanr(s, r)
        t_stat = ic * np.sqrt(max(n-2, 1)) / np.sqrt(max(1-ic*ic, 1e-10))
        print(f"h={horizon:2d}d     {n:>5} {ic:>+10.4f} {pval:>8.4f} {t_stat:>+8.2f}")

print_icir("IC-IR: REAL TFI (from aggTrades)", aligned_df["real_tfi"], aligned_df["close"])
print_icir("IC-IR: OHLCV PROXY TFI (same period)", aligned_df["proxy_tfi"], aligned_df["close"])

# 6. Z-scored TFI (real) - forward-look protection
print(f"\n{'='*70}")
print(f"  IC-IR: Z-SCORED REAL TFI (60d rolling, shift(1))")
print(f"{'='*70}")
print(f"{'Horizon':<10} {'N':>5} {'Rank IC':>10} {'p-val':>8} {'t-stat':>8}")
print("-" * 50)
roll_mean = aligned_df["real_tfi"].shift(1).rolling(60, min_periods=10).mean()
roll_std = aligned_df["real_tfi"].shift(1).rolling(60, min_periods=10).std()
z_tfi = (aligned_df["real_tfi"] - roll_mean) / roll_std.replace(0, np.nan)
z_tfi = z_tfi.clip(-4, 4)

for horizon in [1, 3, 5, 10, 20]:
    fwd_ret = aligned_df["close"].shift(-horizon) / aligned_df["close"] - 1
    mask = z_tfi.notna() & fwd_ret.notna()
    s = z_tfi[mask].values
    r = fwd_ret[mask].values
    n = len(s)
    if n < 10:
        continue
    ic, pval = spearmanr(s, r)
    t_stat = ic * np.sqrt(max(n-2, 1)) / np.sqrt(max(1-ic*ic, 1e-10))
    print(f"h={horizon:2d}d     {n:>5} {ic:>+10.4f} {pval:>8.4f} {t_stat:>+8.2f}")

# 7. Lagged TFI (t-1) vs same-day return — contemporaneous check
print()
same_ret = aligned_df["close"] / aligned_df["close"].shift(1) - 1
mask = aligned_df["real_tfi"].notna() & same_ret.notna()
lag_tfi = aligned_df["real_tfi"].shift(1)
mask = mask & lag_tfi.notna()
ic, pval = spearmanr(lag_tfi[mask].values, same_ret[mask].values)
print(f"Lag-1 TFI vs same-day return: IC={ic:+.4f} (p={pval:.4f}) — contemporaneous check")
