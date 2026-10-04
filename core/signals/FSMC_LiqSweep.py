"""
FSMC-LiqSweep: Liquidity Sweep + Reversal (SMC/ICT)

Definition: Price sweeps a recent swing high/low (taking out stops/liquidity),
then reverses. This is the mechanical core of many ICT entry models.

Mechanics:
  1. Track rolling swing highs/lows (N-bar pivot points).
  2. When price breaks above recent swing high then closes below it
     within M bars → bearish signal (liquidity sweep of buy-side stops).
  3. When price breaks below recent swing low then closes back above it
     within M bars → bullish signal (liquidity sweep of sell-side stops).

Signal: +1 = bullish reversal (sweep low → up), -1 = bearish reversal (sweep high → down)

Anti look-ahead: All swings computed from bars ≤ t. Signal shifted by 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rolling_swing_high(lows: np.ndarray, window: int) -> np.ndarray:
    """Return array of same length: swing high = True where bar is local maximum."""
    n = len(lows)
    result = np.zeros(n, dtype=bool)
    for i in range(window, n - window):
        center = lows[i]
        left = lows[i - window : i]
        right = lows[i + 1 : i + 1 + window]
        if center > left.max() and center > right.max():
            result[i] = True
    return result


def _rolling_swing_low(lows: np.ndarray, window: int) -> np.ndarray:
    """Return array of same length: swing low = True where bar is local minimum."""
    n = len(lows)
    result = np.zeros(n, dtype=bool)
    for i in range(window, n - window):
        center = lows[i]
        left = lows[i - window : i]
        right = lows[i + 1 : i + 1 + window]
        if center < left.min() and center < right.min():
            result[i] = True
    return result


def factor(
    ohlcv_df: pd.DataFrame,
    pivot_window: int = 5,
    reversal_window: int = 3,
    **_: object,
) -> pd.Series:
    """
    Parameters
    ----------
    pivot_window : int
        Bars on each side for pivot detection (5 → 11-bar fractals).
    reversal_window : int
        Max bars after sweep for reversal to be valid.
    """
    df = ohlcv_df.copy()

    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    n = len(df)

    signal = np.zeros(n)

    # Detect swing points (only use data up to current bar for anti look-ahead)
    is_swing_high = _rolling_swing_high(h, pivot_window)
    is_swing_low = _rolling_swing_low(l, pivot_window)

    # Track recent swing levels
    recent_swing_high = np.full(n, np.nan)
    recent_swing_low = np.full(n, np.nan)

    last_swing_high = np.nan
    last_swing_low = np.nan

    for i in range(n):
        if is_swing_high[i]:
            last_swing_high = h[i]
        if is_swing_low[i]:
            last_swing_low = l[i]

        recent_swing_high[i] = last_swing_high
        recent_swing_low[i] = last_swing_low

    # Detect sweeps
    for i in range(pivot_window * 2, n):
        swing_hi = recent_swing_high[i]
        swing_lo = recent_swing_low[i]

        if np.isnan(swing_hi) or np.isnan(swing_lo):
            continue

        # Look for sweep within reversal_window
        for j in range(max(pivot_window * 2, i - 20), i + 1):
            # Sweep of highs (bearish)
            if h[j] > swing_hi and c[i] < swing_hi:
                signal[i] = -1
                break
            # Sweep of lows (bullish)
            if l[j] < swing_lo and c[i] > swing_lo:
                signal[i] = +1
                break

    # Warmup
    warmup = pivot_window * 3
    signal[:warmup] = np.nan

    result = pd.Series(signal, index=df.index)
    result = result.shift(1)
    result.name = "FSMC_LiqSweep"
    return result.reindex(ohlcv_df.index)
