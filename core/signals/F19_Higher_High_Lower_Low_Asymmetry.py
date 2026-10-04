"""
F19: Higher-High Lower-Low Asymmetry (HHLA)
-------------------------------------------
Category: Price-Structure / Breakout Asymmetry
Source: candidates/F19_Higher_High_Lower_Low_Asymmetry.md

Formula:
    HH_t        = sum over i in [t-N+1, t] of  I( High_i > max(High_{i-K..i-1}) )
    LL_t        = sum over i in [t-N+1, t] of  I( Low_i  < min(Low_{i-K..i-1})  )
    HHLA_t      = log( (HH_t + 1) / (LL_t + 1) )
    signal_t    = rolling_zscore(HHLA_t, z_window=90)
    signal_t    = clip(signal_t, ±3)

Parameters:
    N = 20  (event-count window)
    K = 5   (look-back for prior-bar high/low comparison)
    Note: N > K. The K-bar window is used PER BAR to decide whether that bar
    breaks above/below the prior K highs/lows; then we count such events over N.

Hypothesis:
    Asymmetric directional breakouts (more new highs than new lows over a
    20-day window) reveal directional pressure that persists beyond noise.

Anti look-ahead:
    The per-bar breakout test compares High_i with max(High_{i-K..i-1}) —
    strictly prior K bars — using .shift(1).rolling(K).  All rolling stats
    use only data through t. Final signal is additionally shifted by 1.
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
    N: int = 20,
    K: int = 5,
    z_window: int = 90,
    clip_z: float = 3.0,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    h = df["high"].astype(float)
    l = df["low"].astype(float)

    # Guard against non-positive prices
    safe = (h > 0) & (l > 0)
    h = h.where(safe)
    l = l.where(safe)

    # Prior-K-bar reference: shift(1) so bar i is compared to bars i-K..i-1
    prior_max_high = h.shift(1).rolling(K, min_periods=K).max()
    prior_min_low = l.shift(1).rolling(K, min_periods=K).min()

    # Per-bar breakout indicators (NaN-safe: where reference is NaN, drop)
    is_hh = (h > prior_max_high).astype(float)
    is_ll = (l < prior_min_low).astype(float)

    # Mask out bars where the prior-K window is incomplete
    is_hh = is_hh.where(prior_max_high.notna())
    is_ll = is_ll.where(prior_min_low.notna())

    # Count events over the past N bars
    HH = is_hh.rolling(N, min_periods=N).sum()
    LL = is_ll.rolling(N, min_periods=N).sum()

    # Log-asymmetry
    hhla = np.log((HH + 1.0) / (LL + 1.0))

    # Rolling z-score
    signal = _rolling_zscore(hhla, z_window)

    # Clip
    if clip_z is not None and clip_z > 0:
        signal = signal.clip(lower=-clip_z, upper=clip_z)

    # Warm-up mask: need K (prior) + N (event window) + z_window
    warmup = K + N + z_window
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    # Anti look-ahead shift
    signal = signal.shift(1)

    signal.name = "F19_higher_high_lower_low_asymmetry"
    return signal.reindex(ohlcv_df.index)
