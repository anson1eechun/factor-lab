"""
F18: Gap-Drift Reconciliation Spread (GDRS)
-------------------------------------------
Category: Microstructure / Overnight-vs-Intraday Reconciliation
Source: candidates/F18_Gap_Drift_Reconciliation_Spread.md

Formula:
    gap_t        = log( Open_t / Close_{t-1} )            # overnight component
    drift_t      = log( Close_t / Open_t )                # intraday component
    spread_t     = drift_t - gap_t                         # single-day reconciliation
    spread_t     = winsorize(spread_t, ±winsor)
    GDRS_raw_t   = rolling_sum(spread_t, N=20)
    signal_t     = rolling_zscore(GDRS_raw_t, z_window=60)
    signal_t     = clip(signal_t, ±3)

Hypothesis:
    Persistent positive spread (intraday drift exceeds overnight gap) signals
    that informed flow is being absorbed during regular hours; mean-reversion
    in the gap/drift balance gives a tradeable edge.

Anti look-ahead:
    All rolling stats use only data through t. We additionally .shift(1) the
    final signal so the value at index t reflects information available at
    close of t-1 (i.e. usable for t→t+1 trading).
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
    z_window: int = 60,
    winsor: float = 0.03,
    clip_z: float = 3.0,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    o = df["open"].astype(float)
    c = df["close"].astype(float)

    # Guard against non-positive prices
    safe = (o > 0) & (c > 0)
    o = o.where(safe)
    c = c.where(safe)

    # 1) gap and drift components
    gap = np.log(o / c.shift(1))          # uses prior close — no look-ahead
    drift = np.log(c / o)                  # within-day

    # 2) per-day reconciliation spread
    spread = drift - gap

    # 3) winsorise extreme single-day spreads (±3%)
    if winsor is not None and winsor > 0:
        spread = spread.clip(lower=-winsor, upper=winsor)

    # 4) rolling cumulation over N days
    gdrs_raw = spread.rolling(N, min_periods=N).sum()

    # 5) rolling z-score (60d)
    signal = _rolling_zscore(gdrs_raw, z_window)

    # 6) clip
    if clip_z is not None and clip_z > 0:
        signal = signal.clip(lower=-clip_z, upper=clip_z)

    # Warm-up mask
    warmup = N + z_window
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    # Anti look-ahead shift: signal_t computed at close of t applies to t+1
    signal = signal.shift(1)

    signal.name = "F18_gap_drift_reconciliation_spread"
    return signal.reindex(ohlcv_df.index)
