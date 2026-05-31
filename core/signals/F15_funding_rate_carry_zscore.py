"""F15: Funding Rate Carry Z-Score (FRC-Z)

Category: carry
Source: candidates/F15_funding_rate_carry_zscore.md

永續合約資金費率 (funding rate) 的滾動 z-score 反映多空槓桿擁擠度的歷史相對水準。
高 funding z-score（多頭極度擁擠）→ 反轉；低 funding z-score（空頭擁擠）→ 趨勢延續。
"""

import json
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd


def _fetch_binance_funding_rates(symbol: str = "BTCUSDT", limit: int = 1000) -> pd.DataFrame:
    """
    從 Binance fapi 抓取 funding rate 歷史。
    回傳 DataFrame: [funding_time_ms, funding_rate]
    
    Binance API: GET https://fapi.binance.com/fapi/v1/fundingRate
    參數: symbol=BTCUSDT, limit=1000
    """
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
    
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    
    all_rows = []
    remaining = limit
    earliest_ts = None
    while True:
        if earliest_ts is not None:
            batch_url = f"{url}&startTime={earliest_ts - 1}"
        else:
            batch_url = url
        with urllib.request.urlopen(batch_url, timeout=30) as r:
            data = json.load(r)
        if not data:
            break
        
        for entry in data:
            all_rows.append({
                "funding_time_ms": int(entry["fundingTime"]),
                "funding_rate": float(entry["fundingRate"]),
            })
        
        if len(data) < 1000:
            break
        
        earliest_ts = min(int(e["fundingTime"]) for e in data)
        remaining -= len(data)
        time.sleep(0.2)
    
    df = pd.DataFrame(all_rows)
    if df.empty:
        return df
    
    df = df.drop_duplicates(subset=["funding_time_ms"], keep="last")
    df = df.sort_values("funding_time_ms").reset_index(drop=True)
    return df


def _funding_to_daily(funding_df: pd.DataFrame, ohlcv_index: pd.DatetimeIndex) -> pd.Series:
    """
    將 8h funding rate 轉換為日頻，對齊 ohlcv 的 timestamp 欄位格式 (int ms)。
    每日 funding = 當日所有結算值之和。
    """
    if funding_df.empty:
        return pd.Series(np.nan, index=ohlcv_index)
    
    # 將 funding_time_ms 轉為日期並 resample 到 D
    df = funding_df.copy()
    df["date"] = pd.to_datetime(df["funding_time_ms"], unit="ms").dt.date
    daily = df.groupby("date")["funding_rate"].sum()
    daily.index = pd.DatetimeIndex([pd.Timestamp(d) for d in daily.index])
    
    # 將 ohlcv timestamp (int ms) 轉為日期索引
    ohlcv_dates = pd.to_datetime(ohlcv_index, unit="ms")
    
    # 對齊：每個 ohlcv 日期對應的 funding daily sum
    result = pd.Series(np.nan, index=ohlcv_dates)
    for date_val, funding_val in daily.items():
        result.loc[result.index == pd.Timestamp(date_val)] = funding_val
    
    result.index = ohlcv_index  # 恢復原索引
    return result.fillna(0.0)  # 無 funding 數據的日子設 0


def factor(ohlcv_df: pd.DataFrame, **params) -> pd.Series:
    """
    ohlcv_df: DataFrame with columns [timestamp, open, high, low, close, volume].
              timestamp 為 int ms 格式。
    Returns: Series with index matching ohlcv_df (one value per row).
    
    Parameters:
        ema_halflife: EMA halflife for smoothing daily funding (default: 3 days)
        zscore_window: Rolling z-score standardisation window (default: 60 days)
        winsorize_sigma: Clip z-score to ±sigma (default: 4.0)
    """
    ema_halflife = params.get("ema_halflife", 3)
    zscore_window = params.get("zscore_window", 60)
    winsorize_sigma = params.get("winsorize_sigma", 4.0)
    
    # Step 1: 抓取 funding rate 數據 (Binance fapi)
    funding_df = _fetch_binance_funding_rates(symbol="BTCUSDT", limit=1000)
    
    if funding_df.empty:
        # 無 funding 數據 → 回傳全 NaN signal
        return pd.Series(np.nan, index=ohlcv_df.index, name="frc_z")
    
    # Step 2: 轉換為日頻，對齊 ohlcv 日期
    funding_daily = _funding_to_daily(funding_df, ohlcv_df["timestamp"])
    
    # Step 3: EMA 平滑 (halflife=3 日)
    funding_smooth = funding_daily.ewm(halflife=ema_halflife, adjust=False, min_periods=1).mean()
    
    # 前 2*halflife 期設 NaN
    warmup = int(2 * ema_halflife)
    funding_smooth.iloc[:warmup] = np.nan
    
    # Step 4: Z-score 標準化 (60 日滾動)，shift(1) 防前視
    roll_mean = funding_smooth.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).mean()
    roll_std = funding_smooth.shift(1).rolling(zscore_window, min_periods=max(10, zscore_window // 2)).std()
    
    frc_z = (funding_smooth - roll_mean) / roll_std.replace(0, np.nan)
    
    # 信號：高 funding → 反轉 → 負向預測
    signal = -frc_z
    
    # Winsorize
    signal = signal.clip(lower=-winsorize_sigma, upper=winsorize_sigma)
    
    return signal
