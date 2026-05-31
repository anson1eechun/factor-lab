"""F7: session_gap_momentum_decomposition

Category: microstructure
Source: candidates/F7_session_gap_momentum_decomposition.md

將 24H 報酬分解為：
  - session_gap_return：跨 session 缺口（跨時區資訊衝擊）
  - intra_session_drift：session 內漂移（連續做市）
計算 gap_ratio（缺口佔比）與 sign_concordance（符號一致性）

日線降級模式（預設）：
  gap_return_t  = (open_t - close_{t-1}) / close_{t-1}
  intra_t       = (close_t  - open_t)    / open_t
  daily_return_t = (close_t - close_{t-1}) / close_{t-1}

  gap_ratio_t   = |gap_return_t| / (|daily_return_t| + 1e-8)
  sign_conc_t   = sign(gap_return_t) × sign(intra_t)   （+1 同向 / -1 反向）

  訊號 = smoothed_gap_ratio × sign_concordance
        （高 gap_ratio + 同向 → 正值；高 gap_ratio + 反向 → 負值）
"""

import pandas as pd
import numpy as np


def factor(
    ohlcv_df: pd.DataFrame,
    smoothing_window: int = 10,
    atr_filter_sigma: float = 3.0,
) -> pd.Series:
    """計算 session_gap_momentum_decomposition 因子值。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, symbol, open, high, low, close, volume
    smoothing_window : int
        gap_ratio 滾動平均視窗（預設 10 日，候選筆記 Q3 建議 {5,10,20}）
    atr_filter_sigma : float
        ATR 標準化後超過此 σ 的缺口予以 winsorize（預設 3.0）

    Returns
    -------
    pd.Series
        index 與 ohlcv_df 一致；值域大致在 [-1, 1]
        正值 = 缺口主導 + 同向漂移（跨時區資訊推動真趨勢）
        負值 = 缺口主導 + 反向漂移（缺口被回補）
        接近 0 = 低缺口比例（日內 FOMO 主導，訊號意義低）
    """
    df = ohlcv_df.copy()

    # ── 確保依 (symbol, timestamp) 排序，避免前視偏誤 ──────────────────────
    if "symbol" in df.columns:
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        grp = df.groupby("symbol", group_keys=False)
    else:
        df = df.sort_values("timestamp").reset_index(drop=True)
        grp = None

    def _compute_group(g: pd.DataFrame) -> pd.Series:
        g = g.copy()

        # ── 使用 t-1 的 close（.shift(1)），杜絕前視偏誤 ─────────────────
        prev_close = g["close"].shift(1)          # close_{t-1}：只用過去資料
        open_t     = g["open"]                    # open_t：當日開盤，≤ t 資訊

        # ── 日線降級近似（開-收、收-收）──────────────────────────────────
        gap_return   = (open_t - prev_close) / (prev_close + 1e-8)   # 跨 session 缺口
        intra_return = (g["close"] - open_t) / (open_t + 1e-8)       # 日內漂移
        daily_return = (g["close"] - prev_close) / (prev_close + 1e-8)  # 24H 報酬

        # ── ATR 標準化：winsorize 極端缺口（Flash crash 等） ─────────────
        tr = pd.concat([
            g["high"] - g["low"],
            (g["high"] - prev_close).abs(),
            (g["low"]  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=5).mean()
        atr_std = atr.rolling(60, min_periods=20).std()

        # 只在 ATR std 非零時做 winsorize
        valid_atr_std = atr_std.fillna(atr_std.median())
        upper = atr_filter_sigma * valid_atr_std
        gap_return_clipped = gap_return.clip(
            lower=-upper.values, upper=upper.values
        )

        # ── 成交量過濾：量 < 5th percentile 時該列設 NaN ──────────────────
        vol_floor = g["volume"].rolling(20, min_periods=10).quantile(0.05)
        low_vol_mask = g["volume"] < vol_floor

        # ── gap_ratio：缺口幅度佔日報酬比例 ─────────────────────────────
        gap_ratio = gap_return_clipped.abs() / (daily_return.abs() + 1e-8)
        gap_ratio = gap_ratio.clip(0, 2)   # 上限 2（避免分母接近 0 的噪音）

        # ── sign_concordance：缺口與日內漂移的符號一致性 ─────────────────
        sign_gap   = np.sign(gap_return_clipped)
        sign_intra = np.sign(intra_return)
        sign_conc  = sign_gap * sign_intra   # +1 同向，-1 反向

        # ── 滾動平均平滑（短記憶平滑；不使用未來資料）────────────────────
        smooth_gap_ratio = gap_ratio.rolling(
            smoothing_window, min_periods=max(1, smoothing_window // 2)
        ).mean()

        # ── 合成訊號 ──────────────────────────────────────────────────────
        raw_signal = smooth_gap_ratio * sign_conc

        # ── 低成交量日置 NaN ──────────────────────────────────────────────
        raw_signal[low_vol_mask] = np.nan

        # ── 截面排名（單標的時退化為 time-series rank）────────────────────
        # 此處先返回 raw；截面排名由 empiricist 的 cross-sectional rank 完成
        return raw_signal

    if grp is not None and df["symbol"].nunique() > 1:
        # 多標的：分組計算後拼合
        pieces = []
        for sym, g in df.groupby("symbol", sort=False):
            pieces.append(_compute_group(g))
        result = pd.concat(pieces).reindex(df.index)
    else:
        # 單標的或無 symbol 欄位：直接計算
        result = _compute_group(df)

    return result
