"""
F2: Liquidity_Consumption_Tilt — 流動性消耗方向傾斜因子

經濟直覺：
- 知情交易者傾向主動消耗流動性（市價單），因其私有資訊具有時效性
- 買方持續消耗賣方掛單 → 買方資訊優勢 → 看漲信號
- 賣方激進消耗買方掛單 → 賣方資訊優勢 → 看跌信號

OHLCV 近似方法（無逐筆成交資料時的替代方案）：
- 使用每根 K 線內的價格走勢與成交量關係來推斷買賣方向
- Close > Open 視為買方主導，Close < Open 視為賣方主導
- 進一步使用 Close vs Mid(High,Low) 細化方向推斷
- 透過 BVOL (買方成交量) / SVOL (賣方成交量) 比例計算不平衡

若有逐筆成交資料（tick data），應改用 Lee-Ready 演算法進行精確分類。
本實作提供 OHLCV 近似版本，可在無 tick data 環境下運行。

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：cross-sectional rank 標準化。

參考文獻：
- Lee & Ready (1991) "Inferring Trade Direction from Intraday Data"
- Easley et al. (2012) "Flow Toxicity and Liquidity in a High-frequency World"
"""

from __future__ import annotations
import numpy as np


def _safe_volume(volume: np.ndarray) -> np.ndarray:
    """處理成交量缺失值。"""
    vol = np.asarray(volume, dtype=np.float64)
    vol = np.where(np.isnan(vol) | (vol < 0), 0.0, vol)
    return vol


