"""
F5: Anchored_Mean_Reversion_Score — 錨定均值回歸分數因子 (AMRS)

經濟直覺：
- 市場存在一個隱含的「公允價格錨點」——以成交量加權平均價格 (VWAP) 近似
- 價格偏離 VWAP 越遠，均值回歸的引力越強
- 以波動率歸一化偏離幅度，使信號在高低波動率體制下具有可比性
- 這是一個純價值/均值回歸因子，不依賴趨勢方向

計算邏輯：
1. 典型價格：typical_price = (high + low + close) / 3
2. 滾動 VWAP(20)：SUM(typical_price * volume) / SUM(volume)
3. ATR(14)：平均真實波幅
4. raw_amrs = (vwap - close) / ATR
   - 正值 = 價格低於 VWAP（低估 → 做多）
   - 負值 = 價格高於 VWAP（高估 → 做空）
5. signal = EMA(raw_amrs, halflife=5)

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：cross-sectional rank 標準化（單品種下為 expanding z-score）。

參考文獻：
- arXiv:2605.17299 — SuperTrend asymmetry 1.8 進出比
- arXiv:2605.13407 — PRISM-VQ 先驗因子 + 學習因子混合
"""

from __future__ import annotations
import numpy as np


def _ema(arr: np.ndarray, halflife: int) -> np.ndarray:
    """計算指數加權移動平均（無前視偏誤）。"""
    n = len(arr)
    result = np.full(n, np.nan)
    alpha = 1.0 - np.exp(np.log(0.5) / halflife)

    first_valid = None
    for i in range(n):
        if np.isnan(arr[i]):
            continue
        if first_valid is None:
            result[i] = arr[i]
            first_valid = i
        else:
            result[i] = alpha * arr[i] + (1.0 - alpha) * result[i - 1]

    return result


def _true_range(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
) -> np.ndarray:
    """計算每根 K 線的 True Range。

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    """
    n = len(highs)
    tr = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(highs[i]) or np.isnan(lows[i]):
            continue
        hl = highs[i] - lows[i]

        if i == 0 or np.isnan(closes[i - 1]):
            tr[i] = hl
        else:
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

    return tr


