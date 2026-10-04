"""
FSIM: Illiquidity-Impact Reversal (IIR)
---------------------------------------
Hypothesis:
    Illiquid assets exhibit stronger short-term price reversals. When a small
    notional volume moves price a lot (high Amihud illiquidity), recent momentum
    is more likely a transient impact that mean-reverts. We therefore short
    recent winners / long recent losers, scaled up when illiquidity is high.

Formula:
    r_t          = ln(C_t / C_{t-1})
    DV_t         = C_t * V_t                         # notional traded value
                   DV_t == 0  ->  ILLIQ_t = NaN
    ILLIQ_t      = |r_t| / DV_t                       # Amihud illiquidity
    ILLIQ_sm_t   = rolling_mean(ILLIQ, N=illiq_window)
    illiq_z_t    = rolling_zscore(ln(ILLIQ_sm + eps), z_window)
    mom_t        = rolling_sum(r, N=illiq_window)
    IIR_raw_t    = - illiq_z_t * tanh(rolling_zscore(mom_t, z_window))
    signal_t     = rolling_zscore(IIR_raw_t, sig_window)

Notes:
    - eps = 1e-12 protects ln() against zero/near-zero smoothed illiquidity.
    - tanh() bounds the momentum z-score so extreme momentum doesn't dominate;
      the sign flip (-) encodes the reversal direction.
    - illiq_window is reused for both the illiquidity smoothing and the
      momentum lookback (both N=5 per spec).

Anti look-ahead:
    All rolling stats use only data through t; the final signal is shifted by 1
    so signal_t is known strictly before the t->t+1 return it predicts.
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
    illiq_window: int = 5,
    z_window: int = 90,
    sig_window: int = 60,
    eps: float = 1e-12,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    c = df["close"].astype(float)
    v = df["volume"].astype(float)

    r = np.log(c / c.shift(1))

    dv = c * v
    illiq = (r.abs() / dv).where(dv != 0.0, np.nan)

    illiq_sm = illiq.rolling(illiq_window, min_periods=illiq_window).mean()
    illiq_z = _rolling_zscore(np.log(illiq_sm + eps), z_window)

    mom = r.rolling(illiq_window, min_periods=illiq_window).sum()
    mom_z = _rolling_zscore(mom, z_window)

    iir_raw = -illiq_z * np.tanh(mom_z)

    signal = _rolling_zscore(iir_raw, sig_window)

    signal = signal.shift(1)
    signal.name = "FSIM_illiquidity_impact_reversal"
    return signal.reindex(ohlcv_df.index)
