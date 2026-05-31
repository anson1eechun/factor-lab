"""
F3: Volatility_Roughness_Filter — 波動率粗糙度體制過濾器

經濟直覺：
- 粗糙波動率 (H < 0.5)：波動率具反持久性 (anti-persistent)
  波動率衝擊快速衰減 → 進場信號可信度較高，適合在波動率飆升後進場
- 平滑波動率 (H ≈ 0.5)：波動率接近隨機漫步
  高波動率區間會持續 → 應降低倉位、收緊止損
- 趨勢性波動率 (H > 0.5)：波動率具持久趨勢
  異常市場信號 → 大幅降低倉位或觀望

方法：使用 DFA (Detrended Fluctuation Analysis) 估計 Hurst 指數
基於 Parkinson 波動率估計器 (High-Low range) 計算已實現波動率

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：倉位乘數 multiplier ∈ [0.3, 1.2]，反映當前市場波動率體制下的建議倉位比例。

參考文獻：
- Gatheral, Jaisson & Rosenbaum (2018) "Volatility is Rough"
- Di Matteo, Aste & Dacorogna (2005) "Long-term Memories of Developed and Emerging Markets"
"""

from __future__ import annotations
import numpy as np


def _parkinson_volatility(highs: np.ndarray, lows: np.ndarray) -> np.ndarray:
    """
    Parkinson (1980) 波動率估計器。
    
    僅需 High/Low 價格，效率是 Close-to-Close 估計器的 5.2 倍。
    
    sigma_p = sqrt( (1 / (4 * ln(2) * N)) * sum(ln(H_i / L_i)^2) )
    
    對於每根 K 線，回傳標準化後的瞬時波動率。
    """
    h = np.asarray(highs, dtype=np.float64)
    l = np.asarray(lows, dtype=np.float64)
    
    valid = (h > 0) & (l > 0) & (~np.isnan(h)) & (~np.isnan(l))
    result = np.full(len(h), np.nan)
    
    if valid.sum() > 0:
        log_hl = np.log(h[valid] / l[valid])
        # Parkinson 常數: 1/(4*ln(2)) ≈ 0.360674
        result[valid] = np.sqrt(log_hl ** 2 / (4.0 * np.log(2.0)))
    
    return result


