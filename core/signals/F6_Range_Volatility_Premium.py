"""
F6: Range Volatility Premium (RVP)
----------------------------------
Hypothesis:
    RVP_t = log( sigma_GK_t / sigma_CC_t )
    signal_t = -EMA( rolling_zscore(RVP_t, 60), halflife=5 )

GK (Garman-Klass) variance per bar:
    gk_var_t = 0.5 * (ln(H/L))^2 - (2*ln 2 - 1) * (ln(C/O))^2

Anti look-ahead:
    All rolling operations use only data up to t. To be safe at the
    factor → return alignment layer we additionally .shift(1) the final
    signal so that signal_t is decided on information available at close
    of t and applies to t+1 returns.

Output:
    pandas.Series indexed identically to the input DataFrame
    (RangeIndex matching ohlcv_df.index).
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
    gk_window: int = 20,
    cc_window: int = 20,
    z_window: int = 60,
    ema_halflife: int = 5,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    # Guard against non-positive prices
    safe = (o > 0) & (h > 0) & (l > 0) & (c > 0)
    o = o.where(safe)
    h = h.where(safe)
    l = l.where(safe)
    c = c.where(safe)

    # 1) Garman-Klass per-bar variance
    ln_hl = np.log(h / l)
    ln_co = np.log(c / o)
    gk_var = 0.5 * ln_hl**2 - (2.0 * np.log(2.0) - 1.0) * ln_co**2

    # 2) Rolling sigma_GK (sqrt of mean variance)
    sigma_gk = np.sqrt(gk_var.rolling(gk_window, min_periods=gk_window).mean().clip(lower=0))

    # 3) Close-to-Close sigma
    ret_cc = np.log(c / c.shift(1))
    sigma_cc = ret_cc.rolling(cc_window, min_periods=cc_window).std(ddof=1)

    # 4) RVP log ratio (unbounded)
    ratio = sigma_gk / sigma_cc.replace(0, np.nan)
    rvp = np.log(ratio.where(ratio > 0))

    # 5) Rolling z-score (60d)
    z = _rolling_zscore(rvp, z_window)

    # 6) EMA smoothing + sign flip
    ema = z.ewm(halflife=ema_halflife, adjust=False).mean()
    signal = -ema

    # Mask initial warm-up: rolling window + EWM bias
    warmup = max(gk_window + z_window, 2 * ema_halflife)
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    # Anti look-ahead: signal at t reflects info through t close,
    # so apply to t+1. Shift(1) is intentional.
    signal = signal.shift(1)

    signal.name = "F6_range_volatility_premium"
    return signal.reindex(ohlcv_df.index)
