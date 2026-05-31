"""
F1: Complexity_Gap_Regime — 市場複雜度相位切換因子（單品種適應版）

原始 RMT 方法需要多資產相關矩陣，本實作針對單品種 (BTCUSDT) 進行適配：
使用滑動視窗內多個子區段的收益率自相關矩陣近似替代跨資產相關矩陣。

經濟直覺：
- Δ (複雜度間隙) 量化市場從「隨機漫步」偏離的程度
- Δ ≈ 0：無序相位，均值回歸主導 → 輸出負值（建議反轉策略）
- Δ 中等：臨界相位，信號模糊 → 輸出接近 0（收緊進場）
- Δ ≫ 0：有序相位，趨勢/動能主導 → 輸出正值（建議趨勢策略）

無前視偏誤：僅使用 t 時刻及之前的資料。
輸出：cross-sectional rank 標準化（單品種下為 rolling z-score）。

參考文獻：
- Laloux et al. (1999) "Noise Dressing of Financial Correlation Matrices"
- Plerou et al. (2002) "Random Matrix Approach to Cross Correlations in Financial Data"
"""

from __future__ import annotations
import numpy as np
from numpy.linalg import eigh


def _safe_log_returns(close_prices: np.ndarray) -> np.ndarray:
    """計算對數收益率，處理缺失值與非正值。"""
    prices = np.asarray(close_prices, dtype=np.float64)
    # 向前填充缺失值
    mask = np.isnan(prices) | (prices <= 0)
    if mask.any():
        # 用前一個有效值填充
        valid = np.where(~mask)[0]
        if len(valid) == 0:
            return np.full(len(prices) - 1, np.nan)
        for i in range(len(prices)):
            if mask[i]:
                # 找前一個有效值
                prev = valid[valid < i]
                if len(prev) > 0:
                    prices[i] = prices[prev[-1]]
                else:
                    prices[i] = prices[valid[0]]
    log_p = np.log(prices)
    return np.diff(log_p)


def _form_lagged_correlation_matrix(returns: np.ndarray, n_components: int) -> np.ndarray:
    """
    從單一資產的收益率序列建立自相關矩陣（子區段相關性矩陣）。
    
    將長度為 N 的收益率序列切割為 n_components 個重疊子區段，
    計算子區段間的相關係數矩陣，用於 RMT 分析。
    
    Args:
        returns: 長度為 N 的收益率序列
        n_components: 虛擬資產數量（子區段數目）
    
    Returns:
        (n_components, n_components) 相關矩陣
    """
    n = len(returns)
    if n < n_components + 5:
        # 資料不足，回退到單位矩陣
        return np.eye(n_components)
    
    sub_len = n - n_components + 1  # 每個子區段長度
    if sub_len < 3:
        return np.eye(n_components)
    
    # 建立子區段矩陣 (n_components, sub_len)
    subs = np.zeros((n_components, sub_len))
    for i in range(n_components):
        subs[i] = returns[i:i + sub_len]
    
    # 標準化每個子區段
    subs_mean = subs.mean(axis=1, keepdims=True)
    subs_std = subs.std(axis=1, keepdims=True)
    subs_std[subs_std < 1e-12] = 1.0
    subs_norm = (subs - subs_mean) / subs_std
    
    # 相關矩陣 C = (1/sub_len) * S * S^T
    C = np.dot(subs_norm, subs_norm.T) / (sub_len - 1)
    
    # 確保對稱且對角線為 1
    C = 0.5 * (C + C.T)
    np.fill_diagonal(C, 1.0)
    
    # 數值穩定性：clip 到 [-1, 1]
    C = np.clip(C, -1.0, 1.0)
    
    return C


