"""F9: cross_asset_lead_lag_coherence

Category: cross_asset
Source: candidates/F9_cross_asset_lead_lag_coherence.md

BTC → ETH lead-lag 訊號：
  coherence_t = rolling Pearson(BTC_ret[t-W:t], ETH_ret[t-W:t])
  lead_lag_signal_t = sign(BTC_ret_t) × coherence_t × |BTC_ret_t|

  - 當 |coherence_t| > threshold：訊號激活
  - 當 |coherence_t| < low_threshold：訊號靜默（ETH 獨立 regime）

前視偏誤防範：
  1. coherence_t 僅用 [t-W, t] 窗口（rolling，無未來資料）
  2. BTC_ret_t 是時間 t 的當日報酬（≤ t 資訊）
  3. 訊號對應「ETH_{t+1} 的預測」—— .shift(-1) 對齊由 empiricist 完成
     此處輸出的是 signal_t，不做 .shift
  4. coherence 的一階差 |Δρ| > 0.3 時暫停 5 日（regime 切換過濾）

多標的模式：
  若 ohlcv_df 含 BTC 與 ETH 兩個 symbol，函數自動對齊並計算跨資產訊號。
  若只傳入 ETH（或 BTC），無法計算跨資產；函數返回 NaN Series 並警告。
  目標標的（交易）= ETH；BTC 為觀察標的。
"""

import pandas as pd
import numpy as np
import warnings


def factor(
    ohlcv_df: pd.DataFrame,
    coherence_window: int = 60,
    coherence_threshold: float = 0.7,
    coherence_low: float = 0.4,
    regime_pause_days: int = 5,
    btc_symbol: str = "BTCUSDT",
    eth_symbol: str = "ETHUSDT",
) -> pd.Series:
    """計算 cross_asset_lead_lag_coherence 因子值（ETH 側訊號）。

    Parameters
    ----------
    ohlcv_df : DataFrame
        必要欄位：timestamp, symbol, open, high, low, close, volume
        必須同時包含 btc_symbol 與 eth_symbol 的行情
    coherence_window : int
        滾動 Pearson 相關性視窗（日）；預設 60
    coherence_threshold : float
        訊號激活門檻（預設 0.7；|coherence| > 此值才發訊號）
    coherence_low : float
        靜默門檻（預設 0.4；|coherence| < 此值時強制靜默）
    regime_pause_days : int
        coherence 一階差 |Δρ| > 0.3 時暫停幾日（預設 5）
    btc_symbol : str
        BTC 標的名稱（預設 "BTCUSDT"）
    eth_symbol : str
        ETH 標的名稱（預設 "ETHUSDT"）

    Returns
    -------
    pd.Series
        index 與 ohlcv_df 的 ETH 行對應（BTC 行填 NaN）
        正值 → 預期 ETH_{t+1} 正報酬（BTC_t 為正且 coherence 高）
        負值 → 預期 ETH_{t+1} 負報酬（BTC_t 為負且 coherence 高）
        0 / NaN → 靜默（coherence 低或 regime 切換中）
    """
    df = ohlcv_df.copy()

    # ── 先確認兩個標的均存在 ─────────────────────────────────────────────
    symbols = df["symbol"].unique() if "symbol" in df.columns else []
    if btc_symbol not in symbols or eth_symbol not in symbols:
        warnings.warn(
            f"F9: ohlcv_df 必須同時包含 {btc_symbol} 與 {eth_symbol}；"
            "返回全 NaN Series。",
            stacklevel=2,
        )
        return pd.Series(np.nan, index=df.index, name="F9_cross_asset_lead_lag")

    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    # ── 抽取兩個標的的日線收盤報酬 ──────────────────────────────────────
    btc = (
        df[df["symbol"] == btc_symbol]
        .set_index("timestamp")[["close"]]
        .rename(columns={"close": "btc_close"})
    )
    eth = (
        df[df["symbol"] == eth_symbol]
        .set_index("timestamp")[["close"]]
        .rename(columns={"close": "eth_close"})
    )

    # 以 timestamp 對齊（inner join，保留共同時間點）
    aligned = btc.join(eth, how="inner").sort_index()

    # ── 對數報酬（ t 時用 t-1 close，.shift(1) 確保無前視）──────────────
    btc_ret = np.log(aligned["btc_close"] / aligned["btc_close"].shift(1))
    eth_ret = np.log(aligned["eth_close"] / aligned["eth_close"].shift(1))
    btc_ret.iloc[0] = np.nan
    eth_ret.iloc[0] = np.nan

    # ── 滾動 Pearson coherence（只用 [t-W, t] 資料，無前視）──────────────
    coherence = btc_ret.rolling(coherence_window, min_periods=max(10, coherence_window // 3)).corr(eth_ret)

    # ── Regime 切換過濾：|Δρ| > 0.3 → 暫停 regime_pause_days 日 ─────────
    delta_rho = coherence.diff().abs()
    regime_switch = delta_rho > 0.3
    # 展開暫停窗口：若任一日 regime_switch=True，後續 pause_days 日均靜默
    pause_mask = regime_switch.rolling(regime_pause_days, min_periods=1).max().astype(bool)

    # ── 訊號核心：BTC_t 報酬 × coherence_t ──────────────────────────────
    raw_signal = np.sign(btc_ret) * coherence * btc_ret.abs()

    # ── 條件過濾 ─────────────────────────────────────────────────────────
    # 1. coherence < low_threshold → 靜默
    silence_mask = coherence.abs() < coherence_low
    # 2. coherence < activation threshold → 弱化為 0
    below_threshold = coherence.abs() < coherence_threshold

    signal = raw_signal.copy()
    signal[silence_mask]     = 0.0   # 完全靜默
    signal[below_threshold]  = signal[below_threshold] * 0.5  # 降權但不清零
    signal[pause_mask]       = 0.0   # regime 切換暫停

    # ── 對齊回原始 df 的 index ───────────────────────────────────────────
    # signal.index 是 timestamp；需映射回 df 中 ETH 行的 integer index
    eth_rows = df[df["symbol"] == eth_symbol].copy()
    eth_rows = eth_rows.set_index("timestamp")
    eth_rows["_signal"] = signal.reindex(eth_rows.index)
    eth_rows = eth_rows.reset_index()

    # 建立 timestamp → signal 的映射，再對齊回原始 df
    ts_to_signal = dict(zip(eth_rows["timestamp"], eth_rows["_signal"]))
    out = pd.Series(np.nan, index=df.index, name="F9_cross_asset_lead_lag")
    eth_idx = df[df["symbol"] == eth_symbol].index
    out.loc[eth_idx] = df.loc[eth_idx, "timestamp"].map(ts_to_signal).values

    return out
