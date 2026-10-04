"""
FSIM_HollowLeverage — 空心槓桿(Hollow Leverage,cross-sectional)
--------------------------------------------------------------------------
Hypothesis (cross-sectional):
    資費(funding)相對同儕加速上升、但價格未同步跟漲的幣,代表槓桿多頭
    堆積卻缺乏現貨買盤支撐(「空心」槓桿)→ 後續橫截面相對報酬為負(short);
    反之資費相對降溫而價格未弱者為 long。因子 = 「資費加速度」對價格動能
    與資費水位做當日橫截面正交化後之殘差,取負號。

Formula (panel,每日橫截面;一切只用 ≤t 資訊):
    f3_t    = funding.rolling(smooth=3, min_periods=3).mean()
    dF_t    = f3_t − f3_{t−7}                     (= f3.diff(dwin=7))
    r7_t    = ln C_t − ln C_{t−7}                 (= ln(close).diff(7))
    r7lag_t = ln C_{t−7} − ln C_{t−14}            (= r7.shift(7))
    當日有效幣 = {dF, r7, r7lag, f3} 四者皆 finite;
    有效幣數 N < min_coins(40) → 該日整列 NaN。
    均勻 rank 變換  u(x) = (rank(x) − (N+1)/2) / N   (rank 用 average ties)
    當日 OLS(截距 + 3 控制,np.linalg.lstsq):
        u(dF) = a + b1·u(r7) + b2·u(r7lag) + b3·u(f3) + ε
    原始訊號  s_{i,t} = −ε_{i,t}

    宇宙 = 價格檔與資費檔幣種交集;所有序列先轉 DatetimeIndex
    (pd.to_datetime(ts, unit="ms"))再對齊共同日索引。
    預註冊參數(寫死為預設):smooth=3, dwin=7, min_coins=40。

Anti look-ahead:
    rolling / diff / shift 全為 backward-looking;橫截面回歸只用當日資料;
    全 matrix 建完後 S = S.shift(1),使 t 日欄位僅含 ≤t−1 之資訊。
    暖機期(r7lag 需 14 天等)與資料不足日為 NaN。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _to_daily(df: pd.DataFrame, col: str) -> pd.Series:
    """timestamp(ms) 欄 → 以 DatetimeIndex 為索引的日序列(升冪、去重)。"""
    ts = pd.to_datetime(df["timestamp"], unit="ms")
    s = pd.Series(df[col].astype(float).to_numpy(), index=ts)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _urank(x: np.ndarray) -> np.ndarray:
    """均勻 rank 變換:u = (rank − (N+1)/2)/N,rank 用 average ties。"""
    r = pd.Series(x).rank(method="average").to_numpy()
    n = x.size
    return (r - (n + 1) / 2.0) / n


def _prepare_panels(
    uni: dict, fund: dict, smooth: int, dwin: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """交集宇宙 → 對齊共同日索引 → 回傳 (dF, r7, r7lag, f3) 四個 panel。"""
    coins = sorted(set(uni) & set(fund))
    close = {c: _to_daily(uni[c], "close") for c in coins}
    fnd = {c: _to_daily(fund[c], "funding") for c in coins}
    idx = pd.DatetimeIndex(sorted(set().union(*(s.index for s in close.values()))))
    logc = np.log(pd.DataFrame({c: close[c].reindex(idx) for c in coins}))
    f = pd.DataFrame({c: fnd[c].reindex(idx) for c in coins})
    f3 = f.rolling(smooth, min_periods=smooth).mean()
    dF = f3.diff(dwin)
    r7 = logc.diff(dwin)
    r7lag = r7.shift(dwin)
    return dF, r7, r7lag, f3


def build_signal_matrix(
    uni: dict,
    fund: dict,
    smooth: int = 3,
    dwin: int = 7,
    min_coins: int = 40,
) -> pd.DataFrame:
    """建完整 panel 訊號 S(index=日 DatetimeIndex,columns=幣,已 shift(1))。"""
    dF, r7, r7lag, f3 = _prepare_panels(uni, fund, smooth, dwin)
    arrs = [x.to_numpy() for x in (dF, r7, r7lag, f3)]
    S = np.full(arrs[0].shape, np.nan)
    for t in range(S.shape[0]):
        rows = [a[t] for a in arrs]
        ok = np.isfinite(rows[0])
        for v in rows[1:]:
            ok &= np.isfinite(v)
        n = int(ok.sum())
        if n < min_coins:
            continue
        u = [_urank(v[ok]) for v in rows]
        y = u[0]
        X = np.column_stack([np.ones(n), u[1], u[2], u[3]])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        S[t, ok] = -(y - X @ beta)
    out = pd.DataFrame(S, index=dF.index, columns=dF.columns)
    return out.shift(1)


def factor(
    ohlcv_df: pd.DataFrame,
    funding: pd.Series | pd.DataFrame | None = None,
    smooth: int = 3,
    dwin: int = 7,
    **_: object,
) -> pd.Series:
    """契約相容之單幣退化版:僅回傳 per-coin 資費加速度成分 (−dF).shift(1)。

    完整因子需對整個 universe 做當日橫截面殘差化(u-rank + OLS 去除
    r7 / r7lag / f3),請用 build_signal_matrix;此處無同儕可比,僅供
    契約/煙霧驗證。funding 為 None 時回傳全 NaN(位置對齊,同 FSIM_TCA)。
    """
    n = len(ohlcv_df)
    if funding is None:
        return pd.Series(np.nan, index=range(n))
    if isinstance(funding, pd.DataFrame):
        funding = funding["funding"]
    f = funding.astype(float).reset_index(drop=True)
    f3 = f.rolling(smooth, min_periods=smooth).mean()
    dF = f3.diff(dwin)
    return (-dF).shift(1).reindex(range(n)).reset_index(drop=True)
