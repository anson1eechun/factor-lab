"""
FSIM_VenueMigration — Venue-Clientele Migration(場所客群遷移)
=============================================================
預註冊規格:empirical_runs/SIM-2026-08-14-001_prereg.md(凍結,commit bacaea5)§4/§5。

公式(逐字照 §4):
    dv_bn = volume_bn * close_bn              (Binance,universe_1d.pkl)
    dv_cb = volume_cb * close_cb              (Coinbase,coinbase_1d.pkl,僅供訊號)
    兩所日期以共同 UTC 日曆 inner join,缺值不前填
    S_bn  = dv_bn.rolling(w).sum()            w = 7
    S_cb  = dv_cb.rolling(w).sum()
    share = S_cb / (S_cb + S_bn),clip [0.001, 0.999]
    s     = log(share / (1 - share))
    raw   = s[t] - s[t-d]                      d = 28
    過濾(當日):(a) 過去 63 日兩所皆有值日數 >= 60
               (b) S_cb >= 100,000 USD
               (c) 當日通過幣數 >= 30,否則整列 NaN(該日不交易)
    橫截面標準化:當日 raw 取 rank -> 均勻 -> norm.ppf((rank - 0.5) / N)
    方向:高分 = 做多(符號寫死,不接受翻轉救援)

Anti look-ahead / shift 約定:
    所有 rolling / diff 只使用 <= t 的資料。
    **panel() 回傳的是 t 日(收盤後)可得的訊號,未做任何 shift。**
    規格 §4.11 = 「t 日收盤成訊號、t+1 日收盤建倉」,該 shift 由 runner
    (scripts/venue_migration_20260814.py)統一施加(S.shift(1) 後與當日
    fwd = close(t+1)/close(t) - 1 對齊)。訊號模組本身不 shift,以免重複滯後。

funding 不進訊號(§1/§7):funding 只在 runner 的 P&L 現金流腿記帳。
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from scipy import stats

_ER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "empirical_runs")
UNIVERSE_PKL = os.path.join(_ER, "universe_1d.pkl")
COINBASE_PKL = os.path.join(_ER, "coinbase_1d.pkl")

MIN_COINS = 30          # §4.7(c) minN
CLIP_LO, CLIP_HI = 0.001, 0.999

_PANEL_CACHE: dict = {}


def _dollar_volume(book: dict) -> pd.DataFrame:
    """dict[coin] -> DataFrame(timestamp ms, ..., close, volume)  =>  DataFrame(date x coin) 美元成交額。"""
    cols = {}
    for coin, df in book.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
        cols[coin] = pd.Series((df["close"].astype(float) * df["volume"].astype(float)).values, index=idx)
    return pd.DataFrame(cols).sort_index()


def dollar_volumes(universe=None, coinbase=None):
    """回傳 (dv_bn, dv_cb),已對齊到兩所共同 UTC 日曆(inner join,缺值不前填)。"""
    if universe is None:
        universe = pd.read_pickle(UNIVERSE_PKL)
    if coinbase is None:
        coinbase = pd.read_pickle(COINBASE_PKL)
    coins = sorted(set(universe) & set(coinbase))
    bn = _dollar_volume({c: universe[c] for c in coins})
    cb = _dollar_volume({c: coinbase[c] for c in coins})
    idx = bn.index.intersection(cb.index)
    bn = bn.reindex(idx)[coins]
    cb = cb.reindex(idx)[coins]
    both = bn.notna() & cb.notna()
    return bn.where(both), cb.where(both)


def rank_z(raw_row: pd.Series) -> pd.Series:
    """§4.8:rank -> 均勻 -> norm.ppf((rank - 0.5) / N)。"""
    r = raw_row.rank(method="average")
    n = int(r.notna().sum())
    return pd.Series(stats.norm.ppf((r.values - 0.5) / n), index=raw_row.index)


def panel(universe=None, coinbase=None, w: int = 7, d: int = 28, min_cb_usd: float = 1e5,
          cov_win: int = 63, cov_min: int = 60, **_) -> pd.DataFrame:
    """回傳 index=UTC 日期(normalize)、columns=幣、值= t 日橫截面 rank-z 訊號(未 shift)。"""
    dv_bn, dv_cb = dollar_volumes(universe, coinbase)

    S_bn = dv_bn.rolling(w).sum()
    S_cb = dv_cb.rolling(w).sum()
    share = (S_cb / (S_cb + S_bn)).clip(CLIP_LO, CLIP_HI)
    s = np.log(share / (1.0 - share))
    raw = s - s.shift(d)

    cover = (dv_bn.notna() & dv_cb.notna()).astype(float).rolling(cov_win).sum()
    ok = raw.notna() & (cover >= cov_min) & (S_cb >= min_cb_usd)
    raw = raw.where(ok)
    raw = raw.where(raw.notna().sum(axis=1) >= MIN_COINS)

    z = raw.apply(rank_z, axis=1)
    return z.where(raw.notna())


def _cached_panel() -> pd.DataFrame:
    if "z" not in _PANEL_CACHE:
        _PANEL_CACHE["z"] = panel()
    return _PANEL_CACHE["z"]


def factor(ohlcv_df: pd.DataFrame, coin: str | None = None, **_) -> pd.Series:
    """契約相容包裝:回傳與 ohlcv_df 等長、對齊其列順序的 Series(取自 panel 該幣欄)。

    未指定 coin 或該幣不在 panel 內 -> 全 NaN。與 panel() 相同,**不 shift**。
    """
    idx = pd.to_datetime(ohlcv_df["timestamp"], unit="ms").dt.normalize()
    z = _cached_panel()
    if coin is None or coin not in z.columns:
        return pd.Series(np.nan, index=ohlcv_df.index, name="FSIM_VenueMigration")
    out = z[coin].reindex(idx.values)
    return pd.Series(out.values, index=ohlcv_df.index, name="FSIM_VenueMigration")
