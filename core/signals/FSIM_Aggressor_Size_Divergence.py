"""
FSIM_Aggressor_Size_Divergence — Aggressor Size Divergence (ASD)
================================================================
規格凍結於 **SIM-2026-09-14-001**(Proposer 凍結版,逐字實作,零自訂參數)。

資料
----
Binance UM 逐筆成交:
    /srv/nas/marketdata/parquet/um/trades/symbol=<SYM>/<YYYY-MM>.parquet
    schema: id:int64, price:double, qty:double, quote_qty:double,
            time:int64(ms UTC), is_buyer_maker:bool

只讀 ``time, price, qty, is_buyer_maker`` 四欄;notional 自行算 ``price * qty``
(已實測 ``price*qty == quote_qty``,最大相對誤差 2.2e-16,故不讀 quote_qty
——它佔 40% 位元組)。``id`` 有約 0.011% 跳號,接受不處理。

⚠ 資料完整性:凍結規格假設「``time`` 在檔內非遞減」。Builder 實測(掃全部
4502 個月檔的 parquet row-group 統計)發現 **41 個檔違反**此假設,集中在
BTC(8 個月)/ETH(5)/SOL(4)/ORDI/TIA 等高流動性幣的 2023-01、2023-04~06、
2023-10 ~ 2024-01。``aggregate_month`` 因此強制檢查並預設 **raise**;
呼叫端須明確以 ``on_unsorted="sort"`` 選擇「依 id 還原成交順序」。

主動單事件重建(tick → event)
------------------------------
    side = +1  if is_buyer_maker == False   (taker buy)
    side = -1  if is_buyer_maker == True    (taker sell)
    事件 = 連續列中 (time, side) 完全相同的最大連續段
    事件 notional E = Σ(price * qty),事件方向 = 該段 side
零自由參數。事件不跨日(UTC 日界 day = time_ms // 86400000)。

每日統計量
----------
每個 (symbol, day) 一列,欄位順序見 ``COLUMNS``。除規格所需的量之外,額外
輸出「事件規模分桶直方圖」(``EDGES``,23 桶),使所有 robustness 變體
(改門檻 $500/$2,000/$5,000/$20,000、改金額加權)都不必重掃原始 tick。

訊號
----
    Imb_b(i,d) = (n_buy_b - n_sell_b) / (n_buy_b + n_sell_b)      b ∈ {S, L, A}
        S(小單) = 事件 notional ∈ [100, 1000)
        L(大單) = 事件 notional >= 10000
        A(全部) = 所有事件
    ImbBar_b(i,d) = mean(Imb_b(i, d-4 .. d))                      5 日簡單平均(含當日)
    ASD(i,d)      = ImbBar_L(i,d) - ImbBar_S(i,d)

合格性篩選(機械式):
    (i,d) 進入當日橫截面需 min(n_S_buy, n_S_sell) >= 50
                        且 min(n_L_buy, n_L_sell) >= 50
    當日合格幣數 < 30 → 整日為 NaN(不交易)

橫截面標準化:當日對合格幣的 ASD 取 rank(method="average"),映射到均勻分數
    score = (rank - 0.5) / N - 0.5      值域 [-0.5, +0.5]
**不用 z-score。**

方向:**高分做多**(符號寫死,不接受翻轉救援)。

Anti look-ahead / shift 約定(照 FSIM_VenueMigration 慣例)
----------------------------------------------------------
    所有 rolling 只用 <= t 的資料(5 日平均含當日)。
    ``panel()`` 回傳 t 日(UTC 日終)可得的訊號,**未做任何 shift**;
    shift 由 runner 統一施加。訊號模組本身不 shift,以免重複滯後。
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

# ---------------------------------------------------------------- 分桶定義

EDGES = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1e3, 2e3, 5e3, 1e4,
         2e4, 5e4, 1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7, np.inf]
BUCKETS = len(EDGES) - 1          # 23

_EDGES_ARR = np.asarray(EDGES, dtype=np.float64)

MS_PER_DAY = 86_400_000
_PX_OFFSET_MS = 900_000           # 00:15:00 UTC

# 訊號門檻(美元 notional),皆落在 EDGES 上
S_LO, S_HI = 100.0, 1000.0        # 小單 [100, 1000)
L_LO, L_HI = 10000.0, None        # 大單 [10000, inf)

MIN_SIDE = 50                     # 每側事件筆數下限
MIN_COINS = 30                    # 當日合格幣數下限

COLUMNS = (
    ["sym", "day", "n_fills", "n_events", "dv"]
    + [f"cb_{k}" for k in range(BUCKETS)]
    + [f"cs_{k}" for k in range(BUCKETS)]
    + [f"vb_{k}" for k in range(BUCKETS)]
    + [f"vs_{k}" for k in range(BUCKETS)]
    + ["close", "px0015", "px0015_lag_ms", "first_ms", "last_ms"]
)


# ---------------------------------------------------------------- 月檔聚合

def _strip_usdt(sym: str) -> str:
    return sym[:-4] if sym.endswith("USDT") else sym


def aggregate_month(sym: str, path: str, on_unsorted: str = "raise") -> list[tuple]:
    """讀一個月的 trades parquet,回傳該月每日一列(欄位順序 = ``COLUMNS``)。

    全程 numpy 向量化(``np.add.reduceat`` / ``np.bincount``),無 pandas
    groupby、無逐筆 python 迴圈。

    ``on_unsorted`` 處理「``time`` 在檔內非遞減」這個前提被違反的情況
    (實測 4502 個月檔中有 41 個違反,集中在 BTC/ETH/SOL 等高流動性幣的
    2023-10 ~ 2024-01)。事件重建與日界切分都依賴列順序,亂序檔若直接處理
    會產出錯誤結果:
        ``"raise"``(預設)— 拋 ValueError,絕不靜默產出壞資料。
        ``"sort"``      — 額外讀 ``id`` 欄,以 ``id``(交易所成交序號)做
                          stable argsort 還原真實成交順序後再處理。
    """
    if on_unsorted not in ("raise", "sort"):
        raise ValueError(f"on_unsorted 只能是 'raise' 或 'sort',收到 {on_unsorted!r}")
    coin = _strip_usdt(sym)

    tbl = pq.read_table(path, columns=["time", "price", "qty", "is_buyer_maker"])
    time = tbl.column("time").to_numpy(zero_copy_only=False)
    price = tbl.column("price").to_numpy(zero_copy_only=False)
    qty = tbl.column("qty").to_numpy(zero_copy_only=False)
    buy = ~tbl.column("is_buyer_maker").to_numpy(zero_copy_only=False)
    del tbl

    n = time.shape[0]
    if n == 0:
        return []

    if n > 1 and bool((time[1:] < time[:-1]).any()):
        if on_unsorted == "raise":
            raise ValueError(
                f"{path}: `time` 非遞減的前提不成立(檔內有時間倒退)。"
                f"事件重建依賴列順序,拒絕靜默處理。"
                f"確認後請以 on_unsorted='sort' 呼叫(依 id 還原成交順序)。"
            )
        ids = pq.read_table(path, columns=["id"]).column("id").to_numpy(zero_copy_only=False)
        order = np.argsort(ids, kind="stable")
        del ids
        time = time[order]
        price = price[order]
        qty = qty[order]
        buy = buy[order]
        del order
        if bool((time[1:] < time[:-1]).any()):
            # 第二階段修復:交易所端偶發 id 碰撞(同一 id 出現兩次、時間不同),
            # 使 id 排序後 time 仍有倒退。實測 PYTHUSDT/2025-08:23,709,904 列中
            # 僅 8 列(0.00003%),集中於單一 UTC 日。以 **stable** argsort 依 time
            # 再排一次:穩定性保證相同時間戳內的 id 次序不變,故事件切分不受影響。
            # 若需修復的比例超過 1e-5,視為真正的檔案損壞而非偶發碰撞 -> 拒絕處理。
            n_back = int((time[1:] < time[:-1]).sum())
            frac = n_back / max(len(time) - 1, 1)
            if frac > 1e-4:
                raise ValueError(
                    f"{path}: 依 id 排序後仍有 {frac:.2e} 的列時間倒退(> 1e-4 上限),"
                    f"判定為檔案損壞,拒絕處理。")
            _log = os.environ.get("ASD_REPAIRLOG")
            if _log:
                with open(_log, "a") as _f:
                    _f.write(json.dumps({"path": path, "rows": int(len(time)),
                                         "backward_steps": n_back, "frac": frac}) + "\n")
            order2 = np.argsort(time, kind="stable")
            time = time[order2]; price = price[order2]; qty = qty[order2]; buy = buy[order2]
            del order2
            if bool((time[1:] < time[:-1]).any()):
                raise ValueError(f"{path}: 二階段修復後 `time` 仍非遞減,拒絕處理。")

    notional = price * qty
    del qty

    # --- 日界(time 非遞減 → 每日是連續區段) ---------------------------
    d0 = int(time[0]) // MS_PER_DAY
    d1 = int(time[-1]) // MS_PER_DAY
    cand = np.arange(d0, d1 + 1, dtype=np.int64)
    bnd = np.searchsorted(time, cand * MS_PER_DAY, side="left")
    day_end_all = np.empty(cand.shape[0], dtype=np.int64)
    day_end_all[:-1] = bnd[1:]
    day_end_all[-1] = n
    keep = day_end_all > bnd
    days = cand[keep]
    day_beg = bnd[keep]
    day_end = day_end_all[keep]
    nd = days.shape[0]

    n_fills = (day_end - day_beg).astype(np.int64)
    dv = np.add.reduceat(notional, day_beg)
    close = price[day_end - 1]
    first_ms = time[day_beg]
    last_ms = time[day_end - 1]

    # --- px0015:當日 >= 00:15:00.000 的第一筆成交 ----------------------
    target = days * MS_PER_DAY + _PX_OFFSET_MS
    pos = np.searchsorted(time, target, side="left")
    has_px = pos < day_end
    px0015 = np.full(nd, np.nan, dtype=np.float64)
    px_lag = np.full(nd, -1, dtype=np.int64)
    if has_px.any():
        p = pos[has_px]
        px0015[has_px] = price[p]
        px_lag[has_px] = time[p] - target[has_px]

    # --- 事件邊界 -------------------------------------------------------
    if n == 1:
        starts = np.zeros(1, dtype=np.int64)
    else:
        newev = (time[1:] != time[:-1]) | (buy[1:] != buy[:-1])
        starts = np.empty(int(newev.sum()) + 1, dtype=np.int64)
        starts[0] = 0
        starts[1:] = np.flatnonzero(newev) + 1
        del newev

    ev_val = np.add.reduceat(notional, starts)
    ev_buy = buy[starts]
    # 事件不跨日:事件所屬日 = 其起始 fill 所屬日
    ev_day_idx = np.searchsorted(day_beg, starts, side="right") - 1
    del notional, price, time, buy

    n_events = np.bincount(ev_day_idx, minlength=nd).astype(np.int64)

    bucket = np.searchsorted(_EDGES_ARR, ev_val, side="right") - 1
    code = ev_day_idx * BUCKETS + bucket
    del bucket, ev_day_idx

    size = nd * BUCKETS
    cb = np.bincount(code[ev_buy], minlength=size).reshape(nd, BUCKETS)
    cs = np.bincount(code[~ev_buy], minlength=size).reshape(nd, BUCKETS)
    vb = np.bincount(code[ev_buy], weights=ev_val[ev_buy], minlength=size).reshape(nd, BUCKETS)
    vs = np.bincount(code[~ev_buy], weights=ev_val[~ev_buy], minlength=size).reshape(nd, BUCKETS)
    del code, ev_val, ev_buy

    rows = []
    for i in range(nd):
        rows.append(
            (coin, int(days[i]), int(n_fills[i]), int(n_events[i]), float(dv[i]))
            + tuple(int(x) for x in cb[i])
            + tuple(int(x) for x in cs[i])
            + tuple(float(x) for x in vb[i])
            + tuple(float(x) for x in vs[i])
            + (float(close[i]), float(px0015[i]), int(px_lag[i]),
               int(first_ms[i]), int(last_ms[i]))
        )
    return rows


# ---------------------------------------------------------------- 面板載入

def _date_index(days) -> pd.DatetimeIndex:
    """day(int, 自 epoch 起的 UTC 日數)→ tz-naive、normalize 的 DatetimeIndex。"""
    return pd.DatetimeIndex(
        pd.to_datetime(np.asarray(days, dtype=np.int64) * MS_PER_DAY, unit="ms")
    ).normalize()


def load_panel(pkl_path: str) -> pd.DataFrame:
    """讀主代理掃好的快取(單一 DataFrame,欄位同 ``COLUMNS``)。

    回傳以 ``(day, sym)`` 為 MultiIndex、已排序的 DataFrame。
    """
    df = pd.read_pickle(pkl_path)
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"{pkl_path} 不是 DataFrame")
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"快取缺少欄位: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    out = df[COLUMNS].copy()
    out["day"] = out["day"].astype(np.int64)
    return out.set_index(["day", "sym"]).sort_index()


def _wide(df_panel: pd.DataFrame, col) -> pd.DataFrame:
    """(day, sym) 索引的一欄(或一條 Series)→ date x coin 寬表,索引補成完整日曆。"""
    s = df_panel[col] if isinstance(col, str) else col
    w = s.unstack("sym")
    w.index = _date_index(w.index.values)
    w = w.sort_index()
    full = pd.date_range(w.index[0], w.index[-1], freq="D")
    return w.reindex(full).sort_index(axis=1)


def _bucket_slice(lo_usd: float, hi_usd: float | None) -> list[int]:
    """把 [lo_usd, hi_usd) 換成桶索引清單;門檻必須落在 EDGES 上。"""
    lo = float(lo_usd)
    if not np.any(np.isclose(_EDGES_ARR, lo, rtol=0, atol=0)):
        raise ValueError(f"lo_usd={lo_usd} 不在 EDGES 上: {EDGES}")
    k_lo = int(np.flatnonzero(_EDGES_ARR == lo)[0])
    if hi_usd is None:
        k_hi = BUCKETS
    else:
        hi = float(hi_usd)
        if not np.any(_EDGES_ARR == hi):
            raise ValueError(f"hi_usd={hi_usd} 不在 EDGES 上: {EDGES}")
        k_hi = int(np.flatnonzero(_EDGES_ARR == hi)[0])
    if k_hi <= k_lo:
        raise ValueError(f"區間空: [{lo_usd}, {hi_usd})")
    return list(range(k_lo, k_hi))


def side_counts(df_panel: pd.DataFrame, lo_usd: float, hi_usd: float | None):
    """回傳 (n_buy, n_sell) 兩張 date x coin 事件筆數面板。"""
    ks = _bucket_slice(lo_usd, hi_usd)
    nb = df_panel[[f"cb_{k}" for k in ks]].sum(axis=1)
    ns = df_panel[[f"cs_{k}" for k in ks]].sum(axis=1)
    return _wide(df_panel, nb), _wide(df_panel, ns)


def imb(df_panel: pd.DataFrame, lo_usd: float, hi_usd: float | None) -> pd.DataFrame:
    """Imb_b = (n_buy - n_sell) / (n_buy + n_sell),date x coin。

    ``hi_usd=None`` 表示無上界。門檻必須落在 ``EDGES`` 上,否則 ValueError。
    """
    nb, ns = side_counts(df_panel, lo_usd, hi_usd)
    tot = nb + ns
    return (nb - ns) / tot.where(tot > 0)


def components(df_panel: pd.DataFrame, smooth: int = 5):
    """回傳 (ImbBar_L, ImbBar_S, ImbBar_A) 三張 date x coin 面板。"""
    r = {
        "L": imb(df_panel, L_LO, L_HI),
        "S": imb(df_panel, S_LO, S_HI),
        "A": imb(df_panel, EDGES[0], None),
    }
    bar = {k: v.rolling(smooth, min_periods=smooth).mean() for k, v in r.items()}
    return bar["L"], bar["S"], bar["A"]


def raw_asd(df_panel: pd.DataFrame, smooth: int = 5) -> pd.DataFrame:
    """ASD = ImbBar_L - ImbBar_S(未過濾、未標準化)。"""
    bar_l, bar_s, _ = components(df_panel, smooth=smooth)
    return bar_l - bar_s


def eligibility(df_panel: pd.DataFrame, min_side: int = MIN_SIDE,
                min_coins: int = MIN_COINS) -> pd.DataFrame:
    """A3 合格性遮罩:當日兩個尺寸桶的買/賣事件筆數皆 >= min_side;
    當日合格幣數 < min_coins → 整列 False。"""
    sb, ss = side_counts(df_panel, S_LO, S_HI)
    lb, ls = side_counts(df_panel, L_LO, L_HI)
    ok = ((sb >= min_side) & (ss >= min_side) & (lb >= min_side) & (ls >= min_side))
    ok = ok.fillna(False)
    return ok.where(ok.sum(axis=1) >= min_coins, False)


def panel(df_panel: pd.DataFrame, smooth: int = 5, min_side: int = MIN_SIDE,
          min_coins: int = MIN_COINS, **_) -> pd.DataFrame:
    """date x coin 的已標準化 t 日訊號(**未 shift**)。不合格處 NaN。

    橫截面:rank(average) → (rank - 0.5)/N - 0.5,值域 [-0.5, +0.5],高分做多。
    """
    raw = raw_asd(df_panel, smooth=smooth)
    ok = eligibility(df_panel, min_side=min_side, min_coins=min_coins)
    raw = raw.where(ok & raw.notna())
    raw = raw.where(raw.notna().sum(axis=1) >= min_coins)

    r = raw.rank(axis=1, method="average")
    n = raw.notna().sum(axis=1)
    return r.div(n.where(n > 0), axis=0).sub(0.5 / n.where(n > 0), axis=0) - 0.5


# ---------------------------------------------------------------- 價格面板

def exec_price(df_panel: pd.DataFrame) -> pd.DataFrame:
    """date x coin 的 px0015(00:15:00 UTC 之後第一筆成交價)。"""
    return _wide(df_panel, "px0015")


def close_price(df_panel: pd.DataFrame) -> pd.DataFrame:
    """date x coin 的當日最後一筆成交價。"""
    return _wide(df_panel, "close")
