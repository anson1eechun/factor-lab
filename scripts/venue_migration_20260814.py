#!/usr/bin/env python3
"""SIM-2026-08-14-001 — FSIM_VenueMigration 預註冊 runner(分相執行,v2.2/v2.3 紀律)。

凍結規格:empirical_runs/SIM-2026-08-14-001_prereg.md(commit bacaea5,只讀不改)。
訊號:core/signals/FSIM_VenueMigration.panel()(t 日訊號,未 shift)。

分相:
  phase 0  完整性 + 自 hash + 無前視斷言(鎖靜默:不列印任何聚合回測數字)
           -> empirical_runs/SIM-2026-08-14-001_integrity.json
  phase 1  G1 可重現性鎖(主規格獨立跑兩次,主要 metric 差 < 1e-8)
           -> ..._replication_lock.json;FAIL -> ..._lock_fail_N.json 並 HALT
  phase 2  Phase 2 confirmatory + Phase 3 閘門 + Phase 4 disclosure(單次批跑)
           -> ..._results.json

跑: uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/venue_migration_20260814.py {0|1|2}
"""
import sys, os, json, hashlib, platform, datetime, warnings
import numpy as np, pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.signals.FSIM_VenueMigration import (panel, dollar_volumes, rank_z, MIN_COINS,
                                              UNIVERSE_PKL, COINBASE_PKL)

SIM = "SIM-2026-08-14-001"
ER = "/home/anson/factor-lab/empirical_runs/"
FUNDING_PKL = ER + "funding_1d.pkl"
SIG_PY = "/home/anson/factor-lab/core/signals/FSIM_VenueMigration.py"
SELF_PY = os.path.abspath(__file__)
INT_JSON = ER + SIM + "_integrity.json"
LOCK_JSON = ER + SIM + "_replication_lock.json"
RES_JSON = ER + SIM + "_results.json"

ANN = np.sqrt(365)
W_MAIN, D_MAIN, HOLD_MAIN, COST_MAIN, Q_MAIN = 7, 28, 7, 10.0, 5
H1 = ("2023-01-01", "2024-12-31")
H2 = ("2025-01-01", "2026-07-31")


# ---------------- 工具 ----------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


RUNNER_SHA = sha256_file(SELF_PY)


def env_dict():
    import scipy
    return {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "scipy": scipy.__version__}


