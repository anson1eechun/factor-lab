"""
FSIM_CalmStreak — 逐幣低波動 regime 持續度(per-coin calm-streak)
--------------------------------------------------------------------------
Hypothesis (per-coin):
    幣的波動率呈現 regime 群聚。當短窗實現波動相對長窗壓縮(vol ratio < 1)
    且落在自身近 120 日的低百分位時,視為「低波動(calm)regime」。calm 連續
    天數愈長、壓縮愈深,代表 regime 愈穩固;以此持續度作為訊號。

Formula (per-coin):
    ret    = log(close).diff()
    RV_s   = std(ret, w_short)                 # 短窗實現波動
    RV_l   = std(ret, w_long)                  # 長窗實現波動
    vr     = RV_s / (RV_l + 1e-12)             # vol ratio,<1 = 壓縮
    p      = pct_rank(vr, pct_win)             # vr 的 120d 百分位
    calm   = 1{p < calm_thr}                   # 低波動 regime 旗標
    grp    = cumsum(calm == 0)                 # regime 分段
    streak = clip(cumsum_within_grp(calm), 0, streak_cap)   # 連續 calm 天數
    depth  = clip(1 - p, 0, .) * calm          # 壓縮深度(僅 calm 期)
    raw    = streak * (1 + depth)
    signal = raw.shift(1)

Anti look-ahead: 所有 rolling/cumsum 僅用 ≤t 資訊;最終整條 shift(1)。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    w_short: int = 5,
    w_long: int = 60,
    pct_win: int = 120,
    calm_thr: float = 0.40,
    streak_cap: int = 20,
    **_: object,
) -> pd.Series:
    c = ohlcv_df["close"].astype(float).reset_index(drop=True)
    ret = np.log(c).diff()
    RV_s = ret.rolling(w_short).std(ddof=1)
    RV_l = ret.rolling(w_long).std(ddof=1)
    vr = RV_s / (RV_l + 1e-12)
    p = vr.rolling(pct_win).rank(pct=True)
    calm = (p < calm_thr).astype(float)
    grp = (calm == 0).cumsum()
    streak = calm.groupby(grp).cumsum().clip(upper=streak_cap)
    depth = (1.0 - p).clip(lower=0) * calm
    raw = streak * (1.0 + depth)
    return raw.shift(1).reindex(range(len(ohlcv_df))).reset_index(drop=True)