def _rolling_mean(arr: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """滾動平均值（無前視偏誤）。"""
    n = len(arr)
    if min_periods is None:
        min_periods = max(window // 3, 3)

    result = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - window + 1)
        segment = arr[start:i + 1]
        valid = segment[~np.isnan(segment)]

        if len(valid) < min_periods:
            continue

        result[i] = np.mean(valid)

    return result


def _rolling_sum(arr: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """滾動總和（無前視偏誤）。"""
    n = len(arr)
    if min_periods is None:
        min_periods = max(window // 3, 3)

    result = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - window + 1)
        segment = arr[start:i + 1]
        valid = segment[~np.isnan(segment)]

        if len(valid) < min_periods:
            continue

        result[i] = np.sum(valid)

    return result


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


def anchored_mean_reversion_score(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    vwap_window: int = 20,
    atr_period: int = 14,
    ema_halflife: int = 5,
) -> np.ndarray:
    """計算錨定均值回歸分數 (AMRS) 信號。

    Args:
        highs: 最高價序列
        lows: 最低價序列
        closes: 收盤價序列
        volumes: 成交量序列
        vwap_window: VWAP 計算視窗長度
        atr_period: ATR 計算週期
        ema_halflife: AMRS 平滑 EMA 半衰期

    Returns:
        AMRS 信號序列，正值代表價格低於 VWAP（做多），負值代表價格高於 VWAP（做空）
    """
    n = len(closes)
    if n < max(vwap_window, atr_period) + 5:
        return np.full(n, np.nan)

    # 1. 典型價格
    typical_price = np.full(n, np.nan)
    for i in range(n):
        if not (np.isnan(highs[i]) or np.isnan(lows[i]) or np.isnan(closes[i])):
            typical_price[i] = (highs[i] + lows[i] + closes[i]) / 3.0

    # 2. 滾動 VWAP：SUM(tp * vol) / SUM(vol)
    tp_vol = typical_price * volumes
    tp_vol = np.where(np.isnan(tp_vol), np.nan, tp_vol)
    vol_valid = np.where(np.isnan(volumes) | (volumes < 0), np.nan, volumes)

    sum_tp_vol = _rolling_sum(tp_vol, vwap_window)
    sum_vol = _rolling_sum(vol_valid, vwap_window)

    vwap = np.full(n, np.nan)
    for i in range(n):
        if not (np.isnan(sum_tp_vol[i]) or np.isnan(sum_vol[i])) and sum_vol[i] > 0:
            vwap[i] = sum_tp_vol[i] / sum_vol[i]

    # 3. ATR(14)
    tr = _true_range(highs, lows, closes)
    atr = _ema(tr, atr_period)  # Wilder's ATR 使用 EMA 近似（halflife=14）

    # 4. 波動率歸一化偏離
    raw_amrs = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(vwap[i]) or np.isnan(closes[i]) or np.isnan(atr[i]):
            continue
        if atr[i] < 1e-12:
            raw_amrs[i] = 0.0
        else:
            # 正值 = 價格低於 VWAP（低估 → 做多）
            raw_amrs[i] = (vwap[i] - closes[i]) / atr[i]

    # 5. EMA 平滑
    signal = _ema(raw_amrs, ema_halflife)

    return signal


def compute(
    ohlcv_data: list[dict],
    vwap_window: int = 20,
    atr_period: int = 14,
    ema_halflife: int = 5,
    standardize: str = "rank",
) -> dict:
    """F5 Anchored Mean-Reversion Score 因子入口函數。

    符合 factor-lab 信號函數標準介面：
    - 輸入: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
    - 輸出: dict with 'signal' (np.ndarray), 'meta'

    Args:
        ohlcv_data: OHLCV 資料（時間升冪）
        vwap_window: VWAP 計算視窗長度
        atr_period: ATR 計算週期
        ema_halflife: AMRS 平滑 EMA 半衰期
        standardize: 標準化方式 ('rank' = expanding z-score)

    Returns:
        {'signal': np.ndarray, 'raw_signal': np.ndarray, 'vwap': np.ndarray,
         'atr': np.ndarray, 'meta': dict}
    """
    highs = np.array([d["high"] for d in ohlcv_data], dtype=np.float64)
    lows = np.array([d["low"] for d in ohlcv_data], dtype=np.float64)
    closes = np.array([d["close"] for d in ohlcv_data], dtype=np.float64)
    volumes = np.array([d["volume"] for d in ohlcv_data], dtype=np.float64)

    # 處理缺失值
    volumes = np.where(np.isnan(volumes) | (volumes < 0), 0.0, volumes)

    # 計算原始 AMRS 信號
    raw_signal = anchored_mean_reversion_score(
        highs, lows, closes, volumes,
        vwap_window=vwap_window,
        atr_period=atr_period,
        ema_halflife=ema_halflife,
    )

    # 計算中間產物供診斷
    typical_price = np.full(len(closes), np.nan)
    for i in range(len(closes)):
        if not (np.isnan(highs[i]) or np.isnan(lows[i]) or np.isnan(closes[i])):
            typical_price[i] = (highs[i] + lows[i] + closes[i]) / 3.0

    tp_vol = typical_price * volumes
    tp_vol = np.where(np.isnan(tp_vol), np.nan, tp_vol)
    vol_valid = np.where(np.isnan(volumes) | (volumes < 0), np.nan, volumes)

    sum_tp_vol = _rolling_sum(tp_vol, vwap_window)
    sum_vol = _rolling_sum(vol_valid, vwap_window)

    vwap = np.full(len(closes), np.nan)
    for i in range(len(closes)):
        if not (np.isnan(sum_tp_vol[i]) or np.isnan(sum_vol[i])) and sum_vol[i] > 0:
            vwap[i] = sum_tp_vol[i] / sum_vol[i]

    tr = _true_range(highs, lows, closes)
    atr = _ema(tr, atr_period)

    # 標準化
    signal = raw_signal.copy()
    if standardize == "rank":
        signal = _expanding_zscore(signal)

    valid_signal = signal[~np.isnan(signal)]
    meta = {
        "factor": "F5_Anchored_Mean_Reversion_Score",
        "vwap_window": vwap_window,
        "atr_period": atr_period,
        "ema_halflife": ema_halflife,
        "signal_mean": float(np.nanmean(signal)) if len(valid_signal) > 0 else None,
        "signal_std": float(np.nanstd(signal)) if len(valid_signal) > 0 else None,
        "n_valid": int((~np.isnan(signal)).sum()),
    }

    return {
        "signal": signal,
        "raw_signal": raw_signal,
        "vwap": vwap,
        "atr": atr,
        "meta": meta,
    }


__all__ = ["compute", "anchored_mean_reversion_score"]
