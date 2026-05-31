"""
factor-lab 信號函數模組。

每個因子以 compute() 作為標準入口函數：
  - 輸入: ohlcv_data (list[dict])
  - 輸出: dict with 'signal' (np.ndarray), 'meta' (dict)

因子清單：
  - F1_Complexity_Gap_Regime:   市場複雜度相位切換（RMT 自相關矩陣）
  - F2_Liquidity_Consumption_Tilt: 流動性消耗方向傾斜（OHLCV 近似）
  - F3_Volatility_Roughness_Filter: 波動率粗糙度體制過濾（DFA Hurst）
"""

from core.signals import (  # noqa: F401
    F1_Complexity_Gap_Regime,
    F2_Liquidity_Consumption_Tilt,
    F3_Volatility_Roughness_Filter,
)
