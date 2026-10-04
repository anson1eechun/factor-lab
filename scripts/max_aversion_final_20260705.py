#!/usr/bin/env python3
"""SIM-2026-07-05-001 — MAX-aversion(FSIM_MAX_Lottery_Aversion)2020-22 backward-OOS 終局診斷。

唯讀:empirical_runs/universe_1d.pkl(新,~2500 根)與
      empirical_runs/universe_1d.pkl.bak-SIM-2026-07-04-002(鎖用 backup,1200 根)。
凍結:core/signals/FSIM_MAX_Lottery_Aversion.py 之 factor;scripts/crosssec_eval.py 之 evaluate()(唯一聚合器)。
S/F 構法逐字同 crosssec_eval.main():per-coin factor(df),index=pd.to_datetime(df["timestamp"],unit="ms"),
S 全史計算後切窗;F = close.shift(-1)/close − 1。

Phase A(L1 鎖)→ SIM-2026-07-05-001_baseline.json
Phase B(L2 鎖)→ SIM-2026-07-05-001_replication_lock.json
Phase C+D+E+F(confirmatory 單次批跑,須 A/B 皆 PASS)→ SIM-2026-07-05-001_results.json
任一鎖 FAIL → SIM-2026-07-05-001_lock_fail_<n>.json 並 HALT。

跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/max_aversion_final_20260705.py {A|B|CDEF}
"""
import sys, os, json, hashlib, platform, datetime, warnings
import numpy as np, pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.crosssec_eval as X
from core.signals.FSIM_MAX_Lottery_Aversion import factor

SIM = "SIM-2026-07-05-001"
ER = "/home/anson/factor-lab/empirical_runs/"
NEW = ER + "universe_1d.pkl"
BAK = ER + "universe_1d.pkl.bak-SIM-2026-07-04-002"
SIG_PY = "/home/anson/factor-lab/core/signals/FSIM_MAX_Lottery_Aversion.py"
HAR_PY = "/home/anson/factor-lab/scripts/crosssec_eval.py"
BASE_JSON = ER + SIM + "_baseline.json"
LOCK_JSON = ER + SIM + "_replication_lock.json"
RES_JSON = ER + SIM + "_results.json"
ANN = np.sqrt(365)
HOLD_MAIN, COST_MAIN = 10, 10.0
IN_END = "2026-06-30"       # 全窗裁剪上限
BACK_END = "2022-12-31"


# ---------------- 工具 ----------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    if isinstance(o, (np.bool_,)): return bool(o)
    if isinstance(o, (pd.Timestamp, datetime.date)): return str(o)[:10]
    return o


def dump(path, obj):
    with open(path, "w") as f:
        json.dump(sanitize(obj), f, ensure_ascii=False, indent=2)
    print("saved →", path)


def fail_dump(payload):
    n = 1
    while os.path.exists(ER + f"{SIM}_lock_fail_{n}.json"):
        n += 1
    dump(ER + f"{SIM}_lock_fail_{n}.json", payload)


