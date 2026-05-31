"""
F6: Return_Asymmetry_Premium — 回報不對稱溢酬因子 (RAP)

經濟直覺：
- 傳統 carry 因子的核心邏輯是「持有資產所獲得的隱含收益補償」
- 市場參與者願意為承受不對稱風險支付（或索取）溢酬
- 正偏態（多數小幅虧損、少數大幅獲利）→ 市場定價正向風險溢酬 → long carry
- 負偏態（多數小幅獲利、少數大幅虧損）→ 市場參與者避險 → short carry
- RAP 以偏態與波動率的交互項量化此溢酬

計算邏輯：
1. 日對數回報：r_t = ln(close_t / close_{t-1})
2. 滾動偏態（20 日窗口，Fisher-Pearson 偏態係數）
3. 滾動波動率（20 日，年化）：vol = std(r) * sqrt(365)
4. raw_rap = skew * vol
   - 正偏態 × 高波動 = 正向溢酬 → 做多
   - 負偏態 × 高波動 = 避險需求 → 做空
   - 低波動（任一偏態）→ 近零 → 中立
5. rap = EMA(clip(raw_rap, -3, 3), halflife=5)
6. signal = rap（正值做多，負值做空）

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：cross-sectional rank 標準化（單品種下為 expanding z-score）。

參考文獻：
- arXiv:2605.17275 — GPR-HS volatility filter
- arXiv:2605.12977 — EM 框架 + 暫態因子
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


def _rolling_skew(arr: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """滾動偏態（Fisher-Pearson 調整偏態係數，無前視偏誤）。

    每個時間點 t 僅使用 [t-window+1, t] 範圍內的觀測值。
    """
    n = len(arr)
    if min_periods is None:
        min_periods = max(window // 2, 8)

    result = np.full(n, np.nan)

    for i in range(n):
        start = max(0, i - window + 1)
        segment = arr[start:i + 1]
        valid = segment[~np.isnan(segment)]

        if len(valid) < min_periods:
            continue

        mean = np.mean(valid)
        std = np.std(valid, ddof=0)  # population std for skew

        if std < 1e-12:
            result[i] = 0.0
            continue

        # Fisher-Pearson 標準化偏態係數
        n_valid = len(valid)
        z_scores = (valid - mean) / std
        m3 = np.mean(z_scores ** 3)

        # 調整因子（小樣本修正）
        if n_valid >= 3:
            adjustment = np.sqrt(n_valid * (n_valid - 1)) / (n_valid - 2)
            result[i] = adjustment * m3
        else:
            result[i] = m3

    return result


def _rolling_std(arr: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """滾動標準差（無前視偏誤）。"""
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

        result[i] = np.std(valid, ddof=0)

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


def return_asymmetry_premium(
    closes: np.ndarray,
    skew_window: int = 20,
    vol_window: int = 20,
    ema_halflife: int = 5,
    annualize: bool = True,
) -> np.ndarray:
    """計算回報不對稱溢酬 (RAP) 信號。

    Args:
        closes: 收盤價序列
        skew_window: 偏態計算視窗長度
        vol_window: 波動率計算視窗長度
        ema_halflife: RAP 平滑 EMA 半衰期
        annualize: 是否年化波動率（乘以 sqrt(365)）

    Returns:
        RAP 信號序列，正值代表正向溢酬（做多），負值代表避險需求（做空）
    """
    n = len(closes)
    min_required = max(skew_window, vol_window) + 5
    if n < min_required:
        return np.full(n, np.nan)

    # 1. 對數回報
    log_returns = np.full(n, np.nan)
    for i in range(1, n):
        if not (np.isnan(closes[i]) or np.isnan(closes[i - 1])):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns[i] = np.log(closes[i] / closes[i - 1])

    # 2. 滾動偏態
    skew = _rolling_skew(log_returns, skew_window)

    # 3. 滾動波動率（可選年化）
    vol = _rolling_std(log_returns, vol_window)
    if annualize:
        annualize_factor = np.sqrt(365.0)
        for i in range(n):
            if not np.isnan(vol[i]):
                vol[i] = vol[i] * annualize_factor

    # 4. 回報不對稱溢酬
    raw_rap = np.full(n, np.nan)
    for i in range(n):
        if not (np.isnan(skew[i]) or np.isnan(vol[i])):
            raw_rap[i] = skew[i] * vol[i]

    # 5. Clip 去極值 + EMA 平滑
    raw_rap_clipped = np.clip(raw_rap, -3.0, 3.0)
    # 被 clip 的位置若原本是 NaN 會變成 -3 或 3，所以需要 mask
    raw_rap_for_ema = np.where(np.isnan(raw_rap), np.nan, raw_rap_clipped)
    signal = _ema(raw_rap_for_ema, ema_halflife)

    return signal


def compute(
    ohlcv_data: list[dict],
    skew_window: int = 20,
    vol_window: int = 20,
    ema_halflife: int = 5,
    annualize: bool = True,
    standardize: str = "rank",
) -> dict:
    """F6 Return Asymmetry Premium 因子入口函數。

    符合 factor-lab 信號函數標準介面：
    - 輸入: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
    - 輸出: dict with 'signal' (np.ndarray), 'meta'

    Args:
        ohlcv_data: OHLCV 資料（時間升冪）
        skew_window: 偏態計算視窗長度
        vol_window: 波動率計算視窗長度
        ema_halflife: RAP 平滑 EMA 半衰期
        annualize: 是否年化波動率
        standardize: 標準化方式 ('rank' = expanding z-score)

    Returns:
        {'signal': np.ndarray, 'raw_signal': np.ndarray, 'skew': np.ndarray,
         'vol': np.ndarray, 'meta': dict}
    """
    closes = np.array([d["close"] for d in ohlcv_data], dtype=np.float64)

    # 處理缺失值：前向填充
    closes = np.where(np.isnan(closes) | (closes <= 0), np.nan, closes)

    # 計算原始 RAP 信號
    raw_signal = return_asymmetry_premium(
        closes,
        skew_window=skew_window,
        vol_window=vol_window,
        ema_halflife=ema_halflife,
        annualize=annualize,
    )

    # 計算中間產物供診斷
    n = len(closes)
    log_returns = np.full(n, np.nan)
    for i in range(1, n):
        if not (np.isnan(closes[i]) or np.isnan(closes[i - 1])):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns[i] = np.log(closes[i] / closes[i - 1])

    skew = _rolling_skew(log_returns, skew_window)
    vol = _rolling_std(log_returns, vol_window)
    if annualize:
        annualize_factor = np.sqrt(365.0)
        for i in range(n):
            if not np.isnan(vol[i]):
                vol[i] = vol[i] * annualize_factor

    # 標準化
    signal = raw_signal.copy()
    if standardize == "rank":
        signal = _expanding_zscore(signal)

    valid_signal = signal[~np.isnan(signal)]
    meta = {
        "factor": "F6_Return_Asymmetry_Premium",
        "skew_window": skew_window,
        "vol_window": vol_window,
        "ema_halflife": ema_halflife,
        "annualize": annualize,
        "signal_mean": float(np.nanmean(signal)) if len(valid_signal) > 0 else None,
        "signal_std": float(np.nanstd(signal)) if len(valid_signal) > 0 else None,
        "n_valid": int((~np.isnan(signal)).sum()),
    }

    return {
        "signal": signal,
        "raw_signal": raw_signal,
        "skew": skew,
        "vol": vol,
        "meta": meta,
    }


__all__ = ["compute", "return_asymmetry_premium"]
