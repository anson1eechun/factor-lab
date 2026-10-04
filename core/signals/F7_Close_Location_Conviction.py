"""
F7: Close-Location Conviction (CLC)
-----------------------------------
Formula:
    CLV_t      = ((C_t - L_t) - (H_t - C_t)) / (H_t - L_t)   in [-1, +1]
    vol_z_t    = rolling_zscore( log(volume+1), window=60 )
    conviction = CLV_t * vol_z_t
    smoothed   = EMA(conviction, halflife=8)
    signal     = rolling_zscore(smoothed, 60)

Edge cases:
    - H_t == L_t (doji): CLV = 0
    - volume == 0: log(0+1) = 0

Anti look-ahead:
    Rolling statistics use only data up to t; signal is shifted by 1 to be
    applied to next-bar return.
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
    vol_window: int = 60,
    ema_halflife: int = 8,
    z_window: int = 60,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)

    # 1) Symmetric CLV in [-1, +1], 0 when H == L
    rng = h - l
    clv = ((c - l) - (h - c)) / rng.replace(0, np.nan)
    clv = clv.where(rng > 1e-12, 0.0)
    clv = clv.clip(-1.0, 1.0)

    # 2) Volume z-score (log-scaled, 60d window)
    log_vol = np.log(v.clip(lower=0) + 1.0)
    vol_z = _rolling_zscore(log_vol, vol_window)

    # 3) Conviction = CLV * vol_z (bounded × unbounded = unbounded)
    conviction = clv * vol_z

    # 4) EMA smoothing
    smoothed = conviction.ewm(halflife=ema_halflife, adjust=False).mean()

    # 5) Rolling 60d z-score
    signal = _rolling_zscore(smoothed, z_window)

    # Warm-up: vol_z needs vol_window; smoothing needs ~2*halflife; z needs z_window
    warmup = vol_window + z_window + 2 * ema_halflife
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    # Anti look-ahead alignment
    signal = signal.shift(1)
    signal.name = "F7_close_location_conviction"
    return signal.reindex(ohlcv_df.index)
