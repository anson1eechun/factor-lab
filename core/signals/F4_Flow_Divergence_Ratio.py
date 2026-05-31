"""
F4: Flow_Divergence_Ratio — 流量發散比率因子 (FDR)

經濟直覺：
- 永續的價格趨勢需要持續增長的資金流入來支撐
- 當價格持續上升（或下降）但成交量反而萎縮時，表示推動趨勢的資金流正在枯竭
- FDR 透過捕捉價格動量與成交量動量之間的協同衰減 (co-decay) 來量化此效應

計算邏輯：
1. 價格動量：EMA(close_t - close_{t-1}, halflife=5)
2. 成交量動量：EMA(volume_t - volume_{t-1}, halflife=5)
3. 標準化至無量綱（60 日滾動 z-score）
4. 核心：raw_fdr = price_mom_z * vol_mom_z
   - 正值 = 價增量增（健康趨勢延續）
   - 負值 = 價量背離（趨勢衰竭 → 反轉信號）
5. signal = -EMA(raw_fdr, halflife=10)  # 取負 → FDR 負時做多

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：cross-sectional rank 標準化（單品種下為 expanding z-score）。

參考文獻：
- arXiv:2605.12977 — 暫態統計因子 / 流量概念移植
- arXiv:2605.11423 — 缺口維度與成交量互補
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


def _rolling_zscore(arr: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """滾動 z-score 標準化（無前視偏誤）。

    每個時間點 t 僅使用 [t-window+1, t] 範圍內的觀測值。
    """
    n = len(arr)
    if min_periods is None:
        min_periods = max(window // 3, 5)

    result = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - window + 1)
        segment = arr[start:i + 1]
        valid = segment[~np.isnan(segment)]

        if len(valid) < min_periods:
            continue

        mean = np.mean(valid)
        std = np.std(valid)
        if std < 1e-12:
            result[i] = 0.0
        else:
            result[i] = (arr[i] - mean) / std if not np.isnan(arr[i]) else np.nan

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


def flow_divergence_ratio(
    closes: np.ndarray,
    volumes: np.ndarray,
    price_halflife: int = 5,
    vol_halflife: int = 5,
    zscore_window: int = 60,
    fdr_halflife: int = 10,
) -> np.ndarray:
    """計算流量發散比率 (FDR) 信號。

    Args:
        closes: 收盤價序列
        volumes: 成交量序列
        price_halflife: 價格動量 EMA 半衰期
        vol_halflife: 成交量動量 EMA 半衰期
        zscore_window: 滾動 z-score 視窗長度
        fdr_halflife: FDR 平滑 EMA 半衰期

    Returns:
        FDR 信號序列，正值代表預期反轉做多（FDR 負 → 趨勢衰竭）
    """
    n = len(closes)
    if n < zscore_window + 5:
        return np.full(n, np.nan)

    # 1. 價格動量：close 差分後 EMA 平滑
    close_diff = np.diff(closes, prepend=closes[0])
    # prepend 會使 close_diff[0] = 0，標記第一個為 NaN 避免偏誤
    close_diff[0] = np.nan
    price_mom = _ema(close_diff, price_halflife)

    # 2. 成交量動量：volume 差分後 EMA 平滑
    vol_diff = np.diff(volumes, prepend=volumes[0])
    vol_diff[0] = np.nan
    vol_mom = _ema(vol_diff, vol_halflife)

    # 3. 滾動 z-score 標準化（無前視偏誤）
    price_mom_z = _rolling_zscore(price_mom, zscore_window)
    vol_mom_z = _rolling_zscore(vol_mom, zscore_window)

    # 4. 流量發散比率：價量動量交互項
    raw_fdr = np.full(n, np.nan)
    for i in range(n):
        if not (np.isnan(price_mom_z[i]) or np.isnan(vol_mom_z[i])):
            raw_fdr[i] = price_mom_z[i] * vol_mom_z[i]

    # 5. EMA 平滑 FDR
    fdr = _ema(raw_fdr, fdr_halflife)

    # 6. 取負：FDR 負（趨勢衰竭）→ 信號正（做多反轉）
    signal = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(fdr[i]):
            signal[i] = -fdr[i]

    return signal


def compute(
    ohlcv_data: list[dict],
    price_halflife: int = 5,
    vol_halflife: int = 5,
    zscore_window: int = 60,
    fdr_halflife: int = 10,
    standardize: str = "rank",
) -> dict:
    """F4 Flow Divergence Ratio 因子入口函數。

    符合 factor-lab 信號函數標準介面：
    - 輸入: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
    - 輸出: dict with 'signal' (np.ndarray), 'meta'

    Args:
        ohlcv_data: OHLCV 資料（時間升冪）
        price_halflife: 價格動量 EMA 半衰期
        vol_halflife: 成交量動量 EMA 半衰期
        zscore_window: 滾動 z-score 視窗長度
        fdr_halflife: FDR 平滑 EMA 半衰期
        standardize: 標準化方式 ('rank' = expanding z-score)

    Returns:
        {'signal': np.ndarray, 'raw_fdr': np.ndarray, 'price_mom_z': np.ndarray,
         'vol_mom_z': np.ndarray, 'meta': dict}
    """
    closes = np.array([d["close"] for d in ohlcv_data], dtype=np.float64)
    volumes = np.array([d["volume"] for d in ohlcv_data], dtype=np.float64)

    # 處理缺失值：前向填充
    closes = np.where(np.isnan(closes) | (closes <= 0), np.nan, closes)
    volumes = np.where(np.isnan(volumes) | (volumes < 0), 0.0, volumes)

    # 計算原始 FDR 信號
    raw_signal = flow_divergence_ratio(
        closes, volumes,
        price_halflife=price_halflife,
        vol_halflife=vol_halflife,
        zscore_window=zscore_window,
        fdr_halflife=fdr_halflife,
    )

    # 計算中間產物供診斷
    close_diff = np.diff(closes, prepend=closes[0])
    close_diff[0] = np.nan
    price_mom = _ema(close_diff, price_halflife)

    vol_diff = np.diff(volumes, prepend=volumes[0])
    vol_diff[0] = np.nan
    vol_mom = _ema(vol_diff, vol_halflife)

    price_mom_z = _rolling_zscore(price_mom, zscore_window)
    vol_mom_z = _rolling_zscore(vol_mom, zscore_window)

    # 標準化
    signal = raw_signal.copy()
    if standardize == "rank":
        signal = _expanding_zscore(signal)

    valid_signal = signal[~np.isnan(signal)]
    meta = {
        "factor": "F4_Flow_Divergence_Ratio",
        "price_halflife": price_halflife,
        "vol_halflife": vol_halflife,
        "zscore_window": zscore_window,
        "fdr_halflife": fdr_halflife,
        "signal_mean": float(np.nanmean(signal)) if len(valid_signal) > 0 else None,
        "signal_std": float(np.nanstd(signal)) if len(valid_signal) > 0 else None,
        "n_valid": int((~np.isnan(signal)).sum()),
    }

    return {
        "signal": signal,
        "raw_signal": raw_signal,
        "price_mom_z": price_mom_z,
        "vol_mom_z": vol_mom_z,
        "meta": meta,
    }


__all__ = ["compute", "flow_divergence_ratio"]
