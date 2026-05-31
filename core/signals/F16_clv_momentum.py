"""F16: Close Location Value Momentum (CLV-Mom)

Category: momentum
Source: candidates/F16_clv_momentum.md

Close Location Value (CLV = (Close-Low)/(High-Low)) 衡量收盤價在當日高低價區間的位置。
CLV 的滾動動量 (CLV 偏差的 EMA 趨勢) 比純收盤價動量更能捕捉市場微結構中的
買賣力量持續性 —— 高 CLV 代表買方主導，連續高 CLV 預測正向趨勢延續。
"""

import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, **params) -> pd.Series:
    """
    ohlcv_df: DataFrame with columns [timestamp, open, high, low, close, volume].
    Returns: Series with index matching ohlcv_df (one value per row).
    
    Parameters:
        clv_window: Rolling window for CLV mean (default: 14 days, bi-weekly cycle)
        ema_halflife: EMA halflife for CLV deviation momentum (default: 5 days)
        zscore_window: Rolling z-score standardisation window (default: 60 days)
        winsorize_sigma: Clip z-score to ±sigma (default: 4.0)
        atr_filter: If True, flag candles where (High-Low) > 3*ATR(14) as neutral CLV=0.5
    """
    clv_window = params.get("clv_window", 14)
    ema_halflife = params.get("ema_halflife", 5)
    zscore_window = params.get("zscore_window", 60)
    winsorize_sigma = params.get("winsorize_sigma", 4.0)
    atr_filter = params.get("atr_filter", False)
    
    close = ohlcv_df["close"].astype(float)
    open_ = ohlcv_df["open"].astype(float)
    high = ohlcv_df["high"].astype(float)
    low = ohlcv_df["low"].astype(float)
    
    # Step 1: 計算 CLV = (Close - Low) / (High - Low)
    hl_range = high - low
    mask_valid = hl_range > 0
    
    clv = pd.Series(np.nan, index=ohlcv_df.index)
    clv[mask_valid] = (close[mask_valid] - low[mask_valid]) / hl_range[mask_valid]
    clv[~mask_valid] = 0.5  # High == Low: 中性 CLV
    
    # 可選：ATR 過濾異常 K 線 (插針)
    if atr_filter:
        atr = (hl_range.rolling(14).mean()).shift(1)  # shift 防止前視
        abnormal = hl_range > 3 * atr
        clv[abnormal] = 0.5  # 異常 K 線設中性
    
    # Step 2: CLV 偏差 (相對滾動均值的偏差)
    # shift(1) 防前視：t 日的 CLV 均值只用 < t 的資料
    clv_mean = clv.shift(1).rolling(clv_window, min_periods=max(5, clv_window // 3)).mean()
    clv_dev = clv - clv_mean  # [-0.5, +0.5]
    
    # Step 3: 偏差動量 (EMA 累積)
    clv_mom = clv_dev.ewm(halflife=ema_halflife, adjust=False, min_periods=1).mean()
    
    # 前 2*halflife 期設 NaN
    warmup = int(2 * ema_halflife)
    clv_mom.iloc[:warmup] = np.nan
    
    # Step 4: Z-score 標準化 (60 日)，shift(1) 防前視
    roll_mean = clv_mom.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).mean()
    roll_std = clv_mom.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).std()
    
    signal = (clv_mom - roll_mean) / roll_std.replace(0, np.nan)
    
    # 信號正值 → 正向動量 → 預測正向回報
    
    # Winsorize
    signal = signal.clip(lower=-winsorize_sigma, upper=winsorize_sigma)
    
    return signal
