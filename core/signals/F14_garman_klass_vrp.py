"""F14: Garman-Klass Volatility Risk Premium (GK-VRP)

Category: volatility
Source: candidates/F14_garman_klass_vrp.md

Garman-Klass 已實現波動率 (OHLC 估計器) 與 EWMA 預期波動率之差值 (波動率風險溢價)。
高 VRP（已實現 >> 預期）→ 均值回歸；負 VRP（波動壓縮）→ 方向性突破。
"""

import numpy as np
import pandas as pd


def factor(ohlcv_df: pd.DataFrame, **params) -> pd.Series:
    """
    ohlcv_df: DataFrame with columns [timestamp, open, high, low, close, volume].
    Returns: Series with index matching ohlcv_df (one value per row).
    
    Parameters:
        ewma_halflife: EWMA halflife for expected volatility (default: 20 days)
        zscore_window: Rolling z-score standardisation window (default: 60 days)
        winsorize_sigma: Clip z-score to ±sigma (default: 4.0)
    """
    ewma_halflife = params.get("ewma_halflife", 20)
    zscore_window = params.get("zscore_window", 60)
    winsorize_sigma = params.get("winsorize_sigma", 4.0)
    
    close = ohlcv_df["close"].astype(float)
    open_ = ohlcv_df["open"].astype(float)
    high = ohlcv_df["high"].astype(float)
    low = ohlcv_df["low"].astype(float)
    
    # Step 1: Garman-Klass 估計器 (單日，年化)
    # u = log(H/O), d = log(L/O), c = log(C/O)
    # GK_var = 0.5 * u*(u-c) + (2*ln2 - 1) * c^2
    # 注意：防止 log(0) 或負值
    mask = (open_ > 0) & (high > 0) & (low > 0) & (close > 0)
    
    u = np.where(mask, np.log(high / open_), 0.0)
    c = np.where(mask, np.log(close / open_), 0.0)
    
    # 2*ln(2) - 1 ≈ 0.386294
    gk_var = 0.5 * u * (u - c) + 0.3862943611198906 * c * c
    gk_var = np.maximum(gk_var, 0.0)  # 防負方差
    gk_rv = np.sqrt(gk_var * 252)     # 年化 GK 波動率
    gk_rv = pd.Series(gk_rv, index=ohlcv_df.index)
    gk_rv[~mask] = np.nan
    
    # Step 2: EWMA 預期波動率 (halflife=20 日)
    # EWM adjust=False 使用遞推公式，無前視
    ewma_vol = gk_rv.ewm(halflife=ewma_halflife, adjust=False, min_periods=1).mean()
    
    # 前 2*halflife 期設 NaN (EWM 初始條件偏差)
    warmup = int(2 * ewma_halflife)
    ewma_vol.iloc[:warmup] = np.nan
    
    # Step 3: VRP = 已實現 - 預期 (差值，無界)
    vrp = gk_rv - ewma_vol
    
    # Step 4: Z-score 標準化 (60 日滾動)，只用 ≤ t 的資料
    # ⭐ 防前視偏誤：rolling 預設 backward-looking，但 z-score 包含觀測值自身
    # 為了絕對安全，對 rolling mean/std 使用 shift(1)，使 z-score 完全只用 < t 的資料
    vrp_roll_mean = vrp.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).mean()
    vrp_roll_std = vrp.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).std()
    
    vrp_z = (vrp - vrp_roll_mean) / vrp_roll_std.replace(0, np.nan)
    
    # 信號：高 VRP → 均值回歸 → 負向預測；負 VRP → 突破 → 正向預測
    signal = -vrp_z
    
    # Winsorize 極端值
    signal = signal.clip(lower=-winsorize_sigma, upper=winsorize_sigma)
    
    return signal
