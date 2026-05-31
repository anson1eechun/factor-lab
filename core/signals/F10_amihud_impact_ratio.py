"""
F10: Amihud Volume-Price Impact Ratio — 量價衝擊比

Category: microstructure / liquidity
Source: Amihud (2002) illiquidity adapted for crypto

經濟直覺：
- 當少量成交量就能推動大幅價格變動 → 市場深度不足 → 價格反轉機率高
- 當大量成交量只能推動小幅價格變動 → 流動性充足 → 趨勢可持續
- 利用 abs(ret) / normalized_vol 衡量每單位成交量的價格衝擊
- 高衝擊比 → 薄市 → 均值回歸信號（做反方向）
- 低衝擊比 → 厚市 → 趨勢延續信號（做同方向）

與既有因子的區別：
- F4 (Flow Divergence): 量價動量相關性，捕捉趨勢衰竭
- F10 (Impact Ratio): 量價衝擊效率，捕捉流動性狀態 → 均值回歸/趨勢濾波

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：截面排名標準化訊號，正值看多、負值看空。
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    price_window: int = 5,
    vol_lookback: int = 20,
    smoothing_halflife: int = 10,
    zscore_window: int = 60,
) -> pd.Series:
    """計算 Amihud Volume-Price Impact Ratio 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, symbol, open, high, low, close, volume
    price_window : int
        價格變動計算窗口（預設 5 日）
    vol_lookback : int
        成交量均值計算窗口（預設 20 日）
    smoothing_halflife : int
        訊號平滑半衰期（預設 10 日）
    zscore_window : int
        最終訊號標準化窗口（預設 60 日）

    Returns
    -------
    pd.Series
        正值 = 低衝擊比（流動性佳，趨勢可持續）
        負值 = 高衝擊比（薄市，均值回歸壓力）
    """
    df = ohlcv_df.copy()

    # ── 排序避免前視偏誤 ──────────────────────────────────
    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        grp = df.groupby("symbol", group_keys=False)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)
        grp = None

    def _compute_group(g: pd.DataFrame) -> pd.Series:
        g = g.copy()

        # 5日價格變動
        price_ret = g["close"].pct_change(price_window)

        # 成交量 vs 20日均量（正規化）
        vol_ma = g["volume"].rolling(vol_lookback, min_periods=5).mean()
        vol_norm = g["volume"] / (vol_ma + 1e-8)

        # Amihud 衝擊比：abs(ret) / normalized_vol
        # 高值 = 薄市（少量成交量推動大價格變動）
        impact_raw = price_ret.abs() / (vol_norm + 1e-8)

        # 平滑處理（EMWA）
        impact_smooth = impact_raw.ewm(halflife=smoothing_halflife, min_periods=5).mean()

        # Z-score 標準化後反轉（高衝擊 → 空，低衝擊 → 多）
        impact_z = (
            (impact_smooth - impact_smooth.rolling(zscore_window, min_periods=20).mean())
            / (impact_smooth.rolling(zscore_window, min_periods=20).std() + 1e-8)
        )

        # 反轉：高衝擊比 → 負值（看空），低衝擊比 → 正值（看多）
        signal = -impact_z

        # Winsorize at ±3σ
        signal = signal.clip(-3, 3)

        # 成交量地板過濾
        vol_pct5 = g["volume"].rolling(20, min_periods=10).quantile(0.05)
        signal[g["volume"] < vol_pct5] = np.nan

        return signal

    if grp is not None and df["symbol"].nunique() > 1:
        pieces = []
        for sym, sub in df.groupby("symbol", sort=False):
            pieces.append(_compute_group(sub))
        result = pd.concat(pieces).reindex(df.index)
    else:
        result = _compute_group(df)

    return result
