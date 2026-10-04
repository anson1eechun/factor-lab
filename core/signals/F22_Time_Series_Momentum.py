"""
F22: Time-Series Momentum (TSMOM)
---------------------------------
Hypothesis:
    跨資產最穩健的單因子(Moskowitz, Ooi & Pedersen 2012):一個資產過去 L 期的
    報酬方向,對未來報酬有正向預測力(趨勢延續)。以「波動正規化動能」表示,
    使不同波動水位的資產可比、也直接對應風險調整後的趨勢強度。

Formula:
    r_t        = log(C_t / C_{t-1})
    mom_t      = log(C_t / C_{t-L})                 # L 期累積趨勢
    vol_t      = std(r, vol_window)                 # 近期日波動
    sig_t      = mom_t / (vol_t * sqrt(L))          # 波動正規化(類 trailing Sharpe)
    signal_t   = sig_t.shift(1)                      # 防前視

Notes:
    - 正 IC(趨勢延續)。方向因子,部位 = sign(signal),回測端做波動目標化。
    - 與既有因子不同:F6/F7/F10/F18/F19 為日內價格結構;F20 regime;
      VWTP 為量能動能。F22 是純價格的跨期趨勢(無量),跨資產通用。
Anti look-ahead:
    所有 rolling 只用 ≤t;最終 shift(1)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, lookbacks=(20, 60, 120, 250), vol_window: int = 20,
           lookback=None, **_: object) -> pd.Series:
    """canonical TSMOM:多 lookback 波動正規化動能的平均(非單一,降參數依賴)。"""
    if lookback is not None:                      # 相容單一 lookback 呼叫
        lookbacks = (lookback,)
    c = ohlcv_df["close"].astype(float).reset_index(drop=True)
    r = np.log(c / c.shift(1))
    vol = r.rolling(vol_window, min_periods=vol_window).std(ddof=1).replace(0, np.nan)
    parts = []
    for L in lookbacks:
        mom = np.log(c / c.shift(L))
        parts.append(mom / (vol * np.sqrt(L)))
    sig = pd.concat(parts, axis=1).mean(axis=1)   # 等權混合
    return sig.shift(1).reindex(range(len(ohlcv_df))).reset_index(drop=True)
