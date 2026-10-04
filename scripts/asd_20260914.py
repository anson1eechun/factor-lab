#!/usr/bin/env python3
"""SIM-2026-09-14-001 — FSIM_Aggressor_Size_Divergence 預註冊 runner。

凍結規格:empirical_runs/SIM-2026-09-14-001_prereg.md(sha256 於 phase0 記錄,只讀不改)。
訊號:core/signals/FSIM_Aggressor_Size_Divergence.panel()(t 日訊號,未 shift)。

分相(v2.2 範式):
  phase 0  完整性 + 自 hash + 無前視斷言(**鎖靜默:不列印任何聚合回測數字**)
  phase 1  可重現性鎖(主規格獨立跑兩次,主要 metric 差 < 1e-8);FAIL -> lock_fail_N.json + HALT
  phase 2  confirmatory + G1..G5 閘門 + disclosure-only 變體

組合(§3.4):5 日重疊 Jegadeesh-Titman。訊號日 d -> px0015(d+1) 進場、px0015(d+6) 出場。
  R(k) = PX(k+1)/PX(k) - 1 = 在 PX(k) 建倉持到 PX(k+1) 所賺。
  子組合 d 於 k ∈ [d+1, d+5] 活著,每個子組合毛曝險 2/5,總毛曝險 2。
  **持有期內權重隨報酬漂移**(v2.4 §7);固定權重版僅作 disclosure 對照。
  **elig 遮罩不引用任何 *_fwd 欄位**(v2.4 §7 lint):缺報酬日視為該幣當日 0 報酬並計數。

跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/asd_20260914.py {0|1|2}
"""
import sys, os, json, hashlib, platform, datetime, warnings
import numpy as np, pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.signals import FSIM_Aggressor_Size_Divergence as M

SIM = "SIM-2026-09-14-001"
ER = "/home/anson/factor-lab/empirical_runs/"
SP = "/tmp/claude-1000/-home-anson/537e35c7-894a-4fcb-a3e3-a590d08320fe/scratchpad/"
PANEL_PKL = ER + "trade_events_1d.pkl"
FUNDING_PKL = ER + "funding_1d.pkl"
PREREG = ER + SIM + "_prereg.md"
SIG_PY = "/home/anson/factor-lab/core/signals/FSIM_Aggressor_Size_Divergence.py"
SELF_PY = os.path.abspath(__file__)
INT_JSON = ER + SIM + "_integrity.json"
LOCK_JSON = ER + SIM + "_replication_lock.json"
RES_JSON = ER + SIM + "_results.json"

ANN = np.sqrt(365.0)
HOLD, QN, COST_BPS, MIN_COINS, SMOOTH = 5, 5, 5.0, 30, 5
NW_LAG = 10
LOYO_YEARS = [2021, 2022, 2023, 2024, 2025]


# ------------------------------------------------------------------ 工具
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


RUNNER_SHA = sha256_file(SELF_PY)


def sanitize(o):
    if isinstance(o, dict): return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [sanitize(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(o, (np.bool_, bool)): return bool(o)
    if isinstance(o, (pd.Timestamp, datetime.date)): return str(o)[:10]
    return o


def dump(path, obj):
    obj = dict(obj); obj["runner_sha256"] = RUNNER_SHA
    with open(path, "w") as f:
        json.dump(sanitize(obj), f, ensure_ascii=False, indent=2)
    print("saved →", path)


def nw_t(x, L=NW_LAG):
    """Newey-West(Bartlett)t。"""
    x = pd.Series(x).dropna().values.astype(float)
    n = len(x)
    if n < 3: return float("nan")
    mu = float(x.mean()); e = x - mu
    s = float(np.dot(e, e)) / n
    for l in range(1, min(L, n - 1) + 1):
        s += 2.0 * (1.0 - l / (L + 1.0)) * float(np.dot(e[l:], e[:-l])) / n
    if s <= 0: return float("nan")
    return float(mu / np.sqrt(s / n))


def perf(r):
    r = pd.Series(r).dropna()
    if len(r) < 2 or not r.std(ddof=1):
        return {"n_days": int(len(r))}
    eq = (1 + r).cumprod()
    return {"n_days": int(len(r)),
            "ann_return": float(r.mean() * 365),
            "sharpe": float(r.mean() / r.std(ddof=1) * ANN),
            "t_iid": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))),
            "nw_t": nw_t(r),
            "max_drawdown": float((eq / eq.cummax() - 1).min())}


