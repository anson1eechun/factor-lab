"""
FSIM_Volume_Volatility_Discount — 橫截面成交額波動折價(Chordia-Subrahmanyam-Anshuman 2001 的 crypto 版)
--------------------------------------------------------------------------------------------------
Hypothesis (cross-sectional):
    成交額呈脈衝式的幣由注意力交易者定價而被高估 → 成交額波動越高,後續報酬越低(direction -1)。

Formula (per-coin, W=60):
    dv_t  = close_t * volume_t(<= 0 或非有限 → NaN)
    g_t   = log(dv_t) - log(dv_{t-1})
    signal = rolling_std(g, W, min_periods=W, ddof=1)

Components: 無(非複合訊號)。

Anti look-ahead: rolling backward-looking;最終 shift(1)(universe_1d pack 以 entry_lag=0 假設訊號已 shift)。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, W: int = 60, **_: object) -> pd.Series:
    c = ohlcv_df["close"].astype(float)
    v = ohlcv_df["volume"].astype(float)
    dv = c * v
    dv = dv.where(np.isfinite(dv) & (dv > 0))
    g = np.log(dv).diff()
    sig = g.rolling(W, min_periods=W).std(ddof=1)
    return sig.shift(1)