def _dfa_hurst(x: np.ndarray, scales: np.ndarray | None = None) -> float:
    """
    使用 Detrended Fluctuation Analysis (DFA) 估計 Hurst 指數。
    
    DFA 步驟：
    1. 計算累積離差 y(k) = sum_{i=1..k} (x_i - mean(x))
    2. 對於每個尺度 s，將 y 分割為長度 s 的視窗
    3. 在每個視窗內用線性回歸去趨勢
    4. 計算去趨勢後的 RMS: F(s)^2 = mean(residuals^2)
    5. Hurst 指數 H 是 log(F) vs log(s) 的斜率
    
    Args:
        x: 輸入序列
        scales: 分析的尺度列表 (預設: [4, 8, 16, 32])
    
    Returns:
        Hurst 指數 H (NaN if computation fails)
    """
    x = np.asarray(x, dtype=np.float64)
    x = x[~np.isnan(x)]
    
    if len(x) < 16:
        return float("nan")
    
    if scales is None:
        # 根據資料長度自適應選擇尺度
        max_scale = min(len(x) // 4, 64)
        scales = np.array([s for s in [4, 8, 16, 32, 64] if s <= max_scale])
        if len(scales) < 2:
            return float("nan")
    
    # 步驟 1: 累積離差
    y = np.cumsum(x - np.mean(x))
    n = len(y)
    
    f_vals = []
    s_vals = []
    
    for s in scales:
        s = int(s)
        if s < 4 or s > n // 2:
            continue
        
        # 分割為長度 s 的視窗
        n_segments = n // s
        if n_segments < 2:
            continue
        
        rms_sum = 0.0
        count = 0
        
        for v in range(n_segments):
            seg = y[v * s:(v + 1) * s]
            if len(seg) < 4:
                continue
            
            # 線性去趨勢
            t = np.arange(len(seg), dtype=np.float64)
            # 最小平方法線性回歸
            a = np.vstack([t, np.ones(len(seg))]).T
            try:
                coeff = np.linalg.lstsq(a, seg, rcond=None)[0]
                trend = coeff[0] * t + coeff[1]
                residuals = seg - trend
                rms_sum += np.sum(residuals ** 2)
                count += len(seg)
            except np.linalg.LinAlgError:
                continue
        
        if count > 0:
            f_vals.append(np.sqrt(rms_sum / count))
            s_vals.append(s)
    
    if len(f_vals) < 2:
        return float("nan")
    
    # 步驟 5: log-log 回歸估計 H
    log_s = np.log(np.array(s_vals))
    log_f = np.log(np.array(f_vals))
    
    # 最小平方法斜率
    n_pts = len(log_s)
    sx = np.sum(log_s)
    sy = np.sum(log_f)
    sxx = np.sum(log_s ** 2)
    sxy = np.sum(log_s * log_f)
    
    denom = n_pts * sxx - sx ** 2
    if abs(denom) < 1e-12:
        return float("nan")
    
    H = (n_pts * sxy - sx * sy) / denom
    
    return max(0.0, min(1.0, H))


def volatility_roughness_signal(
    highs: np.ndarray,
    lows: np.ndarray,
    window: int = 100,
    dfa_min_window: int = 60,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    計算波動率粗糙度過濾信號。
    
    Args:
        highs: 最高價序列
        lows: 最低價序列
        window: 滑動視窗長度 (預設 100，約對應 500 分鐘的 5-min K 線)
        dfa_min_window: DFA 分析所需最小視窗長度 (預設 60)
    
    Returns:
        (multiplier, hurst, parkinson_vol):
          - multiplier: 倉位乘數 [0.3, 1.2]
          - hurst: Hurst 指數序列
          - parkinson_vol: Parkinson 波動率序列
    """
    n = len(highs)
    
    # 計算 Parkinson 波動率
    park_vol = _parkinson_volatility(highs, lows)
    
    hurst = np.full(n, np.nan)
    multiplier = np.full(n, np.nan)
    
    # 需要足夠資料：至少 window 個有效波動率估計
    effective_window = max(window, dfa_min_window)
    
    for t in range(effective_window - 1, n):
        # 取得過去 window 個波動率觀測值
        start = max(0, t - window + 1)
        vol_window = park_vol[start:t + 1]
        valid_vol = vol_window[~np.isnan(vol_window)]
        
        if len(valid_vol) < dfa_min_window:
            continue
        
        # 計算 Hurst 指數
        H = _dfa_hurst(valid_vol)
        if np.isnan(H):
            continue
        
        hurst[t] = H
        
        # 體制判定 → 倉位乘數
        if H < 0.30:
            # 粗糙波動率：波動率衝擊快速衰減 → 進場信號可信度高
            mult = 1.20
        elif H < 0.45:
            # 中等粗糙：正常市場
            mult = 1.00
        elif H < 0.55:
            # 近隨機漫步：波動率具持久性 → 降低倉位
            mult = 0.70
        else:
            # 趨勢性波動率：異常市場 → 大幅降低倉位
            mult = 0.50
        
        multiplier[t] = mult
    
    return multiplier, hurst, park_vol


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
    window: int = 100,
    dfa_min_window: int = 60,
    standardize: str = "rank",
) -> dict:
    """
    F3 Volatility Roughness Filter 因子入口函數。
    
    符合 factor-lab 信號函數標準介面。
    
    Args:
        ohlcv_data: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
        window: Hurst 估計視窗長度
        dfa_min_window: DFA 最小有效資料點數
        standardize: 標準化方式
    
    Returns:
        {'signal': np.ndarray, 'multiplier': np.ndarray, 'hurst': np.ndarray,
         'parkinson_vol': np.ndarray, 'meta': dict}
    """
    highs = np.array([d["high"] for d in ohlcv_data], dtype=np.float64)
    lows = np.array([d["low"] for d in ohlcv_data], dtype=np.float64)
    
    multiplier, hurst, park_vol = volatility_roughness_signal(
        highs, lows, window=window, dfa_min_window=dfa_min_window
    )
    
    # 信號：將 multiplier 轉換為 [-1, 1] 範圍
    # mult ∈ [0.5, 1.2] → signal ∈ [-1, 1]
    # mult=1.0 → signal=0 (中性), mult=1.2 → signal=1 (加倉), mult=0.5 → signal=-1 (減倉)
    signal = np.full(len(multiplier), np.nan)
    valid = ~np.isnan(multiplier)
    if valid.sum() > 0:
        signal[valid] = (multiplier[valid] - 1.0) / 0.2
        # 額外懲罰 H > 0.55 的情況
        high_h = (~np.isnan(hurst)) & (hurst > 0.55)
        signal[high_h] = np.minimum(signal[high_h], -0.5)
    
    if standardize == "rank":
        signal = _expanding_zscore(signal)
    
    meta = {
        "factor": "F3_Volatility_Roughness_Filter",
        "window": window,
        "dfa_min_window": dfa_min_window,
        "hurst_mean": float(np.nanmean(hurst)) if np.any(~np.isnan(hurst)) else None,
        "hurst_std": float(np.nanstd(hurst)) if np.any(~np.isnan(hurst)) else None,
        "multiplier_range": (
            float(np.nanmin(multiplier)),
            float(np.nanmax(multiplier)),
        ) if np.any(~np.isnan(multiplier)) else (None, None),
        "n_valid": int(np.sum(~np.isnan(signal))),
    }
    
    return {"signal": signal, "multiplier": multiplier, "hurst": hurst,
            "parkinson_vol": park_vol, "meta": meta}


__all__ = ["compute", "volatility_roughness_signal", "_dfa_hurst", "_parkinson_volatility"]
