"""
F10: Realized Kurtosis Reversal — 實現峰度反轉因子

Category: volatility / behavioral
Source: 行為金融學 — 極端事件後的過度反應與均值回歸

經濟直覺：
- 近期報酬分布的峰度高 → 極端值（暴漲暴跌）頻繁出現
- 高峰度反映了市場在不穩定狀態，波動叢聚 → 非理性交易
- 極端波動後，市場傾向回歸常態 → 反轉信號
- 低峰度 = 穩定趨勢期 → 順勢信號

與既有因子的區別：
- F1 (Complexity Gap)：捕捉波動率結構的複雜度變化（非線性維度）
- F8 (Cubic Momentum)：三次函數捕捉動量非線性效應
- F10 (Kurtosis Reversal)：峰度純粹捕捉尾部事件後的行為偏差回歸
- 本因子的關鍵洞見：峰度 ≠ 波動率。高波動低峰度（均勻波動）= 趨勢期；高波動高峰度（跳躍）= 反轉期

無前視偏誤：僅使用 t 時刻及之前的資料。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    kurtosis_window: int = 20,
    smoothing_halflife: int = 5,
    zscore_window: int = 60,
) -> pd.Series:
    """計算 Realized Kurtosis Reversal 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, close（可選 symbol）
    kurtosis_window : int
        實現峰度計算窗口（日數）
    smoothing_halflife : int
        峰度平滑半衰期
    zscore_window : int
        最終標準化窗口

    Returns
    -------
    pd.Series
        正值 = 低峰度（穩定趨勢，順勢看多）
        負值 = 高峰度（尾部事件後，反轉壓力）
    """
    df = ohlcv_df.copy()

    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # ── 日報酬 ──
    ret = df["close"].pct_change()

    # ── Rolling kurtosis (excess kurtosis) ──
    roll_kurt = ret.rolling(kurtosis_window, min_periods=10).kurt()

    # ── 平滑處理 ──
    kurt_smooth = roll_kurt.ewm(halflife=smoothing_halflife, min_periods=5).mean()

    # ── Z-score 後反轉 ──
    zmean = kurt_smooth.rolling(zscore_window, min_periods=20).mean()
    zstd = kurt_smooth.rolling(zscore_window, min_periods=20).std()
    kurt_z = (kurt_smooth - zmean) / (zstd + 1e-8)

    # 反轉：高峰度 → 看空（均值回歸下行風險），低峰度 → 看多
    signal = -kurt_z

    # Winsorize
    signal = signal.clip(-3, 3)

    return signal
