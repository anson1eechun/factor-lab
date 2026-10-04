"""
F10: Wick Absorption Asymmetry (WAA)
------------------------------------
Formula:
    upper_wick_t = high_t - max(open_t, close_t)        >= 0
    lower_wick_t = min(open_t, close_t) - low_t          >= 0
    sum_up_20    = rolling_sum(upper_wick, 20)
    sum_lo_20    = rolling_sum(lower_wick, 20)
    WAA_t        = log( (sum_lo_20 + eps) / (sum_up_20 + eps) )
    signal_t     = rolling_zscore(WAA_t, 60)

Notes:
    - Per task spec we use raw wick lengths (no ATR normalisation).
    - eps = 1e-8 protects against log(0).
    - 20-day aggregation absorbs single-bar noise.

Anti look-ahead:
    Rolling stats use only data through t; final signal is shifted by 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std(ddof=1)
    return (s - mean) / std.replace(0, np.nan)


def factor(
    ohlcv_df: pd.DataFrame,
    wick_window: int = 20,
    z_window: int = 60,
    eps: float = 1e-8,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    body_high = np.maximum(o, c)
    body_low = np.minimum(o, c)

    upper_wick = (h - body_high).clip(lower=0.0)
    lower_wick = (body_low - l).clip(lower=0.0)

    sum_up = upper_wick.rolling(wick_window, min_periods=wick_window).sum()
    sum_lo = lower_wick.rolling(wick_window, min_periods=wick_window).sum()

    waa = np.log((sum_lo + eps) / (sum_up + eps))

    signal = _rolling_zscore(waa, z_window)

    warmup = wick_window + z_window
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    signal = signal.shift(1)
    signal.name = "F10_wick_absorption_asymmetry"
    return signal.reindex(ohlcv_df.index)