# ------------------------------------------------------------------ 資料
def load_all():
    dfp = M.load_panel(PANEL_PKL)
    SIG = M.panel(dfp, smooth=SMOOTH, min_coins=MIN_COINS)
    PX = M.exec_price(dfp)
    CL = M.close_price(dfp)
    # --- 修正案 A1(empirical_runs/SIM-2026-09-14-001_runner_amendment.md) ---
    # Binance 原始逐筆有十進位尺度壞點(9 個 coin-day,比值精確為 10 的次方)。
    # 以嚴格先前資訊驗證:|log(px0015(k) / close(k-1))| > log(10) -> 該執行價作廢。
    # 門檻 5x~96x 標記完全相同的 9 個 coin-day(解析度檢定通過);
    # 真實極端值 DOGE 2021-01-28(比值 0.203)不被標記。零前視。
    _prev_close = CL.shift(1)
    _bad_px = (np.log(PX / _prev_close).abs() > np.log(10.0)) & _prev_close.notna()
    PX = PX.where(~_bad_px)
    R = PX.shift(-1) / PX - 1.0                       # R(k): PX(k)->PX(k+1)
    fund = pd.read_pickle(FUNDING_PKL)
    cols = {}
    for c, d in fund.items():
        idx = pd.to_datetime(d["timestamp"], unit="ms").dt.normalize()
        cols[c] = pd.Series(d["funding"].astype(float).values, index=idx)
    F = pd.DataFrame(cols).reindex(index=SIG.index, columns=SIG.columns)
    # 規格 §3.4 要求 funding 現金流腿必入帳。funding_1d.pkl 止於 2026-07-04,
    # 而逐筆面板到 2026-08-31。把 confirmatory 樣本截到 funding 仍有覆蓋的最後一天,
    # 否則最後約兩個月會被靜默當成 funding=0(等於未申報的記帳漏項)。
    fund_last = pd.DataFrame(cols).dropna(how="all").index.max()
    end = min(fund_last, SIG.index.max())
    SIG, PX, CL, R, F = (x.loc[:end] for x in (SIG, PX, CL, R, F))
    return dfp, SIG, PX, CL, R, F


def controls(dfp, index, columns):
    """G5(i) 控制變數,全部同源於逐筆面板。"""
    CL = M.close_price(dfp)
    ret = CL / CL.shift(1) - 1.0
    _, _, bar_a = M.components(dfp, smooth=SMOOTH)
    dv = M._wide(dfp, "dv")
    out = {"imb_a": bar_a,
           "max21": ret.rolling(21, min_periods=21).max(),
           "ladv20": np.log(dv.rolling(20, min_periods=20).mean().where(lambda x: x > 0)),
           "sig20": ret.rolling(20, min_periods=20).std(ddof=1)}
    return {k: v.reindex(index=index, columns=columns) for k, v in out.items()}


# ------------------------------------------------------------------ 組合
def qweights(row, q=QN, min_coins=MIN_COINS, scale=1.0 / HOLD, which="ls"):
    """訊號列 -> 子組合目標權重(毛曝險 2*scale)。which='ls' 或 quintile 序號 0..q-1。"""
    x = row.dropna()
    if len(x) < min_coins:
        return None
    r = x.rank(method="average")
    lab = pd.qcut(r, q, labels=False, duplicates="drop")
    if lab.max() != q - 1:
        return None
    w = pd.Series(0.0, index=row.index)
    if which == "ls":
        top = x.index[lab == q - 1]; bot = x.index[lab == 0]
        w[top] = scale / len(top); w[bot] = -scale / len(bot)
    else:
        sel = x.index[lab == which]
        w[sel] = scale / len(sel)
    return w