def _infer_buy_sell_ohlcv(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    從 OHLCV 資料推斷每根 K 線的買方/賣方成交量。
    
    方法：
    1. 使用 Close vs Open 判斷主要方向
    2. 若 Close == Open，使用 Close vs (High+Low)/2 判斷
    3. 分配成交量給買方/賣方
    
    Returns:
        (buy_volume, sell_volume): 相同長度的陣列
    """
    n = len(closes)
    buy_vol = np.zeros(n)
    sell_vol = np.zeros(n)
    
    for i in range(n):
        vol = volumes[i] if not np.isnan(volumes[i]) and volumes[i] > 0 else 0.0
        if vol == 0:
            continue
        
        c, o = closes[i], opens[i]
        h, l = highs[i], lows[i]
        
        if np.isnan(c) or np.isnan(o):
            continue
        
        # 計算買賣中價
        mid = (h + l) / 2.0 if not (np.isnan(h) or np.isnan(l)) else (c + o) / 2.0
        
        if c > o:
            # 陽線：買方主導
            # 根據收盤在中價之上/之下的程度分配
            if not np.isnan(mid) and mid != o:
                buy_ratio = min(1.0, max(0.5, (c - mid) / (c - o) if c != o else 0.5))
            else:
                buy_ratio = 0.7  # 預設買方佔優
            buy_vol[i] = vol * buy_ratio
            sell_vol[i] = vol * (1 - buy_ratio)
        elif c < o:
            # 陰線：賣方主導
            if not np.isnan(mid) and mid != c:
                sell_ratio = min(1.0, max(0.5, (mid - c) / (o - c) if o != c else 0.5))
            else:
                sell_ratio = 0.7
            sell_vol[i] = vol * sell_ratio
            buy_vol[i] = vol * (1 - sell_ratio)
        else:
            # 十字線：方向不明，平分
            if c > mid:
                buy_vol[i] = vol * 0.55
                sell_vol[i] = vol * 0.45
            elif c < mid:
                buy_vol[i] = vol * 0.45
                sell_vol[i] = vol * 0.55
            else:
                buy_vol[i] = vol * 0.5
                sell_vol[i] = vol * 0.5
    
    return buy_vol, sell_vol


def liquidity_consumption_tilt(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    ema_halflife: int = 10,
) -> np.ndarray:
    """
    計算流動性消耗傾斜 (LCT) 信號。
    
    Args:
        opens: 開盤價序列
        highs: 最高價序列
        lows: 最低價序列
        closes: 收盤價序列
        volumes: 成交量序列
        ema_halflife: EMA 半衰期（K 線數），預設 10
    
    Returns:
        LCT 信號序列 [-1, 1]，正值代表買方消耗流動性
    """
    n = len(closes)
    if n < 3:
        return np.full(n, np.nan)
    
    volumes = _safe_volume(volumes)
    buy_vol, sell_vol = _infer_buy_sell_ohlcv(opens, highs, lows, closes, volumes)
    
    # 計算原始不平衡
    lct = np.full(n, np.nan)
    for i in range(n):
        total = buy_vol[i] + sell_vol[i]
        if total > 0:
            lct[i] = (buy_vol[i] - sell_vol[i]) / total
        else:
            lct[i] = 0.0
    
    # EMA 平滑
    alpha = 1.0 - np.exp(np.log(0.5) / ema_halflife)
    lct_ema = np.full(n, np.nan)
    first_valid = None
    
    for i in range(n):
        if np.isnan(lct[i]):
            continue
        if first_valid is None:
            lct_ema[i] = lct[i]
            first_valid = i
        else:
            lct_ema[i] = alpha * lct[i] + (1 - alpha) * lct_ema[i - 1]
    
    return lct_ema


def _expanding_zscore(signal: np.ndarray) -> np.ndarray:
    """Expanding-window z-score 標準化（無前視偏誤）。

    每個時間點 t 的標準化僅使用 [0, t] 範圍內的已觀測資料。
    """
    result = np.full_like(signal, np.nan, dtype=np.float64)
    running_sum = 0.0
    running_sum_sq = 0.0
    count = 0

    for i in range(len(signal)):
        val = signal[i]
        if np.isnan(val):
            continue
        count += 1
        running_sum += val
        running_sum_sq += val * val

        if count < 2:
            result[i] = 0.0
            continue

        mean = running_sum / count
        variance = (running_sum_sq / count) - mean * mean
        std = np.sqrt(max(variance, 1e-12))
        result[i] = (val - mean) / std

    return np.clip(result, -4.0, 4.0)


def compute(
    ohlcv_data: list[dict],
    ema_halflife: int = 10,
    standardize: str = "rank",
) -> dict:
    """
    F2 Liquidity Consumption Tilt 因子入口函數。
    
    符合 factor-lab 信號函數標準介面。
    
    Args:
        ohlcv_data: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
        ema_halflife: EMA 平滑半衰期
        standardize: 標準化方式
    
    Returns:
        {'signal': np.ndarray, 'raw_lct': np.ndarray, 'meta': dict}
    """
    opens = np.array([d["open"] for d in ohlcv_data], dtype=np.float64)
    highs = np.array([d["high"] for d in ohlcv_data], dtype=np.float64)
    lows = np.array([d["low"] for d in ohlcv_data], dtype=np.float64)
    closes = np.array([d["close"] for d in ohlcv_data], dtype=np.float64)
    volumes = np.array([d["volume"] for d in ohlcv_data], dtype=np.float64)
    
    lct = liquidity_consumption_tilt(opens, highs, lows, closes, volumes, ema_halflife)
    
    # 標準化：expanding-window z-score（無前視偏誤）
    signal = lct.copy()
    if standardize == "rank":
        signal = _expanding_zscore(signal)
    
    # 信號強度統計
    valid_signal = signal[~np.isnan(signal)]
    meta = {
        "factor": "F2_Liquidity_Consumption_Tilt",
        "ema_halflife": ema_halflife,
        "signal_mean": float(np.nanmean(signal)) if len(valid_signal) > 0 else None,
        "signal_std": float(np.nanstd(signal)) if len(valid_signal) > 0 else None,
        "n_valid": int((~np.isnan(signal)).sum()),
    }
    
    return {"signal": signal, "raw_lct": lct, "meta": meta}


__all__ = ["compute", "liquidity_consumption_tilt"]
