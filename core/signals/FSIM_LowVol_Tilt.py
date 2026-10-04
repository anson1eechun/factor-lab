"""
FSIM_LowVol_Tilt — crypto long-only 低波動傾斜(SIM-2026-06-18-003)
-----------------------------------------------------------------
Hypothesis (directional / long-only tilt):
    低波動率幣在 crypto 橫截面有真實前瞻報酬(來自 SIM-2026-06-18-002 對照組:
    純 -RV60 IC-IR 0.21 / IC t 6.93),但 quintile LS 不可變現(做空小幣噪音)。
    改用 long-only 低波動傾斜組合 → 是否較等權基準有更高 risk-adjusted 報酬(超額 Sharpe>0)。
Score (per-coin): RV = std(log return, 60),低波動=低 RV。signal = -RV(高分=低波動),shift(1)。
Anti look-ahead: rolling 只用 ≤t;最終 shift(1)。組合構造在 eval 端(逆波動權重/低波動 quintile)。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, rv_window: int = 60, **_: object) -> pd.Series:
    c = ohlcv_df["close"].astype(float).reset_index(drop=True)
    rv = np.log(c).diff().rolling(rv_window, min_periods=rv_window // 2).std(ddof=1)
    return (-rv).shift(1).reindex(range(len(ohlcv_df))).reset_index(drop=True)
