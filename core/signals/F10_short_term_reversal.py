"""
F10: Short-Term Reversal — 短期反轉因子

Category: momentum_reversal / behavioral
Source: Jegadeesh (1990), Lehmann (1990) — the original short-term reversal anomaly

經濟直覺：
- 市場參與者對近期資訊過度反應，導致價格暫時偏離
- 短期（1-5日）的極端回報傾向於在後續期間反轉
- 逆向操作：買入近期跌幅最大的資產，賣出近期漲幅最大的資產
- 在加密貨幣市場尤為有效（高波動 + 散戶主導的過度反應）

與既有因子的區別：
- F5 (AMRS): 長期均值回歸，使用 anchored 窗口
- F8 (Cubic Momentum): 中期三次非線性動量
- F10 (STR): 最短期的純價格反轉（1-3日），捕捉日內/日間過度反應

無前視偏誤：僅使用 t 時刻及之前的資料。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    reversal_window: int = 3,
    smoothing_halflife: int = 2,
    zscore_window: int = 40,
) -> pd.Series:
    """計算 Short-Term Reversal 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, close（可選 symbol）
    reversal_window : int
        反轉窗口（日數），1=日反轉，3=三日反轉
    smoothing_halflife : int
        EMA 平滑半衰期（短期反轉用短平滑）
    zscore_window : int
        最終標準化窗口（短窗口配合短因子）

    Returns
    -------
    pd.Series
        正值 = 近期下跌（買入信號，預期反轉上漲）
        負值 = 近期上漲（賣出信號，預期反轉下跌）
    """
    df = ohlcv_df.copy()

    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # ── 短期報酬（反轉窗口）──
    short_ret = df["close"].pct_change(reversal_window)

    # ── 反轉：負報酬 → 正信號（預期反轉上漲）──
    raw_signal = -short_ret

    # ── EMA 平滑 ──
    smooth = raw_signal.ewm(halflife=smoothing_halflife, min_periods=3).mean()

    # ── Z-score 標準化 ──
    zmean = smooth.rolling(zscore_window, min_periods=15).mean()
    zstd = smooth.rolling(zscore_window, min_periods=15).std()
    signal = (smooth - zmean) / (zstd + 1e-8)

    # Winsorize
    signal = signal.clip(-3, 3)

    return signal