def _close_out(rows, prevW, dt, cost_bps):
    """subs 清空時仍須記平倉成本(避免免費出場)。"""
    turn = float(prevW.abs().sum())
    if turn > 0:
        rows.append((dt, 0.0, turn * cost_bps / 1e4, 0.0, -turn * cost_bps / 1e4,
                     turn, 0, 0))


def backtest(SIG, R, F, hold=HOLD, cost_bps=COST_BPS, drift=True, which="ls",
             entry_lag=1, q=QN):
    """5 日重疊 JT。entry_lag=1 -> 訊號日 d 於 PX(d+1) 進場(主規格)。

    回傳 DataFrame(index=交易日),欄位 gross/cost/fund/net/turn/n_pos/n_missing_R。
    """
    dates = list(SIG.index)
    subs = []                                  # list of (formed_pos, weights Series)
    prevW = pd.Series(0.0, index=SIG.columns)
    rows = []
    for k in range(len(dates)):
        dt = dates[k]
        # 退場:形成於 d 的子組合活在 [d+entry_lag, d+entry_lag+hold-1]
        subs = [(d, w) for (d, w) in subs if d + entry_lag + hold - 1 >= k]
        # 進場:今天開始活的子組合形成於 d = k - entry_lag
        d_new = k - entry_lag
        if d_new >= 0:
            w = qweights(SIG.iloc[d_new], q=q, which=which)
            if w is not None:
                subs.append((d_new, w))
        if not subs:
            _close_out(rows, prevW, dt, cost_bps)
            prevW = pd.Series(0.0, index=SIG.columns)
            continue
        W = pd.concat([w for _, w in subs], axis=1).sum(axis=1)
        rv = R.loc[dt]
        n_missing = int(rv.isna()[W != 0].sum())
        rv = rv.fillna(0.0)
        fv = F.loc[dt].fillna(0.0)
        turn = float((W - prevW).abs().sum())
        gross = float((W * rv).sum())
        fund = -float((W * fv).sum())
        cost = turn * cost_bps / 1e4
        rows.append((dt, gross, cost, fund, gross - cost + fund, turn,
                     int((W != 0).sum()), n_missing))
        if drift:
            subs = [(d, w * (1.0 + rv)) for (d, w) in subs]
        prevW = pd.concat([w for _, w in subs], axis=1).sum(axis=1)
    return pd.DataFrame(rows, columns=["dt", "gross", "cost", "fund", "net",
                                       "turn", "n_pos", "n_missing_R"]).set_index("dt")


def ic_series(Z, FWD, min_coins=MIN_COINS):
    idx, val = [], []
    for dt in Z.index:
        x = Z.loc[dt]; y = FWD.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= min_coins:
            c = stats.spearmanr(x[m], y[m]).correlation
            if np.isfinite(c):
                idx.append(dt); val.append(c)
    return pd.Series(val, index=idx, dtype=float)


def ic_stats(ic):
    n = len(ic)
    if n < 3: return {"ic_n": n}
    mu = float(ic.mean()); sd = float(ic.std(ddof=1))
    return {"rank_ic": mu, "ic_ir": mu / sd, "ic_t_iid": mu / (sd / np.sqrt(n)),
            "ic_nw_t": nw_t(ic), "ic_n": n}


def fwd1(R, SIG):
    """訊號日 d 對應的第一天持有報酬 = R(d+1)(PX(d+1)->PX(d+2))。"""
    return R.shift(-1).reindex(index=SIG.index, columns=SIG.columns)


