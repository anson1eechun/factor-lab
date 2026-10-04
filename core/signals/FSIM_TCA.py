"""
FSIM_TCA — Tail Co-movement Asymmetry(尾部共動不對稱)
--------------------------------------------------------------------------
Hypothesis (cross-sectional):
    幣對「等權市場」在下行時的 beta 若顯著高於上行時的 beta(downside crash-beta),
    代表該幣在市場崩跌時放大虧損、上漲時跟不上 → 是不受歡迎的尾部風險特徵,
    橫截面上應有風險溢酬/定價含義。因子取 β⁻ − β⁺ 並做橫截面排序。

Formula (per-coin, conditional betas over rolling window W):
    r_i,t = C_t/C_{t-1} - 1              (逐幣日報酬)
    r_m,t                                (等權全 universe 市場報酬,外部傳入)
    在窗 W 內(只用 ≤t 的資料):
      下行 D = {s in window : r_m,s < 0}: β⁻ = Cov(r_i,r_m | D) / Var(r_m | D)
      上行 U = {s in window : r_m,s > 0}: β⁺ = Cov(r_i,r_m | U) / Var(r_m | U)
    TCA_t = β⁻ − β⁺
    每側至少 min_side(=20)個有效點,否則該日 NaN。

Anti look-ahead:
    rolling 視窗只含 ≤t 的報酬;算完整條 TCA 後再 .shift(1),
    使 t 日因子僅含 ≤t-1 之資訊。暖機期(資料不足)為 NaN。
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def tca_series(
    coin_close: pd.Series,
    market_ret: pd.Series,
    window: int = 90,
    min_side: int = 20,
) -> pd.Series:
    """單幣 close + 市場報酬 → TCA series(已 shift(1)、暖機 NaN)。"""
    coin_close = coin_close.astype(float)
    r_i = coin_close / coin_close.shift(1) - 1.0
    r_m = market_ret.astype(float).reindex(r_i.index)

    n = len(r_i)
    ri = r_i.to_numpy()
    rm = r_m.to_numpy()
    out = np.full(n, np.nan)

    def _beta(x: np.ndarray, m: np.ndarray) -> float:
        # 對齊有效點(無 NaN)
        ok = np.isfinite(x) & np.isfinite(m)
        x, m = x[ok], m[ok]
        if x.size < min_side:
            return np.nan
        var = np.var(m)
        if not np.isfinite(var) or var <= 0:
            return np.nan
        cov = np.cov(x, m, bias=True)[0, 1]
        return cov / var

    for t in range(n):
        lo = max(0, t - window + 1)
        xi = ri[lo : t + 1]
        mi = rm[lo : t + 1]
        valid = np.isfinite(xi) & np.isfinite(mi)
        xi, mi = xi[valid], mi[valid]
        if xi.size == 0:
            continue
        down = mi < 0.0
        up = mi > 0.0
        b_dn = _beta(xi[down], mi[down])
        b_up = _beta(xi[up], mi[up])
        if np.isfinite(b_dn) and np.isfinite(b_up):
            out[t] = b_dn - b_up

    tca = pd.Series(out, index=r_i.index)
    return tca.shift(1)


def factor(
    ohlcv_df: pd.DataFrame,
    market_ret: pd.Series | None = None,
    window: int = 90,
    **_: object,
) -> pd.Series:
    """包一層 tca_series;market_ret 為 None 時用自身報酬 fallback(僅相容)。"""
    close = ohlcv_df["close"].astype(float).reset_index(drop=True)
    if market_ret is None:
        market_ret = close / close.shift(1) - 1.0
    else:
        market_ret = market_ret.reset_index(drop=True)
    s = tca_series(close, market_ret, window=window)
    return s.reset_index(drop=True)
