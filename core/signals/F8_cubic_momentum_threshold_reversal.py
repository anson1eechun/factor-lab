"""F8: cubic_momentum_threshold_reversal

Category: momentum
Source: candidates/F8_cubic_momentum_threshold_reversal.md

Cubic Momentum Indicator (CMI)：
  M_t = Σ_{s≤t} e^{-r(t-s)} * log_return_s        (指數加權累積動量)
  CMI_t = (M_t - a)(M_t - b)(M_t - c)

  三個根 a < b < c 從 M 的滾動分布取分位數：
    a = rolling 5th  percentile  （超賣閾值）
    b = rolling 75th percentile  （過熱閾值）
    c = rolling 95th percentile  （極端過熱閾值）

  符號解讀：
    CMI > 0 且 M ∈ (a, b)：健康動量，follow trend
    CMI < 0 且 M ∈ (b, c)：過熱反轉，做空訊號
    M > c 或 M < a         ：極端區間，CMI 翻號，噪音較大

前視偏誤防範：
  - M_t 在時間 t 使用 ≤ t 的 log returns（EWM 天然累積，無未來洩漏）
  - a/b/c 從 rolling(252) 計算，整個視窗均在 t 之前（無 .shift 需求因為
    pd.Series.quantile 不使用 t+1）
  - 最終輸出不作任何 .shift；shift 由 empiricist 在對齊未來報酬時完成
"""

import pandas as pd
import numpy as np


# 半衰期預設 14 日（候選筆記 Q3 建議 {7,14,21}）
_HALFLIFE_DEFAULT = 14
_LOOKBACK = 252  # 滾動分位數視窗


def factor(
    ohlcv_df: pd.DataFrame,
    halflife: int = _HALFLIFE_DEFAULT,
    lookback: int = _LOOKBACK,
    q_low: float = 0.05,
    q_mid: float = 0.75,
    q_high: float = 0.95,
) -> pd.Series:
    """計算 cubic_momentum_threshold_reversal 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, symbol, open, high, low, close, volume
    halflife : int
        M_t 指數加權動量的半衰期（日），r = log(2) / halflife
    lookback : int
        計算 a/b/c 分位數的滾動視窗（預設 252 日）
    q_low : float
        a = M 的 q_low 分位數（超賣閾值，預設 5%）
    q_mid : float
        b = M 的 q_mid 分位數（過熱閾值，預設 75%）
    q_high : float
        c = M 的 q_high 分位數（極端過熱閾值，預設 95%）

    Returns
    -------
    pd.Series
        index 與 ohlcv_df 一致
        正值 + M ∈ (a, b)：健康動量（跟隨趨勢）
        負值 + M ∈ (b, c)：過熱反轉（做空）
        極端值（M > c 或 M < a）：噪音區，empiricist 需額外過濾
    """
    df = ohlcv_df.copy()

    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        grp = df.groupby("symbol", group_keys=False)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)
        grp = None

    # 衰減率
    r = np.log(2) / halflife

    def _compute_group(g: pd.DataFrame) -> pd.Series:
        g = g.copy()

        # ── 對數報酬（時間 t，使用 t-1 close→t close，無前視） ────────────
        log_ret = np.log(g["close"] / g["close"].shift(1))
        log_ret.iloc[0] = 0.0   # 第一行設 0

        # ── 指數加權累積動量 M_t ───────────────────────────────────────────
        # EWM span 與 halflife 的對應：span = 2*halflife - 1（近似）
        # 但 com = 1/(e^r - 1) 更精確對應連續衰減
        com = 1.0 / (np.exp(r) - 1.0)
        M = log_ret.ewm(com=com, min_periods=1, adjust=False).mean()
        # 注意：ewm.mean() 是加權「均值」而非累積和，但量綱一致、方向相同
        # 若需嚴格「累積和」可用：M = log_ret.ewm(span=...).sum()，但 pandas
        # 不直接提供 ewm.sum()；用 mean 乘以等效長度近似，效果相當
        # → 此處保持 ewm.mean() 以確保數值穩定，empiricist 以排名標準化

        # ── 滾動分位數計算 a/b/c（只用 ≤ t 歷史資料，無前視偏誤） ──────
        a = M.rolling(lookback, min_periods=max(20, lookback // 10)).quantile(q_low)
        b = M.rolling(lookback, min_periods=max(20, lookback // 10)).quantile(q_mid)
        c = M.rolling(lookback, min_periods=max(20, lookback // 10)).quantile(q_high)

        # ── CMI = (M - a)(M - b)(M - c) ──────────────────────────────────
        cmi = (M - a) * (M - b) * (M - c)

        # ── Winsorize CMI（防極端值主導排名）────────────────────────────
        cmi_std = cmi.rolling(lookback, min_periods=20).std()
        cmi_clipped = cmi.clip(
            lower=(-3 * cmi_std).values,
            upper=( 3 * cmi_std).values,
        )

        return cmi_clipped

    if grp is not None and df["symbol"].nunique() > 1:
        pieces = []
        for sym, g in df.groupby("symbol", sort=False):
            pieces.append(_compute_group(g))
        result = pd.concat(pieces).reindex(df.index)
    else:
        result = _compute_group(df)

    return result