def complexity_gap_signal(
    close_prices: np.ndarray,
    window: int = 60,
    n_components: int = 10,
    shrinkage: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """
    計算 Complexity Gap 信號序列。
    
    Args:
        close_prices: 收盤價序列 (length >= window+1)
        window: 滾動視窗長度 K 線數 (預設 60)
        n_components: 虛擬資產數目，即自相關矩陣維度 (預設 10)
        shrinkage: 是否使用 Ledoit-Wolf 型收縮估計 (預設 True)
    
    Returns:
        (signal, delta): 
          - signal: 標準化後的信號序列 [-1, 1]，正值代表有序/趨勢市
          - delta: 原始複雜度間隙 Δ 序列
    """
    returns = _safe_log_returns(close_prices)
    n = len(returns)
    
    if n < window + 2:
        return np.full(n, np.nan), np.full(n, np.nan)
    
    deltas = np.full(n, np.nan)
    signals = np.full(n, np.nan)
    
    for t in range(window - 1, n):
        r_window = returns[t - window + 1:t + 1]  # window 個收益率
        
        # 檢查資料品質
        if np.any(np.isnan(r_window)) or len(r_window) < window:
            continue
        
        # 建立自相關矩陣
        C = _form_lagged_correlation_matrix(r_window, n_components)
        
        # 收縮估計（簡單版本：朝單位矩陣收縮）
        if shrinkage and n_components > 1:
            shrinkage_intensity = min(0.3, n_components / (window * 2))
            C = (1 - shrinkage_intensity) * C + shrinkage_intensity * np.eye(n_components)
        
        # 計算特徵值
        try:
            eigvals = eigh(C)[0]  # eigenvalues in ascending order
        except np.linalg.LinAlgError:
            continue
        
        # 最大特徵值標準化
        lambda_max_norm = eigvals[-1] / np.sum(eigvals)
        rho = 1.0 / n_components  # 均勻分佈基準
        
        delta = lambda_max_norm - rho
        deltas[t] = delta
        
        # 信號：Δ 轉換為 [-1, 1] 範圍的連續信號
        # Δ < 0.02 → 無序 (負信號), Δ >= 0.05 → 有序 (正信號)
        signal = np.clip((delta - 0.035) / 0.04, -1.0, 1.0)
        signals[t] = signal
    
    return signals, deltas


def _expanding_zscore(signal: np.ndarray) -> np.ndarray:
    """Expanding-window z-score 標準化（無前視偏誤）。

    每個時間點 t 的標準化僅使用 [0, t] 範圍內的已觀測資料。
    第一個有效值之後才能開始標準化。
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
            result[i] = 0.0  # 第一個有效值，無法標準化
            continue

        mean = running_sum / count
        variance = (running_sum_sq / count) - mean * mean
        std = np.sqrt(max(variance, 1e-12))
        result[i] = (val - mean) / std

    return np.clip(result, -4.0, 4.0)


def compute(
    ohlcv_data: list[dict],
    window: int = 60,
    n_components: int = 10,
    standardize: str = "rank",
) -> dict:
    """
    F1 Complexity Gap Regime 因子入口函數。
    
    符合 factor-lab 信號函數標準介面：
    - 輸入: OHLCV 資料列表 [{ts, open, high, low, close, volume}, ...]
    - 輸出: dict with 'signal' (np.ndarray), 'meta'
    
    Args:
        ohlcv_data: OHLCV 資料（時間升冪）
        window: RMT 視窗長度
        n_components: 虛擬資產數
        standardize: 標準化方式 ('rank' = cross-sectional rank)
    
    Returns:
        {'signal': np.ndarray, 'delta': np.ndarray, 'regime': np.ndarray, 'meta': dict}
    """
    closes = np.array([d["close"] for d in ohlcv_data], dtype=np.float64)
    
    sig_raw, delta_raw = complexity_gap_signal(
        closes, window=window, n_components=n_components
    )
    
    # complexity_gap_signal 回傳長度 n-1 (因 log returns 減少一個觀測值)
    # 補回 NaN 對齊原始 OHLCV 長度
    signal = np.full(len(closes), np.nan)
    delta = np.full(len(closes), np.nan)
    signal[1:] = sig_raw
    delta[1:] = delta_raw
    
    # 相位分類
    regime = np.full(len(signal), "", dtype=object)
    for i, d in enumerate(delta):
        if np.isnan(d):
            regime[i] = "unknown"
        elif d < 0.02:
            regime[i] = "disordered"   # 無序相位 → 均值回歸
        elif d < 0.05:
            regime[i] = "critical"     # 臨界相位 → 收緊進場
        else:
            regime[i] = "ordered"      # 有序相位 → 趨勢追隨
    
    # 標準化：使用 expanding-window z-score 以避免前視偏誤
    # 每個時間點的標準化只使用 t 及之前的資料
    if standardize == "rank":
        signal = _expanding_zscore(signal)
    
    meta = {
        "factor": "F1_Complexity_Gap_Regime",
        "window": window,
        "n_components": n_components,
        "regime_counts": {
            "disordered": int(np.sum(regime == "disordered")),
            "critical": int(np.sum(regime == "critical")),
            "ordered": int(np.sum(regime == "ordered")),
            "unknown": int(np.sum(regime == "unknown")),
        },
    }
    
    return {"signal": signal, "delta": delta, "regime": regime, "meta": meta}


__all__ = ["compute", "complexity_gap_signal"]
