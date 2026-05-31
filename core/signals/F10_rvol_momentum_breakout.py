"""
F10: RVOL Momentum Breakout — 相對成交量突破動量因子

Category: momentum/microstructure
Source: 實務 traders 常用，結合相對成交量 (RVOL) 與價格動量

經濟直覺：
- 正常成交量的價格變動可能只是雜訊
- 成交量顯著放大（相對於自身常態）+ 價格方向性動量 = 知情交易者的足跡
- 大資金進場通常伴隨成交量異常放大
- RVOL × 價格動量正負號 → 辨識真突破 vs 假突破

與既有因子的區別：
- 非純動量（F8 三次動量反轉捕捉的是非線性閾值效應）
- 非純成交量（F2 VWDT 捕捉的是流動性消耗方向）
- RVOL Breakout 結合兩者門檻：先確認量異常用，再取方向

無前視偏誤：僅使用 t 時刻及之前的資料。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    vol_lookback: int = 20,
    rvol_threshold: float = 1.5,
    price_window: int = 3,
    smoothing_halflife: int = 5,
    zscore_window: int = 60,
) -> pd.Series:
    """計算 RVOL Momentum Breakout 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, close, volume（可選 symbol）
    vol_lookback : int
        RVOL 中位數計算窗口
    rvol_threshold : float
        相對成交量突破門檻倍數
    price_window : int
        價格動量計算窗口（日數）
    smoothing_halflife : int
        EMA 平滑半衰期
    zscore_window : int
        最終標準化窗口

    Returns
    -------
    pd.Series
        正值看多（放量+上漲），負值看空（放量+下跌）
    """
    df = ohlcv_df.copy()

    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # ── RVOL：volume / 20日 median ──
    vol_median = df["volume"].rolling(vol_lookback, min_periods=5).median()
    rvol = df["volume"] / (vol_median + 1e-8)

    # ── 價格動量 ──
    price_mom = df["close"].pct_change(price_window)

    # ── RVOL 突破 + 方向過濾 ──
    # 放量超過 threshold 的日期，取價格動量方向
    # 放量不足的日期，signal = 0（無資訊）
    breakout = rvol >= rvol_threshold
    raw_signal = pd.Series(0.0, index=df.index)
    raw_signal[breakout] = np.sign(price_mom[breakout]) * (rvol[breakout] - rvol_threshold)

    # ── EMA 平滑 ──
    smoothed = raw_signal.ewm(halflife=smoothing_halflife, min_periods=3).mean()

    # ── Z-score 標準化 ──
    zmean = smoothed.rolling(zscore_window, min_periods=20).mean()
    zstd = smoothed.rolling(zscore_window, min_periods=20).std()
    signal = (smoothed - zmean) / (zstd + 1e-8)

    # Winsorize
    signal = signal.clip(-3, 3)

    return signal
