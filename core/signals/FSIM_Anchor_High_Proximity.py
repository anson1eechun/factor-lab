"""
FSIM_Anchor_High_Proximity — 橫截面距 L 日高點的錨定效應(George-Hwang 52w-high 的 crypto 版)
--------------------------------------------------------------------------------------------
Hypothesis (cross-sectional):
    交易者以近期高點為錨:逼近前高者對好消息反應不足 → 距前高越近,後續報酬越高。

Formula (per-coin, L=180):
    Hmax_t  = rolling_max(high, L)(含當日,min_periods=L)
    ret_L   = log(C_t / C_{t-L})
    runup_L = log(Hmax_t / C_{t-L})
    signal  = ret_L - runup_L = log(C_t / Hmax_t)(<= 0)

Components: ret_L(宣告 +1)、runup_L(宣告 -1)。

Anti look-ahead: rolling backward-looking;最終 shift(1)。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _prep(ohlcv_df: pd.DataFrame, L: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    c = ohlcv_df["close"].astype(float).reset_index(drop=True)
    h = ohlcv_df["high"].astype(float).reset_index(drop=True)
    c = c.where(c > 0)
    h = h.where(h > 0)
    hmax = h.rolling(L, min_periods=L).max()
    return c, hmax, c.shift(L)


def _finish(s: pd.Series, n: int) -> pd.Series:
    return s.shift(1).reindex(range(n)).reset_index(drop=True)


def _ret_L(ohlcv_df: pd.DataFrame, L: int = 180, **_: object) -> pd.Series:
    c, _hmax, c_lag = _prep(ohlcv_df, L)
    return _finish(np.log(c / c_lag), len(ohlcv_df))


def _runup_L(ohlcv_df: pd.DataFrame, L: int = 180, **_: object) -> pd.Series:
    _c, hmax, c_lag = _prep(ohlcv_df, L)
    return _finish(np.log(hmax / c_lag), len(ohlcv_df))


def factor(ohlcv_df: pd.DataFrame, L: int = 180, **_: object) -> pd.Series:
    c, hmax, _c_lag = _prep(ohlcv_df, L)
    return _finish(np.log(c / hmax), len(ohlcv_df))


def components(L: int = 180, **_: object) -> dict:
    return {
        "ret_L": lambda df: _ret_L(df, L=L),
        "runup_L": lambda df: _runup_L(df, L=L),
    }
