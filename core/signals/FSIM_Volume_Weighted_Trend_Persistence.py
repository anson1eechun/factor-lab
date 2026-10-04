"""
F21: Volume-Weighted Trend Persistence (VWTP)
---------------------------------------------
Hypothesis:
    Momentum that is confirmed by relative volume persists. When daily
    returns repeatedly share the same sign AND those moves arrive on
    above-average volume, directional conviction is real and tends to
    continue. The factor measures the net signed, volume-weighted return
    over a window relative to the total volume-weighted magnitude, giving
    a bounded persistence score. Expected positive IC.

Formula:
    r_t       = ln(C_t / C_{t-1})
    sign_t    = sign(r_t)
    vrel_t    = V_t / SMA(V, N)                 # N=window=20
    contrib_t = sign_t * |r_t| * vrel_t
    num_t     = rolling_sum(contrib, N)
    den_t     = rolling_sum(|r| * vrel, N) + eps   # eps=1e-12
    vwtp_t    = num_t / den_t                    # bounded [-1, +1]
    z_t       = rolling_zscore(vwtp_t, 90); z_t = clip(z_t, -3, 3)
    sig_t     = EMA(z_t, halflife=3)
    signal    = sig_t.shift(1)                   # anti look-ahead

Notes:
    - vwtp is bounded in [-1, +1] because |num| <= sum(|r|*vrel) <= den.
    - eps protects against zero-volatility / zero-volume windows.

Anti look-ahead:
    All rolling stats (SMA, sums, zscore) and the EMA use only data
    through t; the final signal is shifted by 1 bar before being returned.
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
    window: int = 20,
    z_window: int = 90,
    ema_halflife: int = 3,
    eps: float = 1e-12,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    c = df["close"].astype(float)
    v = df["volume"].astype(float)

    r = np.log(c / c.shift(1))
    sign = np.sign(r)
    abs_r = r.abs()

    sma_v = v.rolling(window, min_periods=window).mean()
    vrel = v / sma_v

    contrib = sign * abs_r * vrel
    weighted_mag = abs_r * vrel

    num = contrib.rolling(window, min_periods=window).sum()
    den = weighted_mag.rolling(window, min_periods=window).sum() + eps

    vwtp = num / den

    z = _rolling_zscore(vwtp, z_window).clip(-3.0, 3.0)

    sig = z.ewm(halflife=ema_halflife, adjust=False).mean()

    signal = sig.shift(1)
    signal.name = "FSIM_volume_weighted_trend_persistence"
    return signal.reindex(ohlcv_df.index)