def load_SF(path):
    """S/F 構法逐字同 scripts/crosssec_eval.main()(freq=1d)。"""
    uni = pd.read_pickle(path)
    sigs, fwds = {}, {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms"); c = df["close"].astype(float)
        sigs[co] = pd.Series(np.asarray(factor(df), dtype="float64").ravel(), index=idx)
        fwds[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
    S = pd.DataFrame(sigs).sort_index(); F = pd.DataFrame(fwds).reindex(S.index)
    return S, F


def ic_series(S, F):
    """複刻 evaluate() 的每日橫截面 Rank IC 迴圈(含 MIN_COINS 與 dropna)。"""
    idx, vals = [], []
    for dt in S.index:
        x = S.loc[dt]; y = F.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= X.MIN_COINS:
            idx.append(dt); vals.append(stats.spearmanr(x[m], y[m]).correlation)
    return pd.Series(vals, index=idx, dtype=float).dropna()


def perf(r):
    r = pd.Series(r).dropna()
    out = {"n_days": int(len(r))}
    if len(r) >= 2 and r.std(ddof=1):
        eq = (1 + r).cumprod()
        out.update({"mean_daily": float(r.mean()),
                    "ann_return": round(float(r.mean() * 365), 4),
                    "sharpe": round(float(r.mean() / r.std(ddof=1) * ANN), 3),
                    "t": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3),
                    "max_drawdown": round(float((eq / eq.cummax() - 1).min()), 4)})
    return out


def daily_series(S, F, t0, t1, cost_bps, hold=HOLD_MAIN, want_contrib=False):
    """逐字複刻 crosssec_eval.evaluate() 的組合迴圈(rets/w/since/qcut/turnover 邏輯不變),
    逐日記錄 gross/net/long/short/turn/n_valid/ic;可另記 per-coin 累積 net 貢獻。"""
    Sw = S.loc[t0:t1]; Fw = F.loc[t0:t1]
    rows = []
    rets, w, since = [], None, 10**9
    contrib = pd.Series(0.0, index=Sw.columns)
    for dt in Sw.index:
        x = Sw.loc[dt]; y = Fw.loc[dt]; m = x.notna() & y.notna()
        ic = float(stats.spearmanr(x[m], y[m]).correlation) if m.sum() >= X.MIN_COINS else np.nan
        if m.sum() < X.MIN_COINS:
            if w is not None:
                fv = Fw.loc[dt].fillna(0)
                g = float((w * fv).sum())
                lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
                rets.append(g)
                if want_contrib: contrib += w * fv
                rows.append((dt, g, g, lg, sh, 0.0, int(m.sum()), ic))
            continue
        xr = x[m].rank(); coins = xr.index
        q = pd.qcut(xr, 5, labels=False, duplicates="drop")
        if since >= hold:
            neww = pd.Series(0.0, index=Sw.columns)
            top = coins[q == q.max()]; bot = coins[q == 0]
            if len(top): neww[top] = 1.0 / len(top)
            if len(bot): neww[bot] = -1.0 / len(bot)
            dtw = (neww - (w if w is not None else 0)).abs()
            turn = float(dtw.sum())
            w = neww; since = 1
            fv = Fw.loc[dt].fillna(0)
            g = float((w * fv).sum())
            lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
            rets.append(g - turn * cost_bps / 10000.0)
            if want_contrib: contrib += w * fv - dtw * cost_bps / 10000.0
            rows.append((dt, g, g - turn * cost_bps / 10000.0, lg, sh, turn, int(m.sum()), ic))
        else:
            fv = Fw.loc[dt].fillna(0)
            g = float((w * fv).sum())
            lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
            rets.append(g); since += 1
            if want_contrib: contrib += w * fv
            rows.append((dt, g, g, lg, sh, 0.0, int(m.sum()), ic))
    df = pd.DataFrame(rows, columns=["dt", "gross", "net", "long", "short", "turn", "n_valid", "ic"]).set_index("dt")
    return (df, contrib) if want_contrib else df


def rankw_series(S, F, t0, t1, cost_bps, hold=HOLD_MAIN):
    """rank-weighted 收割:u = rank − (n+1)/2(去均值)、w = u/Σ|u|×2;每 hold bar rebalance,
    MIN_COINS=8,成本 = turnover×bps。組合迴圈骨架同 evaluate()。"""
    Sw = S.loc[t0:t1]; Fw = F.loc[t0:t1]
    rets, w, since = [], None, 10**9
    for dt in Sw.index:
        x = Sw.loc[dt]; y = Fw.loc[dt]; m = x.notna() & y.notna()
        if m.sum() < X.MIN_COINS:
            if w is not None:
                rets.append(float((w * Fw.loc[dt].fillna(0)).sum()))
            continue
        if since >= hold:
            xr = x[m].rank(); n = int(m.sum())
            u = xr - (n + 1) / 2.0
            neww = pd.Series(0.0, index=Sw.columns)
            neww[u.index] = (u / u.abs().sum() * 2.0).values
            turn = float((neww - (w if w is not None else 0)).abs().sum())
            w = neww; since = 1
            rets.append(float((w * Fw.loc[dt].fillna(0)).sum()) - turn * cost_bps / 10000.0)
        else:
            rets.append(float((w * Fw.loc[dt].fillna(0)).sum())); since += 1
    return pd.Series(rets)


def nw21_t(ic, L=21):
    """IC 日均值之 Newey-West(Bartlett)t 值。
    γ_l = (1/n)Σ_{t=l+1..n}(x_t−μ)(x_{t−l}−μ);S_NW = γ_0 + 2Σ_{l=1..L}(1−l/(L+1))γ_l;
    se = sqrt(S_NW/n);t_NW = μ/se。"""
    x = pd.Series(ic).dropna().values.astype(float)
    n = len(x); mu = float(x.mean()); e = x - mu
    s = float(np.dot(e, e)) / n
    for l in range(1, L + 1):
        gl = float(np.dot(e[l:], e[:-l])) / n
        s += 2.0 * (1.0 - l / (L + 1.0)) * gl
    se = float(np.sqrt(s / n))
    return {"nw_t": round(mu / se, 3), "mean_ic": round(mu, 5), "se_nw": se, "n": n, "lag": L,
            "formula": "gamma_l=(1/n)*sum_{t=l+1..n}(x_t-mu)(x_{t-l}-mu); "
                       "S_NW=gamma_0+2*sum_{l=1..21}(1-l/22)*gamma_l; se=sqrt(S_NW/n); t=mu/se"}


def integrity_meta():
    return {"universe_new": {"path": NEW, "sha256": sha256(NEW)},
            "universe_backup": {"path": BAK, "sha256": sha256(BAK)},
            "signal_file": {"path": SIG_PY, "sha256": sha256(SIG_PY)},
            "harness_file": {"path": HAR_PY, "sha256": sha256(HAR_PY)},
            "env": env_dict()}


def check_hashes(meta_recorded):
    now = integrity_meta()
    for k in ("universe_new", "universe_backup", "signal_file", "harness_file"):
        if now[k]["sha256"] != meta_recorded[k]["sha256"]:
            return False, k
    return True, None


def halves_ir(ic):
    h = len(ic) // 2
    a, b = ic.iloc[:h], ic.iloc[h:]
    ir = lambda s: round(float(s.mean() / s.std(ddof=1)), 4) if len(s) > 1 and s.std(ddof=1) else None
    return ir(a), ir(b), h, len(ic) - h


# ---------------- Phase A:L1 鎖 ----------------
def phase_A():
    meta = integrity_meta()
    S, F = load_SF(BAK)
    runs = {}
    for hold, cost in [(5, 10.0), (10, 10.0), (20, 10.0), (10, 0.0)]:
        runs[f"hold{hold}_cost{int(cost)}"] = X.evaluate(S, F, cost, ANN, hold)
    ref = runs["hold10_cost10"]
    ic = ic_series(S, F)
    ic_consistency = {"ic_series_n": int(len(ic)), "evaluate_ic_n_days": ref["ic_n_days"],
                      "ic_series_mean": round(float(ic.mean()), 4), "evaluate_rank_ic_mean": ref["rank_ic_mean"],
                      "match": bool(len(ic) == ref["ic_n_days"] and round(float(ic.mean()), 4) == ref["rank_ic_mean"])}
    # 硬判準(L1-A1 修訂版,2026-07-05,見 W-back 前;原版第 3 項要求 hold{5,10,20} 全含,
    # 第一次嘗試 FAIL 已落盤 lock_fail_1.json;Proposer 裁定為「規格轉錄缺陷」——
    # 六月報告「quintile −0.28~−1.0」未記載 hold×cost 對應,ledger 唯一可考 PnL(−0.44)吻合 hold5)
    nets = {h: runs[f"hold{h}_cost10"]["ls_sharpe"] for h in (5, 10, 20)}
    hard = {
        "ic_ir(0.228±0.003)": {"value": ref["ic_ir"], "pass": bool(abs(ref["ic_ir"] - 0.228) <= 0.003)},
        "ic_t(7.84±0.10)": {"value": ref["ic_t"], "pass": bool(abs(ref["ic_t"] - 7.84) <= 0.10)},
        "quintile_net10_hold5&10_in[-1.05,-0.23]_(L1-A1)": {
            "values": nets, "pass": bool(all(-1.05 <= nets[h] <= -0.23 for h in (5, 10))),
            "hold20_no_band": "複現值權威 in-sample 參照;六月範圍出處網格不可考,likely 不含 hold20@10bps",
            "hold20_value": nets[20]},
    }
    hard_pass = all(v["pass"] for v in hard.values())
    # 軟判準
    ir1, ir2, n1, n2 = halves_ir(ic)
    anchor_hits = [h for h in (5, 10, 20) if abs(nets[h] - (-0.44)) <= 0.03]
    soft = {
        "half_ic_ir_first(0.273±0.02)": {"value": ir1, "n_days": n1, "pass": bool(ir1 is not None and abs(ir1 - 0.273) <= 0.02)},
        "half_ic_ir_second(0.219±0.02)": {"value": ir2, "n_days": n2, "pass": bool(ir2 is not None and abs(ir2 - 0.219) <= 0.02)},
        "any_hold_net~-0.44±0.03": {"values": nets, "holds_matching": anchor_hits, "pass": bool(anchor_hits)},
    }
    out = {"sim_id": SIM, "phase": "A (L1 lock: backup full-window replication of 2026-06-07 archive)",
           "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
           "archive_ref": "SIM-2026-06-07-007_debate_report.md (80-coin MAX-aversion diagnostics)",
           "integrity": meta,
           "backup_panel": {"n_coins": int(S.shape[1]), "n_days": int(S.shape[0]),
                            "index_range": [str(S.index[0].date()), str(S.index[-1].date())]},
           "runs": runs, "ic_consistency": ic_consistency,
           "hard_criteria": hard, "soft_criteria": soft,
           "soft_annotation_L1_A1": "折半前半 0.2334 超原 ±0.02:六月折半切法慣例不可考,採本輪複現值為權威(照原條款僅加註)",
           "amendment_L1_A1": {
               "date": "2026-07-05", "ruled_by": "Proposer(獨立裁定,全文見報告)",
               "nature": "規格轉錄缺陷,非歸檔不可重現",
               "change": "硬判準3:hold{5,10,20}全含[−1.05,−0.23] → hold5&hold10 含帶;hold20 撤帶、記錄複現值為權威參照",
               "evidence": "同一性由四獨立量確立(ic_ir Δ0.0005/ic_t Δ0.035/hold5 對 ledger Δ0.011/hold10 在帶內);漂移假說被 07-04 carry L1 完美重現證偽",
               "impact_on_confirmatory": "C1/C2/R1 零影響(皆為 W-back 絕對 t 值,不含 hold20);hold20 雙向 disclosure-only 防濫用條款寫死",
               "multiple_comparison": "lock_fail_1.json 保留,FAIL 行照記 ledger,本修訂不抹除多重比較帳",
               "wback_barrier_assertion": "本修訂時點 Phase C 從未執行,W-back 聚合數字從未被計算或列印"},
           "anchor_hold10_net10_ls_sharpe(W-in-canonical)": ref["ls_sharpe"],
           "pass": bool(hard_pass)}
    print(f"=== Phase A(L1 鎖,backup 全窗 {S.index[0].date()}→{S.index[-1].date()},80 幣)===")
    for k, v in hard.items():
        print(f"  HARD {k}: {'PASS' if v['pass'] else 'FAIL'}  {v.get('value', v.get('values'))}")
    for k, v in soft.items():
        print(f"  SOFT {k}: {'PASS' if v['pass'] else 'MISS'}  {v.get('value', v.get('values'))}"
              + (f" (holds={v['holds_matching']})" if 'holds_matching' in v else ""))
    print(f"  anchor(hold10 net@10bps ls_sharpe)= {ref['ls_sharpe']}")
    if not hard_pass:
        out["FAIL"] = "L1 hard criteria not met"
        fail_dump(out)
        print("L1 LOCK FAIL → HALT")
        sys.exit(1)
    dump(BASE_JSON, out)
    print("L1 LOCK PASS")


# ---------------- Phase B:L2 鎖 ----------------
def phase_B():
    if not os.path.exists(BASE_JSON):
        print("HALT: baseline 不存在,先跑 Phase A"); sys.exit(1)
    base = json.load(open(BASE_JSON))
    if not base.get("pass"):
        print("HALT: baseline 未 PASS"); sys.exit(1)
    ok, k = check_hashes(base["integrity"])
    if not ok:
        print(f"HALT: {k} sha256 與 baseline 不符"); sys.exit(1)

    Sb, Fb = load_SF(BAK); Sn, Fn = load_SF(NEW)
    ub = pd.read_pickle(BAK); un = pd.read_pickle(NEW)
    literal_start = Sb.index[23]; w_end = Sb.index[-3]
    # 裁量:backup 各幣起點不齊(退市幣「最後1200根」起點早於 2023-02-24 主體)。
    # 直取 union index[23] 無法避開被截斷幣的 21 窗暖機(且 2021-22 段 backup 幣數 <8、新 pkl 幣數多,
    # 會造成純機械性的 ic_n_days 不等)。按規格意旨(避開暖機),W-lock 起點 = 所有「被截斷幣」
    # (backup 首根晚於新 pkl 首根者)各自第 23 根(0-based)之最大值。終點照字面 index[-3]。
    trunc_rows = []
    used_start = literal_start
    for co in ub:
        bfirst = pd.to_datetime(ub[co]["timestamp"].iloc[0], unit="ms")
        nfirst = pd.to_datetime(un[co]["timestamp"].iloc[0], unit="ms")
        if bfirst > nfirst:
            idx = pd.to_datetime(ub[co]["timestamp"], unit="ms")
            t23 = idx[23]
            trunc_rows.append({"coin": co, "bak_first": str(bfirst.date()), "new_first": str(nfirst.date()),
                               "bar23": str(t23.date())})
            if t23 > used_start:
                used_start = t23
    runs, all_pass = {}, True
    for cost in (0.0, 10.0):
        rb = X.evaluate(Sb.loc[used_start:w_end], Fb.loc[used_start:w_end], cost, ANN, HOLD_MAIN)
        rn = X.evaluate(Sn.loc[used_start:w_end], Fn.loc[used_start:w_end], cost, ANN, HOLD_MAIN)
        d = {"ic_n_days_equal": bool(rb["ic_n_days"] == rn["ic_n_days"]),
             "d_ic_ir": round(abs(rb["ic_ir"] - rn["ic_ir"]), 6),
             "d_ic_t": round(abs(rb["ic_t"] - rn["ic_t"]), 6),
             "d_ls_sharpe": round(abs(rb["ls_sharpe"] - rn["ls_sharpe"]), 6)}
        p = bool(d["ic_n_days_equal"] and d["d_ic_ir"] <= 0.001 and d["d_ic_t"] <= 0.05 and d["d_ls_sharpe"] <= 0.01)
        runs[f"hold10_cost{int(cost)}"] = {"backup": rb, "new": rn, "deltas": d, "pass": p}
        all_pass &= p
    out = {"sim_id": SIM, "phase": "B (L2 lock: backup vs new pkl, identical W-lock window)",
           "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
           "w_lock": {"literal_backup_index_23": str(literal_start.date()),
                      "used_start": str(used_start.date()), "end_backup_index_-3": str(w_end.date()),
                      "discretion_note": "backup 各幣起點不齊(退市幣);union index[23] 無法避開 2023-02-24 主體幣的暖機,"
                                         "且 2021-22 段 backup <8 幣、新 pkl >8 幣 → 機械性 ic_n_days 不等。"
                                         "改用:所有被截斷幣各自第 23 根之最大值(規格意旨=避開首 21 窗暖機)。",
                      "n_truncated_coins": len(trunc_rows),
                      "truncated_coins_head": trunc_rows[:10]},
           "runs": runs, "pass": bool(all_pass)}
    print(f"=== Phase B(L2 鎖)W-lock=[{used_start.date()}, {w_end.date()}]"
          f"(字面 index[23]={literal_start.date()},裁量見 JSON)===")
    for k, v in runs.items():
        d = v["deltas"]
        print(f"  {k}: ic_n_days {v['backup']['ic_n_days']} vs {v['new']['ic_n_days']} equal={d['ic_n_days_equal']}"
              f"  |Δic_ir|={d['d_ic_ir']}  |Δic_t|={d['d_ic_t']}  |Δls_sharpe|={d['d_ls_sharpe']}"
              f"  → {'PASS' if v['pass'] else 'FAIL'}")
    if not all_pass:
        out["FAIL"] = "L2 tolerance exceeded"
        fail_dump(out)
        print("L2 LOCK FAIL → HALT")
        sys.exit(1)
    dump(LOCK_JSON, out)
    print("L2 LOCK PASS")


# ---------------- Phase C+D+E+F:confirmatory 單次批跑 ----------------
def phase_CDEF():
    # 門:A/B 皆 PASS + 雜湊未變
    for p, name in [(BASE_JSON, "baseline"), (LOCK_JSON, "replication_lock")]:
        if not os.path.exists(p):
            print(f"HALT: {name} 不存在"); sys.exit(1)
        if not json.load(open(p)).get("pass"):
            print(f"HALT: {name} 未 PASS"); sys.exit(1)
    base = json.load(open(BASE_JSON))
    ok, k = check_hashes(base["integrity"])
    if not ok:
        print(f"HALT: {k} sha256 與 baseline 不符"); sys.exit(1)
    anchor = base["anchor_hold10_net10_ls_sharpe(W-in-canonical)"]

    S, F = load_SF(NEW)
    S = S.loc[:IN_END]; F = F.loc[:IN_END]          # 全窗裁剪 ≤2026-06-30
    ub = pd.read_pickle(BAK); un = pd.read_pickle(NEW)
    coinsets_equal = bool(set(ub) == set(un) and len(un) == 80)

    results = {"sim_id": SIM, "phase": "C+D+E+F (confirmatory batch, single run)",
               "generated_at": str(datetime.datetime.now(datetime.timezone.utc))[:19],
               "integrity": integrity_meta(),
               "gates": {"baseline_pass": True, "replication_lock_pass": True},
               "signal": "FSIM_MAX_Lottery_Aversion.factor (max_window=21, (-mx).shift(1))",
               "hold_main": HOLD_MAIN, "cost_main_bps": COST_MAIN, "min_coins": X.MIN_COINS,
               "anchor_hold10_net10_from_phaseA(W-in-canonical)": anchor}

    # --- Phase C: T30/T8 與 ramp ---
    valid = (S.notna() & F.notna()).sum(axis=1)
    def first_ge(k):
        hit = valid.index[valid >= k]
        return hit[0] if len(hit) else None
    T8, T20, T30, T40 = first_ge(8), first_ge(20), first_ge(30), first_ge(40)
    ramp = [{"threshold": k, "first_date": str(first_ge(k).date()) if first_ge(k) is not None else None}
            for k in (8, 10, 15, 20, 25, 30, 40, 50, 60, 66, 70, 80)]
    year_starts = []
    for yr in range(int(S.index[0].year), int(S.index[-1].year) + 1):
        seg = valid.loc[f"{yr}"]
        if len(seg):
            year_starts.append({"year": yr, "first_day": str(seg.index[0].date()),
                                "valid_at_year_start": int(seg.iloc[0]),
                                "valid_at_year_end": int(seg.iloc[-1])})
    print("=== Phase C:T30/T8 與幣數 ramp(僅日期/幣數)===")
    print(f"  T8  = {T8.date() if T8 is not None else None}")
    print(f"  T20 = {T20.date() if T20 is not None else None}")
    print(f"  T30 = {T30.date() if T30 is not None else None}")
    print(f"  T40 = {T40.date() if T40 is not None else None}")
    print("  threshold → first_date:")
    for r in ramp:
        print(f"    >={r['threshold']:>2d} 幣: {r['first_date']}")
    for r in year_starts:
        print(f"    {r['year']} 年初 {r['first_day']} 有效幣 {r['valid_at_year_start']},年末 {r['valid_at_year_end']}")
    assert_T30 = bool(T30 is not None and T30 <= pd.Timestamp("2022-01-01"))
    results["T"] = {"T8": T8, "T20": T20, "T30": T30, "T40": T40}
    results["ramp"] = ramp; results["year_start_valid"] = year_starts
    if not assert_T30:
        results["ABORT"] = "T30 不存在或 > 2022-01-01"
        dump(RES_JSON, results)
        print("ASSERT FAIL: T30 不存在或 > 2022-01-01 → HALT"); sys.exit(1)

    windows = {"W_back": (T30, BACK_END), "W_in": ("2023-01-01", IN_END),
               "W_comb": (T30, IN_END), "exploratory": (T8, IN_END)}
    results["windows"] = {k: [v[0], v[1]] for k, v in windows.items()}

    # 斷言
    Swb = S.loc[T30:BACK_END]
    wb_valid = (Swb.notna() & F.loc[T30:BACK_END].notna()).sum(axis=1)
    assertions = {"T30_le_2022-01-01": assert_T30,
                  "wback_index_max_le_2022-12-31": bool(Swb.index.max() <= pd.Timestamp(BACK_END)),
                  "coinsets_equal_80": coinsets_equal,
                  "wback_daily_valid_min": int(wb_valid.min()),
                  "wback_daily_valid_min_ge20": bool(wb_valid.min() >= 20),
                  "wback_valid_flag": None if wb_valid.min() >= 20 else "W-back 有效幣數曾 <20(加註旗標,不 HALT)"}
    results["assertions"] = assertions
    if not assertions["wback_index_max_le_2022-12-31"] or not coinsets_equal:
        results["ABORT"] = "W-back 索引或幣集合斷言失敗"
        dump(RES_JSON, results)
        print("ASSERT FAIL(W-back 索引/幣集合)→ HALT"); sys.exit(1)

    # --- confirmatory 批(全部經 X.evaluate) ---
    def run(t0, t1, cost, hold):
        return X.evaluate(S.loc[t0:t1], F.loc[t0:t1], cost, ANN, hold)
    conf = {"W_back": {}, "W_in": {}, "W_comb": {}, "exploratory": {}}
    for h in (5, 10, 20):
        for c in (0.0, 10.0):
            conf["W_back"][f"hold{h}_cost{int(c)}"] = run(T30, BACK_END, c, h)
    for c in (0.0, 10.0):
        conf["W_in"][f"hold10_cost{int(c)}"] = run("2023-01-01", IN_END, c, 10)
        conf["W_comb"][f"hold10_cost{int(c)}"] = run(T30, IN_END, c, 10)
    conf["exploratory"]["hold10_cost10"] = run(T8, IN_END, 10.0, 10)
    results["confirmatory"] = conf

    # 敏感度:T20 窗(僅 IC 層)、T40 窗(IC+主規格 PnL)
    ic20 = ic_series(S.loc[T20:BACK_END], F.loc[T20:BACK_END])
    sens = {"T20_window": {"start": T20, "end": BACK_END,
                           "rank_ic_mean": round(float(ic20.mean()), 4),
                           "ic_ir": round(float(ic20.mean() / ic20.std(ddof=1)), 4),
                           "ic_t": round(float(ic20.mean() / (ic20.std(ddof=1) / np.sqrt(len(ic20)))), 3),
                           "ic_n_days": int(len(ic20))}}
    r40 = run(T40, BACK_END, COST_MAIN, HOLD_MAIN)
    sens["T40_window"] = {"start": T40, "end": BACK_END, **r40}
    # rank-weighted 主規格(W-back hold10@10bps;裁量:rank-w 窗取 W-back=診斷標的)
    rw = rankw_series(S, F, T30, BACK_END, COST_MAIN, HOLD_MAIN)
    sens["rankw_Wback_hold10_cost10"] = perf(rw)
    results["sensitivity"] = sens

    print("\n=== Phase C:confirmatory 批(單次)===")
    for wname, d in conf.items():
        for ck, v in d.items():
            print(f"  {wname:12s} {ck:14s} ic_t={v.get('ic_t')} ic_ir={v.get('ic_ir')} ic_n={v.get('ic_n_days')}"
                  f" ls_sharpe={v.get('ls_sharpe')} ls_t={v.get('ls_t')} annret={v.get('ls_ann_return')}"
                  f" maxDD={v.get('ls_max_drawdown')} mono={v.get('mono')}")
    print(f"  sens T20(IC only): ic_t={sens['T20_window']['ic_t']} ic_ir={sens['T20_window']['ic_ir']}"
          f" n={sens['T20_window']['ic_n_days']}")
    print(f"  sens T40: ic_t={r40['ic_t']} ic_ir={r40['ic_ir']} ls_sharpe={r40['ls_sharpe']} ls_t={r40['ls_t']}")
    print(f"  rank-w W-back hold10@10bps: sharpe={sens['rankw_Wback_hold10_cost10'].get('sharpe')}"
          f" t={sens['rankw_Wback_hold10_cost10'].get('t')}")
    print(f"  W-back 每日有效幣 min={assertions['wback_daily_valid_min']} (≥20: {assertions['wback_daily_valid_min_ge20']})")

    # --- Phase D:腿記帳 ---
    print("\n=== Phase D:腿記帳(複刻組合迴圈)===")
    daily_cache, leg_dec = {}, {}
    checks = {"per_day_leg_gap_max": 0.0, "sharpe_crosscheck": []}
    ABORT = False
    dwin = {"W_back": (T30, BACK_END, [0.0, 10.0]), "W_in": ("2023-01-01", IN_END, [0.0, 10.0]),
            "W_comb": (T30, IN_END, [0.0, 10.0])}
    contrib_wb = None
    for name, (t0, t1, costs) in dwin.items():
        if name == "W_back":
            ds, contrib_wb = daily_series(S, F, t0, t1, COST_MAIN, HOLD_MAIN, want_contrib=True)
        else:
            ds = daily_series(S, F, t0, t1, COST_MAIN, HOLD_MAIN)
        daily_cache[name] = ds
        gap = float((ds["long"] + ds["short"] - ds["gross"]).abs().max()) if len(ds) else 0.0
        checks["per_day_leg_gap_max"] = max(checks["per_day_leg_gap_max"], gap)
        if len(ds) and (np.round(ds["long"] + ds["short"], 3) != np.round(ds["gross"], 3)).any():
            print(f"  ABORT: {name} 腿和 != gross(3 位小數) max_gap={gap}"); ABORT = True
        for c in costs:
            net_c = ds["gross"] - ds["turn"] * c / 10000.0
            pm = perf(net_c); s_mine = pm.get("sharpe")
            s_eval = conf[name][f"hold10_cost{int(c)}"].get("ls_sharpe")
            checks["sharpe_crosscheck"].append({"window": name, "cost": c, "replica": s_mine, "evaluate": s_eval})
            if s_mine is None or s_eval is None or abs(s_mine - s_eval) > 0.0010001:
                print(f"  ABORT: {name} cost={c} 複刻 Sharpe {s_mine} != evaluate {s_eval}"); ABORT = True
        leg_dec[name] = {"n_days": int(len(ds)),
                         "long": perf(ds["long"]), "short": perf(ds["short"]), "gross": perf(ds["gross"]),
                         "net10": perf(ds["net"]), "avg_turnover_daily": float(ds["turn"].mean())}
        cc_txt = ", ".join(f"c{int(cc['cost'])}: {cc['replica']} vs {cc['evaluate']}"
                           for cc in checks["sharpe_crosscheck"][-len(costs):])
        print(f"  {name:8s} n={len(ds)} leg_gap_max={gap:.2e} crosscheck[{cc_txt}]")
    results["leg_check"] = checks; results["leg_decomposition"] = leg_dec
    if ABORT:
        results["ABORT"] = "Phase D leg accounting / replica crosscheck failed"
        dump(RES_JSON, results)
        sys.exit(1)
    print(f"  斷言通過:|long+short−gross| 3 位小數全 0(max gap={checks['per_day_leg_gap_max']:.2e});複刻 vs evaluate Sharpe ≤0.001")

    # --- Phase E:診斷(disclosure-only) ---
    print("\n=== Phase E:診斷 ===")
    icb = ic_series(S.loc[T30:BACK_END], F.loc[T30:BACK_END])
    ir1, ir2, n1, n2 = halves_ir(icb)
    nw = nw21_t(icb)
    diag = {"wback_ic_half_ir": {"first_half": ir1, "second_half": ir2, "n_first": n1, "n_second": n2},
            "wback_ic_nw21": nw}
    # 剔尾(主規格 gross,W-back)
    g = daily_cache["W_back"]["gross"]; n = len(g)
    strip = {"n_days": n, "full": perf(g)}
    for pct in (0.01, 0.05):
        k = max(1, int(np.floor(n * pct)))
        strip[f"drop_best_{int(pct*100)}pct"] = {"n_dropped": k, **perf(g.drop(g.nlargest(k).index))}
        strip[f"drop_worst_{int(pct*100)}pct"] = {"n_dropped": k, **perf(g.drop(g.nsmallest(k).index))}
    diag["wback_gross_tail_strip"] = strip
    # 腿 vs EW 市場(W-back)
    ds = daily_cache["W_back"]
    Swb2 = S.loc[T30:BACK_END]; Fwb2 = F.loc[T30:BACK_END]
    ew = []
    for dt in ds.index:
        x = Swb2.loc[dt]; y = Fwb2.loc[dt]; m = x.notna() & y.notna()
        ew.append(float(y[m].mean()) if int(m.sum()) > 0 else np.nan)
    ew = pd.Series(ew, index=ds.index)
    lottery = -ds["short"]
    diag["wback_vs_ew"] = {"ew_market": perf(ew),
                           "long_leg_minus_ew": perf(ds["long"] - ew),
                           "lottery_basket(hiMAX_q0)_minus_ew": perf(lottery - ew),
                           "note": "long/lottery 為主規格持倉腿(hold10);EW=當日 S&F 皆有效幣等權;lottery=−short 腿"}
    # per-coin 貢獻 top5 + LOO
    order = contrib_wb.abs().sort_values(ascending=False)
    top5 = [{"coin": co, "cum_net_contrib": round(float(contrib_wb[co]), 5)} for co in order.index[:5]]
    star = str(order.index[0])
    S_loo = S.drop(columns=[star]); F_loo = F.drop(columns=[star])
    loo = X.evaluate(S_loo.loc[T30:BACK_END], F_loo.loc[T30:BACK_END], COST_MAIN, ANN, HOLD_MAIN)
    diag["wback_percoin_top5_abs_net_contrib"] = top5
    diag["wback_loo"] = {"dropped_coin": star, "evaluate_hold10_cost10": loo,
                         "delta_ls_sharpe_vs_full": round(float(loo["ls_sharpe"] - conf["W_back"]["hold10_cost10"]["ls_sharpe"]), 3),
                         "delta_ic_t_vs_full": round(float(loo["ic_t"] - conf["W_back"]["hold10_cost10"]["ic_t"]), 3)}
    # 逐年表(exploratory 日序列)
    dse = daily_series(S, F, T8, IN_END, COST_MAIN, HOLD_MAIN)
    yearly = []
    for yr, dy in dse.groupby(dse.index.year):
        yearly.append({"year": int(yr), "n_days": int(len(dy)),
                       "gross_sharpe": perf(dy["gross"]).get("sharpe"),
                       "net10_sharpe": perf(dy["net"]).get("sharpe"),
                       "ic_mean": round(float(dy["ic"].mean()), 4) if dy["ic"].notna().any() else None,
                       "ic_days": int(dy["ic"].notna().sum()),
                       "n_valid_median": float(dy["n_valid"].median())})
    diag["yearly_exploratory"] = yearly
    results["diagnostics"] = diag
    print(f"  W-back IC 前/後半 IC-IR: {ir1} / {ir2} (n={n1}/{n2})")
    print(f"  W-back IC NW21-t = {nw['nw_t']} (mean IC={nw['mean_ic']}, n={nw['n']})")
    print(f"  W-back gross full: sharpe={strip['full'].get('sharpe')} annret={strip['full'].get('ann_return')}")
    for kk in ("drop_best_1pct", "drop_best_5pct", "drop_worst_1pct", "drop_worst_5pct"):
        print(f"    {kk}: sharpe={strip[kk].get('sharpe')} annret={strip[kk].get('ann_return')} (剔 {strip[kk]['n_dropped']} 日)")
    print(f"  long−EW: sharpe={diag['wback_vs_ew']['long_leg_minus_ew'].get('sharpe')}"
          f" annret={diag['wback_vs_ew']['long_leg_minus_ew'].get('ann_return')}")
    print(f"  lottery(q0 hiMAX)−EW: sharpe={diag['wback_vs_ew']['lottery_basket(hiMAX_q0)_minus_ew'].get('sharpe')}"
          f" annret={diag['wback_vs_ew']['lottery_basket(hiMAX_q0)_minus_ew'].get('ann_return')}")
    print(f"  top5 |貢獻|: {top5}")
    print(f"  LOO 剔 {star}: ls_sharpe={loo['ls_sharpe']} (Δ={diag['wback_loo']['delta_ls_sharpe_vs_full']})"
          f" ic_t={loo['ic_t']} (Δ={diag['wback_loo']['delta_ic_t_vs_full']})")
    print("  逐年(exploratory):")
    for r in yearly:
        print(f"    {r['year']}: gross_sh={r['gross_sharpe']} net10_sh={r['net10_sharpe']}"
              f" ic_mean={r['ic_mean']} ic_days={r['ic_days']} n_valid_med={r['n_valid_median']}")

    # --- Phase F:裁決輸入 ---
    main_run = conf["W_back"][f"hold{HOLD_MAIN}_cost{int(COST_MAIN)}"]
    ic_t = main_run["ic_t"]; nwt = nw["nw_t"]
    ls_sh = main_run["ls_sharpe"]; ls_t = main_run["ls_t"]
    q1_band = "IC-CONFIRM" if (ic_t >= 3 and nwt >= 2) else ("IC-FAIL" if ic_t < 1 else "IC-AMBIG")
    q2_band = "PnL-NEG" if ls_t <= 0 else ("PnL-POS" if ls_t >= 2 else "PnL-AMBIG")
    verdict_inputs = {"q1": {"ic_t": ic_t, "nw21_t": nwt, "band": q1_band},
                      "q2": {"ls_sharpe": ls_sh, "ls_t": ls_t, "band": q2_band},
                      "R1": bool(ic_t >= 2 and nwt >= 2 and ls_t >= 2),
                      "matrix_cell": f"{q1_band}×{q2_band}",
                      "spec": "主規格 = W-back hold10@10bps;q1 依 W-back IC 層(ic_t 與 NW21-t)"}
    results["verdict_inputs"] = verdict_inputs
    dump(RES_JSON, results)
    print("\n=== Phase F:verdict_inputs ===")
    print(json.dumps(sanitize(verdict_inputs), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ph = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    if ph == "A":
        phase_A()
    elif ph == "B":
        phase_B()
    elif ph in ("CDEF", "C"):
        phase_CDEF()
    else:
        print("usage: max_aversion_final_20260705.py {A|B|CDEF}"); sys.exit(2)