def xs_resid(Z, CTRL):
    """每日橫截面對控制變數迴歸取殘差(含截距)。"""
    out = pd.DataFrame(np.nan, index=Z.index, columns=Z.columns)
    for dt in Z.index:
        y = Z.loc[dt]
        X = pd.concat([c.loc[dt] for c in CTRL], axis=1,
                      keys=[f"c{j}" for j in range(len(CTRL))])
        m = y.notna() & X.notna().all(axis=1)
        if m.sum() < MIN_COINS + len(CTRL) + 1:
            continue
        Xm = np.column_stack([np.ones(int(m.sum()))] + [stats.rankdata(X.loc[m, c]) for c in X.columns])
        yv = stats.rankdata(y[m])
        beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
        out.loc[dt, y[m].index] = yv - Xm @ beta
    return out


# ------------------------------------------------------------------ phase 0
def phase0():
    """完整性 + 無前視斷言。**鎖靜默:不列印任何聚合回測數字。**"""
    dfp, SIG, PX, CL, R, F = load_all()
    days = M._date_index(sorted({d for d, _ in dfp.index}))
    coins = sorted({s for _, s in dfp.index})

    # 無前視:截斷重算 vs 全樣本,重疊期逐格容差 0
    cut = SIG.index[-40]
    dfp_trunc = dfp[dfp.index.get_level_values("day") <= int((cut.value // 10**6) // M.MS_PER_DAY)]
    SIG_t = M.panel(dfp_trunc, smooth=SMOOTH, min_coins=MIN_COINS)
    ov = SIG.index.intersection(SIG_t.index)
    a = SIG.loc[ov].reindex(columns=SIG.columns)
    b = SIG_t.loc[ov].reindex(columns=SIG.columns)
    same = bool(((a.isna() & b.isna()) | (a == b)).all().all())

    # v2.4 §7 lint:elig 遮罩不得引用任何 fwd 欄位
    src = open(SIG_PY).read()
    lint_ok = ("shift(-1)" not in src) and ("_fwd" not in src)

    # funding 對齊
    fn_cov = float(F.notna().sum().sum()) / float(SIG.notna().sum().sum() or 1)

    elig = M.eligibility(dfp)
    payload = {
        "session": SIM, "phase": 0,
        "prereg_sha256": sha256_file(PREREG), "signal_sha256": sha256_file(SIG_PY),
        "panel_sha256": sha256_file(PANEL_PKL),
        "env": {"python": platform.python_version(), "numpy": np.__version__,
                "pandas": pd.__version__, "scipy": __import__("scipy").__version__},
        "panel": {"rows": int(len(dfp)), "coins": len(coins),
                  "day_first": str(days.min())[:10], "day_last": str(days.max())[:10],
                  "coin_list": coins},
        "signal_grid": {"dates": int(len(SIG)), "cols": int(SIG.shape[1]),
                        "first_tradable_day": str(SIG.dropna(how="all").index.min())[:10],
                        "last_tradable_day": str(SIG.dropna(how="all").index.max())[:10],
                        "tradable_days": int(SIG.notna().any(axis=1).sum()),
                        "median_coins_per_day": float(SIG.notna().sum(axis=1)[SIG.notna().any(axis=1)].median())},
        "eligibility": {"coin_days_pass": int(elig.sum().sum()),
                        "days_with_ge_min_coins": int((elig.sum(axis=1) >= MIN_COINS).sum())},
        "px0015": {"nan_ratio": float(PX.isna().mean().mean()),
                   "lag_ms_p50": float(dfp["px0015_lag_ms"].median()),
                   "lag_ms_p99": float(dfp["px0015_lag_ms"].quantile(0.99)),
                   "lag_ms_max": int(dfp["px0015_lag_ms"].max())},
        "no_lookahead_truncation_identical": same,
        "lint_no_fwd_in_signal_module": lint_ok,
        "funding_coverage_vs_signal": fn_cov,
        "note": "lock 靜默:本相不輸出任何 IC / Sharpe / P&L 數字",
    }
    dump(INT_JSON, payload)
    if not same:
        print("HALT: 前視斷言失敗"); sys.exit(1)
    if not lint_ok:
        print("HALT: lint 失敗(訊號模組引用了 fwd)"); sys.exit(1)
    print("phase0 OK")


# ------------------------------------------------------------------ phase 1
def _main_metrics():
    dfp, SIG, PX, CL, R, F = load_all()
    bt = backtest(SIG, R, F)
    p = perf(bt["net"])
    ic = ic_series(SIG, fwd1(R, SIG))
    return {"net_sharpe": p["sharpe"], "net_nw_t": p["nw_t"],
            "rank_ic": ic_stats(ic)["rank_ic"], "turn_mean": float(bt["turn"].mean())}


def phase1():
    a = _main_metrics(); b = _main_metrics()
    diffs = {k: abs(a[k] - b[k]) for k in a}
    ok = all(v < 1e-8 for v in diffs.values())
    payload = {"session": SIM, "phase": 1, "run_a": a, "run_b": b,
               "abs_diffs": diffs, "tolerance": 1e-8, "replication_lock": "PASS" if ok else "FAIL"}
    if not ok:
        n = 1
        while os.path.exists(ER + f"{SIM}_lock_fail_{n}.json"):
            n += 1
        dump(ER + f"{SIM}_lock_fail_{n}.json", payload)
        print("HALT: 複製鎖 FAIL"); sys.exit(1)
    dump(LOCK_JSON, payload)
    print("phase1 replication lock PASS")


# ------------------------------------------------------------------ 變體工具
def _rank_xs(raw, ok, min_coins=MIN_COINS):
    raw = raw.where(ok & raw.notna())
    raw = raw.where(raw.notna().sum(axis=1) >= min_coins)
    r = raw.rank(axis=1, method="average")
    n = raw.notna().sum(axis=1)
    return r.div(n.where(n > 0), axis=0).sub(0.5 / n.where(n > 0), axis=0) - 0.5


def variant_signal(dfp, s_lo, s_hi, l_lo, ok, smooth=SMOOTH):
    L = M.imb(dfp, l_lo, None).rolling(smooth, min_periods=smooth).mean()
    S = M.imb(dfp, s_lo, s_hi).rolling(smooth, min_periods=smooth).mean()
    return _rank_xs(L - S, ok)


def notional_imb(dfp, lo, hi):
    ks = M._bucket_slice(lo, hi)
    vb = dfp[[f"vb_{k}" for k in ks]].sum(axis=1)
    vs = dfp[[f"vs_{k}" for k in ks]].sum(axis=1)
    B, S = M._wide(dfp, vb), M._wide(dfp, vs)
    tot = B + S
    return (B - S) / tot.where(tot > 0)


# ------------------------------------------------------------------ phase 2
def phase2():
    dfp, SIG, PX, CL, R, F = load_all()

    def R2(x):
        """把任何由 dfp 導出的面板對齊到訊號網格。dfp 覆蓋到 2026-08-31,
        但 R/F 受 funding 覆蓋截到 2026-07-04(load_all),索引必須一致。"""
        return x.reindex(index=SIG.index, columns=SIG.columns)

    ok = R2(M.eligibility(dfp))
    FWD = fwd1(R, SIG)
    res = {"session": SIM, "phase": 2,
           "prereg_sha256": sha256_file(PREREG), "signal_sha256": sha256_file(SIG_PY)}

    # ---------------- 主規格(confirmatory) ----------------
    bt = backtest(SIG, R, F)
    main = perf(bt["net"])
    main_gross = perf(bt["gross"])
    ic = ic_series(SIG, FWD)
    T_years = len(bt) / 365.0
    res["main"] = {
        **main,
        "gross_sharpe": main_gross.get("sharpe"),
        "gross_minus_cost_sharpe": perf(bt["gross"] - bt["cost"]).get("sharpe"),
        "turn_mean": float(bt["turn"].mean()), "turn_p95": float(bt["turn"].quantile(.95)),
        "cost_drag_ann": float(bt["cost"].mean() * 365),
        "funding_ann": float(bt["fund"].mean() * 365),
        "n_pos_median": float(bt["n_pos"].median()),
        "n_missing_R_total": int(bt["n_missing_R"].sum()),
        "date_first": str(bt.index.min())[:10], "date_last": str(bt.index.max())[:10],
        "T_years": T_years, **ic_stats(ic)}

    # ---------------- G1 機制分解閘 ----------------
    bar_l, bar_s, bar_a = (R2(x) for x in M.components(dfp, smooth=SMOOTH))
    icL = ic_series(bar_l.where(ok), FWD)
    icS = ic_series(bar_s.where(ok), FWD)
    icA = ic_series(bar_a.where(ok), FWD)
    sL, sS, sA = ic_stats(icL), ic_stats(icS), ic_stats(icA)
    g1 = (sL["ic_nw_t"] >= 1.5) and (sS["ic_nw_t"] <= -1.5)
    res["G1"] = {"comp_L": sL, "comp_S": sS, "comp_A_control": sA,
                 "rule": "t(L)>=+1.5 AND t(S)<=-1.5", "PASS": bool(g1)}

    # ---------------- G2 美元層閘 ----------------
    g2i = (main["sharpe"] >= 0.7) and (main["nw_t"] >= 2.0)
    g2ii = float(bt["turn"].mean()) <= 0.60
    g2iii = main_gross.get("sharpe", 0) <= 3.0
    res["G2"] = {"i_net_sharpe": main["sharpe"], "i_net_nw_t": main["nw_t"], "i_PASS": bool(g2i),
                 "ii_turn_mean": float(bt["turn"].mean()), "ii_PASS": bool(g2ii),
                 "iii_gross_sharpe": main_gross.get("sharpe"), "iii_PASS": bool(g2iii),
                 "iii_note": "純噪音通過率≈100%,依 v2.4 §6 不計入通過數",
                 "PASS": bool(g2i and g2ii)}

    # ---------------- G3 Leave-one-year-out ----------------
    yr = bt.index.year
    yearly = {int(y): float(bt.loc[yr == y, "net"].mean()) for y in sorted(set(yr))}
    n_pos = sum(1 for y in LOYO_YEARS if yearly.get(y, 0.0) > 0)
    loyo = {int(y): nw_t(bt.loc[yr != y, "net"]) for y in LOYO_YEARS}
    loyo_min = float(np.nanmin(list(loyo.values())))
    g3 = (n_pos >= 4) and (loyo_min >= 1.5)
    res["G3"] = {"yearly_mean_net": yearly, "n_positive_years_2021_2025": n_pos,
                 "loyo_nw_t": loyo, "loyo_min": loyo_min, "PASS": bool(g3)}

    # ---------------- G4 單調性 ----------------
    qmeans = []
    for i in range(QN):
        bq = backtest(SIG, R, F, which=i)
        qmeans.append(float(bq["net"].mean()))
    mono = float(stats.spearmanr(np.arange(QN), qmeans).correlation)
    g4 = (mono >= 0.8) and ((qmeans[-1] - qmeans[0]) > max(qmeans[-2] - qmeans[1], 0.0))
    res["G4"] = {"quintile_mean_net": qmeans, "mono_spearman": mono, "PASS": bool(g4)}

    # ---------------- G5 正交性與存續期 ----------------
    C = controls(dfp, SIG.index, SIG.columns)
    ctrl_ic = {k: ic_stats(ic_series(v.where(ok), FWD)) for k, v in C.items()}
    resid = _rank_xs(xs_resid(SIG, [C[k] for k in ["imb_a", "max21", "ladv20", "sig20"]]), ok)
    bt_r = backtest(resid, R, F)
    pr = perf(bt_r["net"])
    g5i = (pr.get("sharpe", -9) >= 0.5) and (pr.get("nw_t", -9) >= 1.5)
    bt_d = backtest(SIG, R, F, entry_lag=2)
    pd_ = perf(bt_d["net"])
    same_sign = np.sign(pd_.get("nw_t", 0)) == np.sign(main["nw_t"])
    g5ii = bool(same_sign and abs(pd_.get("nw_t", 0)) >= 0.5 * abs(main["nw_t"]))
    # v2.4 §4:控制變數自身 alpha 若反號且更強 -> 該檢定作廢
    voided = [k for k, v in ctrl_ic.items()
              if abs(v.get("rank_ic", 0)) > abs(res["main"]["rank_ic"])
              and np.sign(v.get("rank_ic", 0)) != np.sign(res["main"]["rank_ic"])]
    res["G5"] = {"i_resid": pr, "i_PASS": bool(g5i),
                 "ii_delayed_entry": pd_, "ii_PASS": g5ii,
                 "control_own_ic": ctrl_ic,
                 "controls_stronger_and_opposite": voided,
                 "i_voided_by_v24_rule4": bool(voided),
                 "PASS": bool(g5i and g5ii and not voided)}

    # ---------------- disclosure-only ----------------
    dis = {}
    for tag, (slo, shi, llo) in {"thr_500_5k": (500.0, 5e3, 5e3),
                                 "thr_2k_20k": (2e3, 2e4, 2e4)}.items():
        sv = R2(variant_signal(dfp, slo, shi, llo, ok))
        b = backtest(sv, R, F)
        dis[tag] = {**perf(b["net"]), **ic_stats(ic_series(sv, FWD))}
    nL = R2(notional_imb(dfp, M.L_LO, None).rolling(SMOOTH, min_periods=SMOOTH).mean())
    nS = R2(notional_imb(dfp, M.S_LO, M.S_HI).rolling(SMOOTH, min_periods=SMOOTH).mean())
    sv = _rank_xs(nL - nS, ok)
    b = backtest(sv, R, F)
    dis["notional_weighted"] = {**perf(b["net"]), **ic_stats(ic_series(sv, FWD))}
    for tag, comp in {"comp_L_only": bar_l, "comp_S_only": -bar_s, "imb_A_only": bar_a}.items():
        sv = _rank_xs(comp, ok)
        b = backtest(sv, R, F)
        dis[tag] = {**perf(b["net"]), **ic_stats(ic_series(sv, FWD))}
    b = backtest(SIG, R, F, drift=False)
    dis["fixed_weight_no_drift"] = {**perf(b["net"]), "turn_mean": float(b["turn"].mean())}
    b = backtest(SIG, R, F, cost_bps=0.0)
    dis["zero_cost"] = perf(b["net"])
    res["disclosure"] = dis

    # ---------------- Deflated Sharpe(公式凍結於 prereg §6) ----------------
    N_planned = 12
    se = 1.0 / np.sqrt(T_years)
    res["deflated_sharpe"] = {
        "T_years": T_years, "SE_sharpe": se, "N_planned": N_planned,
        "expected_max_sharpe_noise": float(se * np.sqrt(2 * np.log(N_planned))),
        "observed_net_sharpe": main["sharpe"],
        "passes_DSR": bool(main["sharpe"] > se * np.sqrt(2 * np.log(N_planned)))}

    gates = {g: res[g]["PASS"] for g in ["G1", "G2", "G3", "G4", "G5"]}
    res["gates"] = gates
    res["gates_passed"] = int(sum(gates.values()))
    dump(RES_JSON, res)
    print(json.dumps(sanitize({"main": res["main"], "gates": gates,
                               "dsr": res["deflated_sharpe"]}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    {"0": phase0, "1": phase1, "2": phase2}[sys.argv[1]]()
