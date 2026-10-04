"""
FSIM: Cross-Sectional Lottery-Demand Aversion (XLOT)
----------------------------------------------------
Hypothesis:
    Coins with strong "lottery" characteristics (recent extreme single-day
    payoffs, right-skewed returns, large intraday gambling-style ranges)
    attract speculative demand, get overpriced, and subsequently underperform.
    Avoiding lottery-like coins (going long the least lottery-like) should earn
    a positive cross-sectional return premium -> positive IC.

Formula (per coin; C=close, H=high, L=low):
    r       = C / C.shift(1) - 1
    MAX5    = rolling_max(r, max_window=21)              # recent extreme payoff
    RSKEW   = rolling_skew(r, skew_window=60)            # right-skew = lottery
    rng     = (H - L) / C
    IRANGE  = rolling_mean(rng, max_window=21)           # intraday gambling range
    zA, zB, zC = time-series z-score(., z_window=252) of MAX5, RSKEW, IRANGE
    XLOT    = -(zA + zB + zC)                            # low lottery -> high score
    signal  = XLOT.shift(1)

Notes:
    - The three components are each standardised per-coin over time (z_window)
      before equal-weight summation, so they share a common scale.
    - z-score min_periods is fixed at 120 per spec (partial warm-up allowed once
      120 observations exist).
    - rolling_skew uses pandas' .rolling(w).skew() (bias-corrected, needs >=3 obs).
    - The sign flip (-) makes low-lottery coins rank highest, matching the
      expected positive IC.

Anti look-ahead:
    All rolling stats are backward-looking (use only data through t); the final
    signal is shifted by 1 so signal_t is known strictly before the t->t+1
    return it predicts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_MIN_PERIODS = 120


def _rolling_zscore(s: pd.Series, window: int, min_periods: int = Z_MIN_PERIODS) -> pd.Series:
    mean = s.rolling(window, min_periods=min_periods).mean()
    std = s.rolling(window, min_periods=min_periods).std(ddof=1)
    return (s - mean) / std.replace(0, np.nan)


def factor(
    ohlcv_df: pd.DataFrame,
    max_window: int = 21,
    skew_window: int = 60,
    z_window: int = 252,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    r = c / c.shift(1) - 1.0

    max5 = r.rolling(max_window, min_periods=max_window).max()
    rskew = r.rolling(skew_window, min_periods=skew_window).skew()
    rng = (h - l) / c
    irange = rng.rolling(max_window, min_periods=max_window).mean()

    z_a = _rolling_zscore(max5, z_window)
    z_b = _rolling_zscore(rskew, z_window)
    z_c = _rolling_zscore(irange, z_window)

    xlot = -(z_a + z_b + z_c)

    signal = xlot.shift(1)
    signal.name = "FSIM_cross_sectional_lottery_aversion"
    return signal.reindex(ohlcv_df.index)