def sanitize(o):
    if isinstance(o, dict): return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [sanitize(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
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


def fail_dump(payload):
    n = 1
    while os.path.exists(ER + f"{SIM}_lock_fail_{n}.json"):
        n += 1
    dump(ER + f"{SIM}_lock_fail_{n}.json", payload)


# ---------------- 資料 ----------------
def load_books(t_end=None):
    uni = pd.read_pickle(UNIVERSE_PKL); cb = pd.read_pickle(COINBASE_PKL)
    if t_end is not None:
        ms = int(pd.Timestamp(t_end).value // 10**6)
        uni = {k: v[v["timestamp"] <= ms].reset_index(drop=True) for k, v in uni.items()}
        cb = {k: v[v["timestamp"] <= ms].reset_index(drop=True) for k, v in cb.items()}
    return uni, cb


def close_panel(book, coins, index):
    cols = {}
    for c in coins:
        df = book[c]
        idx = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
        cols[c] = pd.Series(df["close"].astype(float).values, index=idx)
    return pd.DataFrame(cols).reindex(index)[coins]


def funding_panel(coins, index):
    """funding_fwd[t] = funding[t+1]:與 fwd[t]=close(t+1)/close(t)-1 同一持有區間。"""
    f = pd.read_pickle(FUNDING_PKL)
    cols = {}
    for c in coins:
        if c not in f:
            cols[c] = pd.Series(np.nan, index=index); continue
        df = f[c]
        idx = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
        cols[c] = pd.Series(df["funding"].astype(float).values, index=idx).reindex(index)
    F = pd.DataFrame(cols)[coins]
    return F.shift(-1)


def build_main(t_end=None, w=W_MAIN, d=D_MAIN, drop_coins=()):
    """回傳 (Z_t 未 shift, FWD, FUND_fwd, CLOSE, dv_bn, dv_cb)。"""
    uni, cb = load_books(t_end)
    for c in drop_coins:
        uni.pop(c, None); cb.pop(c, None)
    Z = panel(uni, cb, w=w, d=d)
    coins, index = list(Z.columns), Z.index
    C = close_panel(uni, coins, index)
    FWD = C.shift(-1) / C - 1.0
    FUND = funding_panel(coins, index)
    dv_bn, dv_cb = dollar_volumes(uni, cb)
    return Z, FWD, FUND, C, dv_bn, dv_cb


# ---------------- 指標 ----------------
def ic_series(Z, FWD, min_coins=MIN_COINS):
    idx, vals = [], []
    for dt in Z.index:
        x = Z.loc[dt]; y = FWD.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= min_coins:
            idx.append(dt); vals.append(stats.spearmanr(x[m], y[m]).correlation)
    return pd.Series(vals, index=idx, dtype=float).dropna()


def ic_stats(ic):
    n = len(ic); mu = float(ic.mean()); sd = float(ic.std(ddof=1))
    return {"rank_ic_mean": round(mu, 5), "ic_ir": round(mu / sd, 4),
            "ic_t": round(mu / (sd / np.sqrt(n)), 3), "ic_n_days": int(n)}


def nw_t(x, L=7):
    """Newey-West(Bartlett)t:γ_l=(1/n)Σ(x_t-μ)(x_{t-l}-μ);S=γ_0+2Σ(1-l/(L+1))γ_l;t=μ/√(S/n)。"""
    x = pd.Series(x).dropna().values.astype(float)
    n = len(x); mu = float(x.mean()); e = x - mu
    s = float(np.dot(e, e)) / n
    for l in range(1, L + 1):
        s += 2.0 * (1.0 - l / (L + 1.0)) * float(np.dot(e[l:], e[:-l])) / n
    return round(mu / float(np.sqrt(s / n)), 3)


def perf(r, ann=ANN):
    r = pd.Series(r).dropna()
    if len(r) < 2 or not r.std(ddof=1):
        return {"n_days": int(len(r))}
    eq = (1 + r).cumprod()
    return {"n_days": int(len(r)), "mean_daily": float(r.mean()),
            "ann_return": round(float(r.mean() * 365), 4),
            "sharpe": round(float(r.mean() / r.std(ddof=1) * ann), 3),
            "t_daily": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3),
            "max_drawdown": round(float((eq / eq.cummax() - 1).min()), 4)}


def backtest(Z_shift, FWD, FUND, hold=HOLD_MAIN, cost_bps=COST_MAIN, q=Q_MAIN,
             min_coins=MIN_COINS):
    """§4.10-13 組合迴圈。Z_shift = 已 shift(1) 的可交易訊號(t-1 訊號、t 收盤建倉、賺 t→t+1)。
    每 hold 列再平衡(第一個有效日為錨、固定步長);腿內等權、兩腿等額;
    turnover = Σ|Δw|(建倉+平倉兩側);funding:多頭付、空頭收 → pnl = -Σ w·funding_fwd。"""
    rows, w, since, blk = [], None, 10**9, -1
    for dt in Z_shift.index:
        x = Z_shift.loc[dt]; y = FWD.loc[dt]; fn = FUND.loc[dt]
        elig = x.notna() & y.notna() & fn.notna()
        turn = 0.0
        if since >= hold and int(elig.sum()) >= min_coins:
            xr = x[elig].rank(method="average")
            qq = pd.qcut(xr, q, labels=False, duplicates="drop")
            neww = pd.Series(0.0, index=Z_shift.columns)
            top = xr.index[qq == qq.max()]; bot = xr.index[qq == 0]
            neww[top] = 1.0 / len(top); neww[bot] = -1.0 / len(bot)
            turn = float((neww - (w if w is not None else 0.0)).abs().sum())
            w = neww; since = 0; blk += 1
        if w is None:
            continue
        yv = y.fillna(0.0); fv = fn.fillna(0.0)
        gross = float((w * yv).sum())
        long_r = float((w.clip(lower=0) * yv).sum())
        short_r = float((-w.clip(upper=0) * yv).sum())      # 空頭籃子自身報酬(正號)
        fund = -float((w * fv).sum())
        long_f = -float((w.clip(lower=0) * fv).sum())
        short_f = -float((w.clip(upper=0) * fv).sum())
        cost = turn * cost_bps / 10000.0
        rows.append((dt, blk, gross, cost, fund, gross - cost, gross - cost + fund,
                     long_r, short_r, long_f, short_f, turn, int(elig.sum()),
                     int(fn[x.notna() & y.notna()].isna().sum())))
        since += 1
    return pd.DataFrame(rows, columns=["dt", "blk", "gross", "cost", "fund", "gross_net_cost",
                                       "net", "long_r", "short_r", "long_f", "short_f",
                                       "turn", "n_elig", "n_no_funding"]).set_index("dt")


def weekly_t(bt):
    wk = bt.groupby("blk")["net"].sum()
    n = len(wk); sd = float(wk.std(ddof=1))
    return {"n_blocks": int(n), "mean_weekly": round(float(wk.mean()), 6),
            "weekly_t": round(float(wk.mean() / (sd / np.sqrt(n))), 3),
            "weekly_sharpe_ann": round(float(wk.mean() / sd * np.sqrt(365.0 / HOLD_MAIN)), 3),
            "n_complete_blocks": int((bt.groupby("blk").size() == HOLD_MAIN).sum())}


def quintile_fwd(Z_shift, FWD, FUND, q=Q_MAIN, min_coins=MIN_COINS):
    acc = {i: [] for i in range(q)}
    for dt in Z_shift.index:
        x = Z_shift.loc[dt]; y = FWD.loc[dt]; fn = FUND.loc[dt]
        m = x.notna() & y.notna() & fn.notna()
        if m.sum() < min_coins:
            continue
        xr = x[m].rank(method="average")
        qq = pd.qcut(xr, q, labels=False, duplicates="drop")
        for i in range(q):
            sel = xr.index[qq == i]
            if len(sel):
                acc[i].append(float(y[sel].mean()))
    means = [float(np.mean(acc[i])) for i in range(q)]
    mono = float(stats.spearmanr(np.arange(q), means).correlation)
    return [round(m, 6) for m in means], round(mono, 4)


def xs_resid(Z, CTRL):
    """逐日橫截面對 CTRL 做 OLS 殘差化(兩者皆先 rank-z)。"""
    out = pd.DataFrame(np.nan, index=Z.index, columns=Z.columns)
    for dt in Z.index:
        x = Z.loc[dt]; c = CTRL.loc[dt]
        m = x.notna() & c.notna()
        if m.sum() < MIN_COINS:
            continue
        xz = rank_z(x[m]); cz = rank_z(c[m])
        b = float(np.dot(cz.values, xz.values) / np.dot(cz.values, cz.values))
        out.loc[dt, m[m].index] = (xz - b * cz).values
    return out


def xs_spearman_mean(A, B):
    vals = []
    for dt in A.index:
        x = A.loc[dt]; y = B.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS:
            r = stats.spearmanr(x[m], y[m]).correlation
            if np.isfinite(r):
                vals.append(r)
    return round(float(np.mean(vals)), 4), len(vals)


# ---------------- Phase 0 ----------------
def phase0():
    print(f"=== Phase 0:完整性 + 自 hash + 無前視斷言(鎖靜默:不列印任何聚合回測數字)===")
    uni, cb = load_books()
    fnd = pd.read_pickle(FUNDING_PKL)
    inter = sorted(set(uni) & set(cb))
    def idx_of(df): return pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
    per = []
    for c in inter:
        ib, ic_ = set(idx_of(uni[c])), set(idx_of(cb[c]))
        ov = sorted(ib & ic_)
        per.append({"coin": c, "n_bn": len(ib), "n_cb": len(ic_), "n_overlap": len(ov),
                    "ov_start": str(ov[0].date()) if ov else None,
                    "ov_end": str(ov[-1].date()) if ov else None,
                    "has_funding": bool(c in fnd)})
    ovn = pd.Series({p["coin"]: p["n_overlap"] for p in per})
    dv_bn, dv_cb = dollar_volumes(uni, cb)
    Z = panel(uni, cb)
    valid = Z.notna().sum(axis=1)
    vpos = valid[valid > 0]
    print(f"  兩所交集幣數: {len(inter)}   (universe {len(uni)} / coinbase {len(cb)})")
    print(f"  全域重疊日曆: {len(dv_bn)} 日  {dv_bn.index[0].date()} → {dv_bn.index[-1].date()}"
          f"  contiguous={len(pd.date_range(dv_bn.index[0], dv_bn.index[-1], freq='D')) == len(dv_bn)}")
    print(f"  逐幣重疊日數: min={ovn.min()} p25={int(ovn.quantile(.25))} median={int(ovn.median())} "
          f"p75={int(ovn.quantile(.75))} max={ovn.max()}  (>=1000 日: {(ovn >= 1000).sum()} 幣)")
    print(f"    覆蓋最少 5 幣: {ovn.sort_values().head(5).to_dict()}")
    print(f"  funding 覆蓋: {sum(p['has_funding'] for p in per)}/{len(inter)} 幣"
          f"  (缺: {[p['coin'] for p in per if not p['has_funding']]})")
    print(f"  過濾後有效交易日: {len(vpos)} 日  {vpos.index[0].date()} → {vpos.index[-1].date()}")
    print(f"  每日有效幣數分位: min={int(vpos.min())} p05={int(vpos.quantile(.05))} "
          f"p25={int(vpos.quantile(.25))} p50={int(vpos.quantile(.50))} "
          f"p75={int(vpos.quantile(.75))} p95={int(vpos.quantile(.95))} max={int(vpos.max())}")
    print(f"  minN<30 而整列 NaN 之日數: {int((valid == 0).sum())}(含 {int(63 + 28)} 日暖機)")

    # 無前視:截斷重算 vs 全樣本,容差 0
    la = []
    for T in ("2025-06-30", "2026-01-31"):
        Zt = panel(*load_books(T))
        A = Z.loc[:T].reindex(columns=Zt.columns)
        same_idx = bool(list(A.index) == list(Zt.index))
        eq = bool(same_idx and np.array_equal(A.values, Zt.values, equal_nan=True))
        la.append({"truncate_at": T, "index_match": same_idx, "identical_tol0": eq,
                   "n_rows": int(len(Zt))})
        print(f"  無前視斷言 T={T}: index_match={same_idx} identical(tol=0)={eq} rows={len(Zt)}")
    assert all(x["identical_tol0"] for x in la), "LOOK-AHEAD ASSERT FAIL"

    # funding 對齊自檢:交集幣在重疊期是否有洞
    FU = funding_panel(list(Z.columns), Z.index)
    fstart = {}
    for c in Z.columns:
        if c not in fnd:
            fstart[c] = None; continue
        fi = pd.to_datetime(fnd[c]["timestamp"], unit="ms").dt.normalize()
        fstart[c] = str(max(fi.min(), Z.index[0]).date())
    late = {c: v for c, v in fstart.items() if v and v > str(Z.index[0].date())}
    # 訊號有效但當日無 funding → 依 §7 該日剔除(不以 0 填)
    drop_cnt = (Z.notna() & FU.isna()).sum(axis=1)
    dpos = drop_cnt[valid > 0]
    print(f"  funding 起始晚於面板首日之幣: {len(late)} 檔 → {late}")
    print(f"  依 §7『無 funding 當日剔除』之每日剔除數: mean={dpos.mean():.2f} "
          f"p50={int(dpos.median())} max={int(dpos.max())}")
    out = {"sim_id": SIM, "phase": "0 (integrity, lock-silent)",
           "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
           "env": env_dict(),
           "files": {"universe": {"path": UNIVERSE_PKL, "sha256": sha256_file(UNIVERSE_PKL)},
                     "coinbase": {"path": COINBASE_PKL, "sha256": sha256_file(COINBASE_PKL)},
                     "funding": {"path": FUNDING_PKL, "sha256": sha256_file(FUNDING_PKL)},
                     "signal": {"path": SIG_PY, "sha256": sha256_file(SIG_PY)},
                     "runner": {"path": SELF_PY, "sha256": RUNNER_SHA}},
           "n_intersection": len(inter), "n_calendar_days": int(len(dv_bn)),
           "calendar": [str(dv_bn.index[0].date()), str(dv_bn.index[-1].date())],
           "per_coin_overlap": per,
           "overlap_summary": {"min": int(ovn.min()), "p25": int(ovn.quantile(.25)),
                               "median": int(ovn.median()), "p75": int(ovn.quantile(.75)),
                               "max": int(ovn.max()), "n_ge_1000": int((ovn >= 1000).sum())},
           "funding_coverage": {"n_with_funding": int(sum(p["has_funding"] for p in per)),
                                "missing": [p["coin"] for p in per if not p["has_funding"]],
                                "funding_start_after_panel_start": late,
                                "daily_dropped_for_no_funding": {
                                    "mean": round(float(dpos.mean()), 3),
                                    "median": int(dpos.median()), "max": int(dpos.max())}},
           "valid_coins_per_day": {"n_trading_days": int(len(vpos)),
                                   "first": str(vpos.index[0].date()), "last": str(vpos.index[-1].date()),
                                   "min": int(vpos.min()), "p05": int(vpos.quantile(.05)),
                                   "p25": int(vpos.quantile(.25)), "p50": int(vpos.quantile(.50)),
                                   "p75": int(vpos.quantile(.75)), "p95": int(vpos.quantile(.95)),
                                   "max": int(vpos.max())},
           "look_ahead_assertions": la, "pass": True}
    dump(INT_JSON, out)
    print("PHASE 0 PASS(未列印任何聚合回測數字)")


# ---------------- Phase 1:G1 可重現性鎖 ----------------
def phase1():
    if not (os.path.exists(INT_JSON) and json.load(open(INT_JSON)).get("pass")):
        print("HALT: Phase 0 未通過/不存在"); sys.exit(1)
    print("=== Phase 1:G1 可重現性鎖(主規格獨立跑兩次)===")
    keys = ("rank_ic_mean", "ic_t", "net_sharpe")
    runs = []
    for i in (1, 2):
        Z, FWD, FUND, *_ = build_main()
        Zs = Z.shift(1)
        ic = ic_series(Zs, FWD)
        bt = backtest(Zs, FWD, FUND)
        st = ic_stats(ic)
        r = pd.Series(bt["net"]).dropna()
        runs.append({"rank_ic_mean": float(ic.mean()), "ic_t": float(st["ic_t"]),
                     "net_sharpe": float(r.mean() / r.std(ddof=1) * ANN)})
    d = {k: abs(runs[0][k] - runs[1][k]) for k in keys}
    ok = all(v < 1e-8 for v in d.values())
    for k in keys:
        print(f"  {k}: run1={runs[0][k]:.12f} run2={runs[1][k]:.12f} |Δ|={d[k]:.3e}")
    out = {"sim_id": SIM, "phase": "1 (G1 replication lock)",
           "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
           "run1": runs[0], "run2": runs[1], "deltas": d, "tolerance": 1e-8, "pass": bool(ok)}
    if not ok:
        out["FAIL"] = "G1 replication tolerance exceeded"
        fail_dump(out); print("G1 LOCK FAIL → HALT"); sys.exit(1)
    dump(LOCK_JSON, out)
    print("G1 LOCK PASS")


# ---------------- Phase 2 + 3 + 4 ----------------
def phase2():
    for p, nm in [(INT_JSON, "integrity"), (LOCK_JSON, "replication_lock")]:
        if not (os.path.exists(p) and json.load(open(p)).get("pass")):
            print(f"HALT: {nm} 未通過/不存在"); sys.exit(1)

    R = {"sim_id": SIM, "phase": "2+3+4 (confirmatory batch + gates + disclosure)",
         "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
         "env": env_dict(), "runner_sha256": RUNNER_SHA,
         "spec": {"w": W_MAIN, "d": D_MAIN, "quantiles": Q_MAIN, "rebalance_days": HOLD_MAIN,
                  "hold_days": HOLD_MAIN, "cost_bps_per_unit_turnover": COST_MAIN,
                  "execution": "t signal @close, t+1 close entry (runner applies shift(1))",
                  "returns": "Binance close-to-close", "funding": "cash leg included (perp)"}}

    # ---- 主規格 ----
    Z, FWD, FUND, CLOSE, dv_bn, dv_cb = build_main()
    Zs = Z.shift(1)
    ic = ic_series(Zs, FWD)
    bt = backtest(Zs, FWD, FUND)
    st = ic_stats(ic)
    st["ic_t_nw_lag7"] = nw_t(ic, 7)
    net = bt["net"]; gross_c = bt["gross_net_cost"]; pre = bt["gross"]
    p_net, p_gross, p_pre = perf(net), perf(gross_c), perf(pre)
    wk = weekly_t(bt)
    qf, mono = quintile_fwd(Zs, FWD, FUND)
    years = len(bt) / 365.0
    ann_turn = float(bt["turn"].sum() / years)
    cost_drag = float(bt["cost"].mean() * 365)
    fund_contrib = float(bt["fund"].mean() * 365)
    short_pnl = -bt["short_r"]                      # 做空的價格 P&L(= Σ w_short·fwd)
    legs = {"long_leg_price_pnl": perf(bt["long_r"]),
            "short_leg_price_pnl": perf(short_pnl),
            "short_basket_raw_return": perf(bt["short_r"]),
            "long_leg_incl_funding": perf(bt["long_r"] + bt["long_f"]),
            "short_leg_incl_funding": perf(short_pnl + bt["short_f"]),
            "long_funding_ann": round(float(bt["long_f"].mean() * 365), 5),
            "short_funding_ann": round(float(bt["short_f"].mean() * 365), 5)}
    gap = (bt["long_r"] - bt["short_r"] - bt["gross"]).abs()
    leg_gap = {"max_abs_residual": float(gap.max()), "mean_abs_residual": float(gap.mean()),
               "assert_ok": bool(gap.max() < 1e-12)}

    R["phase2"] = {"ic": st, "quintile_fwd": qf, "mono": round(mono, 4),
                   "net": p_net, "gross_incl_cost_excl_funding": p_gross, "pre_cost": p_pre,
                   "weekly_nonoverlap": wk,
                   "ann_turnover_sum_abs_dw": round(ann_turn, 2),
                   "cost_drag_ann": round(cost_drag, 5),
                   "funding_contribution_ann": round(fund_contrib, 5),
                   "legs": legs, "leg_gap_assert": leg_gap,
                   "n_trading_days": int(len(bt)), "years": round(years, 3),
                   "n_no_funding_dropped_per_day_mean": round(float(bt["n_no_funding"].mean()), 4)}

    print("=== Phase 2:主規格 confirmatory(w=7, d=28, 五分位, 7/7, 10bps, funding 計入)===")
    print(f"  期間 {bt.index[0].date()} → {bt.index[-1].date()}  交易日 {len(bt)}  年數 {years:.2f}")
    print(f"  rank_ic_mean = {st['rank_ic_mean']}   ic_ir = {st['ic_ir']}   ic_t = {st['ic_t']}"
          f"   ic_t_NW(lag7) = {st['ic_t_nw_lag7']}   ic_n_days = {st['ic_n_days']}")
    print(f"  淨 Sharpe(成本+funding) = {p_net['sharpe']}   毛 Sharpe(含成本不含 funding) = {p_gross['sharpe']}"
          f"   pre-cost Sharpe = {p_pre['sharpe']}")
    print(f"  非重疊週 t = {wk['weekly_t']}  (n_blocks={wk['n_blocks']}, 完整週 {wk['n_complete_blocks']})")
    print(f"  mono = {mono:.4f}   quintile_fwd(Q1..Q5, 1日) = {qf}")
    print(f"  淨年化報酬 = {p_net['ann_return']}   MaxDD = {p_net['max_drawdown']}   日 t = {p_net['t_daily']}")
    print(f"  年換手(Σ|Δw|/年) = {ann_turn:.2f}   成本拖累/年 = {cost_drag:.5f}   funding 貢獻/年 = {fund_contrib:+.5f}")
    print(f"  腿記帳(價格 P&L): 多頭腿 ann={legs['long_leg_price_pnl']['ann_return']}"
          f" sharpe={legs['long_leg_price_pnl']['sharpe']}"
          f" | 空頭腿 ann={legs['short_leg_price_pnl']['ann_return']}"
          f" sharpe={legs['short_leg_price_pnl']['sharpe']}"
          f" (空頭籃子自身報酬 ann={legs['short_basket_raw_return']['ann_return']})")
    print(f"          含 funding: 多頭腿 ann={legs['long_leg_incl_funding']['ann_return']}"
          f" sharpe={legs['long_leg_incl_funding']['sharpe']}"
          f" | 空頭腿 ann={legs['short_leg_incl_funding']['ann_return']}"
          f" sharpe={legs['short_leg_incl_funding']['sharpe']}")
    print(f"          funding 年化: 多頭腿 {legs['long_funding_ann']:+.5f} / 空頭腿 {legs['short_funding_ann']:+.5f}")
    print(f"  腿和 gap: max|long - short - ls_gross| = {leg_gap['max_abs_residual']:.3e}"
          f"  mean = {leg_gap['mean_abs_residual']:.3e}  → {'OK' if leg_gap['assert_ok'] else 'MISMATCH'}")

    # ---- Phase 3 閘門 ----
    print("=== Phase 3:預註冊閘門判定 ===")
    G = {}
    # F1
    f1 = bool(st["rank_ic_mean"] < 0 or abs(st["ic_t"]) < 1.0)
    G["F1_fatal_ic"] = {"rule": "mean RankIC<0 or |IC_t|<1.0", "rank_ic_mean": st["rank_ic_mean"],
                        "ic_t": st["ic_t"], "hit": f1}
    # F2 季度集中
    qtr = net.groupby(pd.PeriodIndex(net.index, freq="Q")).sum()
    tot = float(qtr.sum())
    shares = (qtr / tot) if tot > 0 else qtr * np.nan
    top_q = str(shares.idxmax()) if tot > 0 else None
    f2 = bool(tot > 0 and float(shares.max()) > 0.60)
    G["F2_fatal_quarter"] = {"rule": "single calendar quarter contributes >60% of cumulative P&L",
                             "total_net_sum": round(tot, 5),
                             "max_quarter": top_q,
                             "max_share": (round(float(shares.max()), 4) if tot > 0 else None),
                             "quarter_shares": {str(k): round(float(v), 4) for k, v in shares.items()}
                             if tot > 0 else None, "hit": f2}
    # F3 剔除 2024
    ex24 = gross_c[~(gross_c.index.year == 2024)]
    p_ex24 = perf(ex24)
    f3 = bool(p_ex24.get("sharpe", 0.0) < 0.2)
    G["F3_fatal_ex2024"] = {"rule": "gross Sharpe (incl cost, excl funding) excluding 2024 < 0.2",
                            "gross_sharpe_ex2024": p_ex24.get("sharpe"), "n_days": p_ex24["n_days"],
                            "hit": f3}
    # G1
    lock = json.load(open(LOCK_JSON))
    G["G1_replication"] = {"rule": "two independent runs, key metrics |Δ|<1e-8",
                           "deltas": lock["deltas"], "pass": bool(lock["pass"])}
    # G2
    G["G2_ranking"] = {"rule": "rank_ic_mean>=+0.02 and ic_t>=2.4",
                       "rank_ic_mean": st["rank_ic_mean"], "ic_t": st["ic_t"],
                       "pass": bool(st["rank_ic_mean"] >= 0.02 and st["ic_t"] >= 2.4)}
    G["G2c_cap_sentinel"] = {"rule": "rank_ic_mean>0.15 → forced look-ahead audit",
                             "rank_ic_mean": st["rank_ic_mean"],
                             "triggered": bool(st["rank_ic_mean"] > 0.15)}
    # G3
    G["G3_dollar"] = {"rule": "net Sharpe>=1.0 and non-overlapping weekly t>=2.0",
                      "net_sharpe": p_net["sharpe"], "weekly_t": wk["weekly_t"],
                      "pass": bool(p_net["sharpe"] >= 1.0 and wk["weekly_t"] >= 2.0)}
    # G4
    G["G4_monotonic"] = {"rule": "quintile mono>=0.7", "mono": round(mono, 4),
                         "quintile_fwd": qf, "pass": bool(mono >= 0.7)}
    # G5 剔除成交額前 5 大幣(全期中位 dv_bn+dv_cb)
    med = (dv_bn + dv_cb).median()
    top5 = list(med.sort_values(ascending=False).head(5).index)
    Z5, FWD5, FUND5, *_ = build_main(drop_coins=top5)
    bt5 = backtest(Z5.shift(1), FWD5, FUND5)
    p5 = perf(bt5["net"])
    G["G5_capacity"] = {"rule": "drop top-5 by median (dv_bn+dv_cb): net Sharpe>=0.5 and same sign",
                        "dropped": top5,
                        "median_dv_usd": {c: round(float(med[c]), 1) for c in top5},
                        "net_sharpe_ex_top5": p5["sharpe"], "net_sharpe_full": p_net["sharpe"],
                        "n_coins_left": int(Z5.shape[1]),
                        "pass": bool(p5["sharpe"] >= 0.5 and
                                     np.sign(p5["sharpe"]) == np.sign(p_net["sharpe"]))}
    # G6 兩半符號一致
    h1 = net.loc[H1[0]:H1[1]]; h2 = net.loc[H2[0]:H2[1]]
    s1, s2 = float(h1.sum()), float(h2.sum())
    G["G6_subperiod"] = {"rule": "2023-01~2024-12 and 2025-01~2026-07 net return same sign",
                         "h1_sum_net": round(s1, 5), "h1_days": int(len(h1)),
                         "h1_sharpe": perf(h1).get("sharpe"),
                         "h2_sum_net": round(s2, 5), "h2_days": int(len(h2)),
                         "h2_sharpe": perf(h2).get("sharpe"),
                         "pass": bool(np.sign(s1) == np.sign(s2) and s1 != 0 and s2 != 0)}
    # G7 額外 lag+1
    ic_lag = ic_series(Z.shift(2), FWD)
    st_lag = ic_stats(ic_lag)
    G["G7_displacement"] = {"rule": "signal lag+1: IC sign unchanged and ic_t>=1.0",
                            "rank_ic_mean": st_lag["rank_ic_mean"], "ic_t": st_lag["ic_t"],
                            "pass": bool(np.sign(st_lag["rank_ic_mean"]) == np.sign(st["rank_ic_mean"])
                                         and st_lag["ic_t"] >= 1.0)}
    for k, v in G.items():
        if "hit" in v:
            print(f"  {k}: {'HIT (FATAL)' if v['hit'] else 'not hit'}  "
                  + json.dumps({a: b for a, b in v.items() if a not in ('rule', 'hit', 'quarter_shares')},
                               ensure_ascii=False))
        elif "pass" in v:
            print(f"  {k}: {'PASS' if v['pass'] else 'FAIL'}  "
                  + json.dumps({a: b for a, b in v.items() if a not in ('rule', 'pass', 'median_dv_usd')},
                               ensure_ascii=False))
        else:
            print(f"  {k}: triggered={v['triggered']}  rank_ic_mean={v['rank_ic_mean']}")
    fatal = [k for k in ("F1_fatal_ic", "F2_fatal_quarter", "F3_fatal_ex2024") if G[k]["hit"]]
    gates = {k: G[k]["pass"] for k in G if "pass" in G[k]}
    failed = [k for k, v in gates.items() if not v]
    verdict = "REJECT" if fatal else ("PASS" if not failed else "REWORK")
    R["phase3"] = {"gates": G, "fatal_hits": fatal, "failed_gates": failed,
                   "VERDICT_INPUT": verdict,
                   "note": "Builder 只計算與陳述,最終裁決屬 Arbiter"}
    print(f"  --- 必死命中: {fatal or '無'} ;失敗閘門: {failed or '無'}")
    print(f"  VERDICT_INPUT = {verdict}   (Builder 僅陳述,不裁決)")

    # ---- Phase 4 disclosure-only ----
    print("=== Phase 4:disclosure-only 診斷(明確標記,不得替補主規格)===")
    D = {"_label": "DISCLOSURE-ONLY — 不得替補主規格、不得 promote"}
    sens = {}
    for tag, kw in [("d14", dict(d=14)), ("d56", dict(d=56))]:
        Zx, FWDx, FUNDx, *_ = build_main(**kw)
        icx = ic_series(Zx.shift(1), FWDx); btx = backtest(Zx.shift(1), FWDx, FUNDx)
        sens[tag] = {**ic_stats(icx), "net_sharpe": perf(btx["net"])["sharpe"],
                     "weekly_t": weekly_t(btx)["weekly_t"]}
    for tag, kw in [("hold14", dict(hold=14)), ("tercile", dict(q=3))]:
        btx = backtest(Zs, FWD, FUND, **kw)
        sens[tag] = {"net_sharpe": perf(btx["net"])["sharpe"], "weekly_t_blocks": weekly_t(btx)["weekly_t"],
                     "ann_return": perf(btx["net"])["ann_return"]}
    D["sensitivity"] = sens
    for k, v in sens.items():
        print(f"  敏感度 {k}: {json.dumps(v, ensure_ascii=False)}")

    # 控制變數
    coins, index = list(Z.columns), Z.index
    MOM20 = CLOSE / CLOSE.shift(20) - 1.0
    S_bn = dv_bn.rolling(W_MAIN).sum(); S_cb = dv_cb.rolling(W_MAIN).sum()
    TOT7 = np.log(S_bn + S_cb); DVCHG = TOT7 - TOT7.shift(28)
    TOTD = np.log(dv_bn + dv_cb); DVCHG_RAW = TOTD - TOTD.shift(28)
    uni_raw, cb_raw = load_books()
    CB_CLOSE = close_panel(cb_raw, coins, index)
    lp = np.log(CB_CLOSE / CLOSE)
    XV = ((lp - lp.rolling(28).mean()) / lp.rolling(28).std(ddof=1))

    base_key = {}
    resid = {}
    for tag, CTRL in [("mom20", MOM20), ("dvchg28_smoothed", DVCHG), ("dvchg28_raw_daily", DVCHG_RAW)]:
        C = CTRL.shift(1)
        RES = xs_resid(Zs, C)
        mask = RES.notna()
        base_ic = ic_series(Zs.where(mask), FWD)
        res_ic = ic_series(RES, FWD)
        ratio = float(res_ic.mean() / base_ic.mean()) if base_ic.mean() != 0 else np.nan
        resid[tag] = {"base_ic_on_common_set": round(float(base_ic.mean()), 5),
                      "resid_ic": round(float(res_ic.mean()), 5),
                      "resid_ic_t": ic_stats(res_ic)["ic_t"],
                      "retention_ratio": round(ratio, 4), "n_days": int(len(res_ic))}
        base_key[tag] = ratio
        print(f"  §10.3 殘差化 vs {tag}: base_IC={resid[tag]['base_ic_on_common_set']} "
              f"resid_IC={resid[tag]['resid_ic']} 殘留={ratio:.1%} (t={resid[tag]['resid_ic_t']})")
    mom_dead = bool(base_key["mom20"] < 0.30 and base_key["dvchg28_smoothed"] < 0.30)
    resid["momentum_repackaging_self_kill"] = {
        "rule": "§10.3 both retentions <30% → self-declared dead", "hit": mom_dead}
    D["residualization"] = resid
    print(f"  §10.3 動能重包裝自判死(兩者皆 <30%): {mom_dead}")

    # §7 規模中性化
    med_all = (dv_bn + dv_cb).median()
    grp = pd.qcut(np.log(med_all.dropna()), 3, labels=False)
    Zg = Zs.copy()
    for g in sorted(grp.unique()):
        cols = [c for c in grp.index[grp == g] if c in Zg.columns]
        Zg[cols] = Zg[cols].sub(Zg[cols].mean(axis=1), axis=0)
    ic_g = ic_series(Zg, FWD)
    drop = float(1 - ic_g.mean() / ic.mean()) if ic.mean() != 0 else np.nan
    size_dead = bool(drop > 0.60)
    D["size_neutralized"] = {"rule": "§7 3 groups by log median dv, within-group demean; IC drop>60% → dead",
                             "base_ic": st["rank_ic_mean"], "neutralized_ic": round(float(ic_g.mean()), 5),
                             "neutralized_ic_t": ic_stats(ic_g)["ic_t"],
                             "ic_drop": round(drop, 4), "hit": size_dead,
                             "group_sizes": {int(g): int((grp == g).sum()) for g in sorted(grp.unique())}}
    print(f"  §7 規模中性化: base_IC={st['rank_ic_mean']} → {round(float(ic_g.mean()),5)}"
          f"  掉幅={drop:.1%}  自判死(>60%)={size_dead}")

    # §9 相關性
    corr = {}
    for tag, CTRL in [("xvenue_prem_z28", XV), ("dvchg28_smoothed", DVCHG), ("mom20", MOM20)]:
        r, n = xs_spearman_mean(Zs, CTRL.shift(1))
        corr[tag] = {"mean_xs_spearman": r, "n_days": n}
        print(f"  §9 相關 vs {tag}: 日均橫截面 Spearman = {r}  (n={n})")
    D["correlations"] = corr

    # IC 滯後約定的敏感度(判讀揭露:主規格 IC 用 shift(1) 可交易訊號)
    lagd = {}
    for lg, nm in [(0, "lag0_unshifted_t_signal"), (1, "lag1_MAIN_confirmatory"), (2, "lag2_G7")]:
        lagd[nm] = ic_stats(ic_series(Z.shift(lg), FWD))
    lagd["note"] = ("主規格 IC 採 shift(1)(= §4.11 t+1 收盤建倉之可交易訊號),G7 = 再 +1。"
                    "lag0 亦列出以證明 G2(>=0.02 且 t>=2.4)與 F1(|t|>=1.0)在兩種讀法下判定相同。")
    lagd["gate_invariance"] = {
        "G2_pass_at_lag0": bool(lagd["lag0_unshifted_t_signal"]["rank_ic_mean"] >= 0.02
                                and lagd["lag0_unshifted_t_signal"]["ic_t"] >= 2.4),
        "F1_hit_at_lag0": bool(lagd["lag0_unshifted_t_signal"]["rank_ic_mean"] < 0
                               or abs(lagd["lag0_unshifted_t_signal"]["ic_t"]) < 1.0)}
    D["ic_lag_convention"] = lagd
    print(f"  IC 滯後約定揭露: lag0 IC={lagd['lag0_unshifted_t_signal']['rank_ic_mean']}"
          f" t={lagd['lag0_unshifted_t_signal']['ic_t']} | lag1(主規格) IC={st['rank_ic_mean']} t={st['ic_t']}"
          f" | lag2(G7) IC={lagd['lag2_G7']['rank_ic_mean']} t={lagd['lag2_G7']['ic_t']}"
          f"  → G2 在 lag0 亦 FAIL={not lagd['gate_invariance']['G2_pass_at_lag0']}")

    D["turnover_definition"] = {"annual_sum_abs_dw": round(ann_turn, 2),
                                "annual_one_sided": round(ann_turn / 2, 2),
                                "note": "Σ|Δw| 同時含建倉與平倉兩側;單邊口徑 = Σ|Δw|/2"}
    D["no_funding_net_sharpe"] = {"note": "拼接假設量級標定 = 毛 Sharpe(含成本不含 funding)",
                                  "sharpe": p_gross["sharpe"], "ann_return": p_gross["ann_return"],
                                  "funding_contribution_ann": round(fund_contrib, 5)}
    print(f"  無 funding 版(含成本)Sharpe = {p_gross['sharpe']}  vs 含 funding 淨 Sharpe = {p_net['sharpe']}"
          f"  (funding 年化貢獻 {fund_contrib:+.5f})")
    R["phase4_disclosure_only"] = D
    dump(RES_JSON, R)
    print("=== 完成 ===")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "0": phase0()
    elif arg == "1": phase1()
    elif arg == "2": phase2()
    else:
        print(__doc__); sys.exit(2)
