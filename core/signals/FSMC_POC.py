"""
FSMC-POC: Point of Control / Volume Profile (SMC/ICT)

Definition: The price level with the highest traded volume over a lookback window.
In ICT/SMC, the POC acts as a magnet — price tends to return to it for "rebalancing."

Mechanics:
  1. Over a rolling window (e.g. 20 bars), build a volume profile by price bucket.
  2. POC = price bucket with highest cumulative volume.
  3. Signal = normalized distance from current close to POC:
     +magnet = deviation from POC → price likely reverts toward POC
     → short-term mean-reversion signal

Signal: +1 = price below POC (expect rise), -1 = price above POC (expect fall)

Anti look-ahead: POC computed from window [t-window, t]. Signal shifted by 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _compute_poc(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                volume: np.ndarray, start: int, end: int, n_buckets: int = 20) -> float:
    """Compute POC for window [start:end]."""
    if end <= start:
        return np.nan

    price_range = high[start:end].max() - low[start:end].min()
    if price_range <= 0:
        return np.nan

    bucket_size = price_range / n_buckets
    price_min = low[start:end].min()

    # Accumulate volume in each price bucket
    vol_profile = np.zeros(n_buckets)

    for i in range(start, end):
        # Distribute candle's volume across its range (simplified: put at close)
        bucket_idx = int((close[i] - price_min) / bucket_size)
        bucket_idx = max(0, min(bucket_idx, n_buckets - 1))
        vol_profile[bucket_idx] += volume[i]

    if vol_profile.sum() == 0:
        return np.nan

    poc_bucket = np.argmax(vol_profile)
    poc_price = price_min + (poc_bucket + 0.5) * bucket_size
    return poc_price


def factor(
    ohlcv_df: pd.DataFrame,
    profile_window: int = 20,
    signal_window: int = 60,
    n_buckets: int = 20,
    **_: object,
) -> pd.Series:
    """
    Parameters
    ----------
    profile_window : int
        Bars to build the volume profile.
    signal_window : int
        Bars for z-score normalization of POC distance.
    n_buckets : int
        Number of price buckets for volume profile.
    """
    df = ohlcv_df.copy()

    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    v = df["volume"].astype(float).values
    n = len(df)

    raw_signal = np.full(n, np.nan)

    for i in range(profile_window, n):
        poc = _compute_poc(h, l, c, v, i - profile_window, i, n_buckets)
        if np.isnan(poc) or poc == 0:
            continue
        # Deviation from POC (negative = below POC → bullish)
        raw_signal[i] = (poc - c[i]) / poc  # fractional distance

    # Z-score normalize the distance signal
    signal = np.full(n, np.nan)
    for i in range(profile_window + signal_window, n):
        segment = raw_signal[i - signal_window : i + 1]
        seg = segment[~np.isnan(segment)]
        if len(seg) < signal_window // 2:
            continue
        mu = seg.mean()
        std = seg.std(ddof=1)
        if std == 0 or np.isnan(std):
            continue
        signal[i] = (raw_signal[i] - mu) / std

    result = pd.Series(signal, index=df.index)
    result = result.shift(1)
    result.name = "FSMC_POC"
    return result.reindex(ohlcv_df.index)
