"""
F10: Volatility-Adjusted Momentum — 波動率調整動量因子

Category: momentum / risk
Source: Standard quant finance — risk-adjusted momentum (Barroso & Santa-Clara 2015)

經濟直覺：
- 相同幅度的價格變動，在低波動環境下更有資訊含量（穩定趨勢）
- 高波動下的價格變動更像是雜訊（易反轉）
- Momentum / RealizedVol = Sharpe-ratio-like metric for trend quality
- 高「波動調整動量」→ 穩健趨勢，順勢交易
- 低「波動調整動量」→ 雜訊主導，均值回歸

與既有因子的區別：
- F8 (Cubic Momentum): 三次函數映射非線性閾值效應（轉折點捕捉）
- F10 (Vol-Adj Mom): 線性動量經波動率標準化（趨勢品質度量）
- F5 (AMRS): 均值回歸基準（非動量）
- 與 F8 的關鍵區別：F8 問「動量有多大（非線性尺度）」；F10 問「動量有多可靠（經風險調整）」

無前視偏誤：僅使用 t 時刻及之前的資料。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    mom_window: int = 20,
    vol_window: int = 20,
    smoothing_halflife: int = 5,
    zscore_window: int = 60,
) -> pd.Series:
    """計算 Volatility-Adjusted Momentum 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, close（可選 symbol）
    mom_window : int
        動量計算窗口（日數）
    vol_window : int
        波動率計算窗口
    smoothing_halflife : int
        EMA 平滑半衰期
    zscore_window : int
        最終標準化窗口

    Returns
    -------
    pd.Series
        正值 = 高波動調整動量（穩健趨勢，順勢看多）
        負值 = 低/負波動調整動量（雜訊/反轉，看空）
    """
    df = ohlcv_df.copy()

    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # ── 價格動量：close / close_{t-window} - 1 ──
    mom = df["close"].pct_change(mom_window)

    # ── 實現波動率：std(ret, vol_window) * sqrt(365) annualized ──
    ret = df["close"].pct_change()
    vol = ret.rolling(vol_window, min_periods=10).std()

    # ── 波動率調整動量：mom / vol ──
    vol_adj_mom = mom / (vol + 1e-8)

    # ── EMA 平滑 ──
    smooth = vol_adj_mom.ewm(halflife=smoothing_halflife, min_periods=5).mean()

    # ── Z-score 標準化 ──
    zmean = smooth.rolling(zscore_window, min_periods=20).mean()
    zstd = smooth.rolling(zscore_window, min_periods=20).std()
    signal = (smooth - zmean) / (zstd + 1e-8)

    # Winsorize
    signal = signal.clip(-3, 3)

    return signal
