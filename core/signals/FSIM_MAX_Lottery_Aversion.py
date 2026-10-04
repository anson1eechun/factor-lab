"""
FSIM_MAX_Lottery_Aversion — 橫截面 MAX lottery-aversion(XLOT REWORK 蒸餾)
--------------------------------------------------------------------------
Hypothesis (cross-sectional):
    crypto 散戶追逐「近月最大單日漲幅(MAX, Bali-Cakici-Whitelaw)」高的彩券型幣,
    使其過度定價 → 橫截面上高 MAX 的幣未來相對弱。因子取 -MAX,使低彩券性得高分。

Formula (per-coin):
    r_t   = C_t/C_{t-1} - 1
    MAX_t = rolling_max(r, 21)
    signal= (-MAX_t).shift(1)

Empirical (20-coin universe, 2023-02~2026-06, 真實):
    ic_t = +5.26(極顯著)、IC-IR = +0.153、前/後半 IC-IR +0.149/+0.157(regime-stable)。
    但 IC-IR < 0.3(Gate1 未過)、LS net Sharpe ~0.19、Mono 失敗(極端尾部雜訊)。
    → 真實且穩健的訊號,但未達可交易 alpha 門檻;保留為最佳線索供後續 REWORK。

Anti look-ahead: rolling backward-looking;最終 shift(1)。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, max_window: int = 21, **_: object) -> pd.Series:
    c = ohlcv_df["close"].astype(float).reset_index(drop=True)
    r = c / c.shift(1) - 1.0
    mx = r.rolling(max_window, min_periods=max(10, max_window // 2)).max()
    return (-mx).shift(1).reindex(range(len(ohlcv_df))).reset_index(drop=True)
