"""
FSIM: Idiosyncratic Oversold Reversal (IOR)
-------------------------------------------
Per-coin, cross-sectional, additive factor. All three legs share the same sign
convention ("more oversold -> more positive"), so they add up:

    ret1d       = close / close.shift(1) - 1
    vol20       = rolling_std(ret1d, rev_window)
    mom5        = close / close.shift(mom) - 1
    reversal    = - mom5 / (vol20 * sqrt(mom) + eps)            # bigger drop -> +

    dvol        = volume * close
    adv20       = rolling_mean(dvol, rev_window)
    vspike      = log( (rolling_sum(dvol, 5) / 5) / (adv20 + eps) + eps )

    lower_wick  = min(open, close) - low
    rng         = high - low
    absorb      = rolling_mean( lower_wick / (rng + eps), 5 )

    IOR         = z60(reversal) + 0.5*z60(vspike) + 0.5*z60(absorb)
    signal      = IOR.shift(1)                                  # anti look-ahead

Anti look-ahead:
    Every rolling stat uses only data through t; the final signal is shifted by
    one bar (single shift on the output, no shift on the input frame).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-9


def _rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std(ddof=1)
    return (s - mean) / std.replace(0, np.nan)


def factor(
    ohlcv_df: pd.DataFrame,
    rev_window: int = 20,
    mom: int = 5,
    z_window: int = 60,
    **_: object,
) -> pd.Series:
    df = ohlcv_df

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)

    # --- reversal leg: idiosyncratic-vol-scaled short-term momentum (negated)
    ret1d = c / c.shift(1) - 1.0
    vol20 = ret1d.rolling(rev_window, min_periods=rev_window).std(ddof=1)
    mom5 = c / c.shift(mom) - 1.0
    reversal = -mom5 / (vol20 * np.sqrt(mom) + EPS)

    # --- volume-spike leg: recent dollar-volume vs its 20d average
    dvol = v * c
    adv20 = dvol.rolling(rev_window, min_periods=rev_window).mean()
    vspike = np.log(
        (dvol.rolling(5, min_periods=5).sum() / 5.0) / (adv20 + EPS) + EPS
    )

    # --- absorption leg: lower-wick fraction of range (buying pressure)
    lower_wick = np.minimum(o, c) - l
    rng = h - l
    absorb = (lower_wick / (rng + EPS)).rolling(5, min_periods=5).mean()

    ior = (
        _rolling_zscore(reversal, z_window)
        + 0.5 * _rolling_zscore(vspike, z_window)
        + 0.5 * _rolling_zscore(absorb, z_window)
    )

    signal = ior.shift(1)
    signal.name = "FSIM_idiosyncratic_oversold_reversal"
    return signal.reindex(ohlcv_df.index)
