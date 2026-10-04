"""
FSIM: Volatility-of-Volatility Timing (VoVT)
--------------------------------------------
Hypothesis:
    The second moment of volatility (how stable realised volatility itself is)
    carries timing information that is orthogonal to the *level* of volatility.
    When vol-of-vol is low (volatility regime is stable), forward returns tend
    to be higher; when vol-of-vol spikes (regime is turbulent / uncertain),
    forward returns tend to be lower. We therefore expect a POSITIVE IC after
    flipping the sign of the standardised vol-of-vol.

Formula (OHLC only, Parkinson estimator):
    pk_t  = (1 / (4 * ln 2)) * (ln(H_t / L_t))^2     # Parkinson per-bar variance
    rv_t  = sqrt(rolling_mean(pk, rv_window))         # realised volatility level
    vov_t = rolling_std(rv, vov_window, ddof=1)       # volatility of volatility
    z_t   = rolling_zscore(vov, z_window)
    raw_t = - z_t                                      # low vov -> high factor value
    signal_t = raw_t.shift(1)

Anti look-ahead:
    All rolling operations use only data through t. The final signal is shifted
    by 1 so that signal_t is decided on information available at the close of t
    and applies to t+1 returns.

Output:
    pandas.Series indexed identically to the input DataFrame (warm-up NaN ok).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_INV_4LN2 = 1.0 / (4.0 * np.log(2.0))


def _rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=window).mean()
    std = s.rolling(window, min_periods=window).std(ddof=1)
    return (s - mean) / std.replace(0, np.nan)


def factor(
    ohlcv_df: pd.DataFrame,
    rv_window: int = 10,
    vov_window: int = 20,
    z_window: int = 60,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    h = df["high"].astype(float)
    l = df["low"].astype(float)

    # Guard against non-positive prices (would break the log).
    safe = (h > 0) & (l > 0)
    h = h.where(safe)
    l = l.where(safe)

    # 1) Parkinson per-bar variance
    pk = _INV_4LN2 * np.log(h / l) ** 2

    # 2) Realised volatility level
    rv = np.sqrt(pk.rolling(rv_window, min_periods=rv_window).mean().clip(lower=0))

    # 3) Volatility of volatility (sample std, ddof=1)
    vov = rv.rolling(vov_window, min_periods=vov_window).std(ddof=1)

    # 4) Rolling z-score and sign flip (low vov -> high factor value)
    raw = -_rolling_zscore(vov, z_window)

    # Mask initial warm-up explicitly.
    warmup = rv_window + vov_window + z_window
    if warmup < len(raw):
        raw.iloc[:warmup] = np.nan
    else:
        raw[:] = np.nan

    # Anti look-ahead: signal at t reflects info through t close, apply to t+1.
    signal = raw.shift(1)

    signal.name = "FSIM_vol_of_vol_timing"
    return signal.reindex(ohlcv_df.index)
