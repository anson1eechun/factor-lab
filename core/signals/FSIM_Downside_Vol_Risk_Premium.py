"""
FSIM: Downside Volatility Risk Premium (DVRP)
---------------------------------------------
Hypothesis:
    When realised volatility is dominated by downside moves (panic / oversold),
    the asset tends to carry a higher forward return as a risk premium for
    bearing downside risk. The factor is expected to be positively aligned with
    future returns (downside-dominated -> higher forward return).

Formula (additive design):
    r_t    = log(C_t / C_{t-1})
    down_t = min(r_t, 0)**2                                   >= 0
    up_t   = max(r_t, 0)**2                                   >= 0
    DSV_t  = rolling_sum(down_t, 20)                          >= 0
    USV_t  = rolling_sum(up_t,   20)                          >= 0
    ASY_t  = (DSV_t - USV_t) / (DSV_t + USV_t + eps)          in [-1, 1]
    z_t    = rolling_zscore(ASY_t, 60)
    signal = EMA(clip(z_t, -3, 3), halflife=5).shift(1)

Notes:
    - ASY is an additive difference-ratio of two non-negative quantities,
      bounded in [-1, 1]; eps = 1e-12 guards the all-zero window case.
    - z-score normalises ASY across regimes; clipping to +/-3 tames outliers
      before exponential smoothing.

Anti look-ahead:
    All rolling stats use only data through t; the EMA is causal
    (adjust=False); the final signal is shifted by 1 bar.
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
    sv_window: int = 20,
    z_window: int = 60,
    ema_halflife: int = 5,
    eps: float = 1e-12,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    c = df["close"].astype(float)
    r = np.log(c / c.shift(1))

    down = r.clip(upper=0.0) ** 2
    up = r.clip(lower=0.0) ** 2

    dsv = down.rolling(sv_window, min_periods=sv_window).sum()
    usv = up.rolling(sv_window, min_periods=sv_window).sum()

    asy = (dsv - usv) / (dsv + usv + eps)

    z = _rolling_zscore(asy, z_window)

    signal = z.clip(-3.0, 3.0).ewm(halflife=ema_halflife, adjust=False).mean()

    signal = signal.shift(1)
    signal.name = "FSIM_downside_vol_risk_premium"
    return signal.reindex(ohlcv_df.index)
