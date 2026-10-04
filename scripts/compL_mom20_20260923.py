#!/usr/bin/env python3
"""SIM-2026-09-23-001：comp_L ⊥ Mom20（priority-0 confirmatory）。

規格、判準與控制變數適格性全部凍結於 empirical_runs/SIM-2026-09-23-001_prereg.md。
所有組合與統計工具直接 import 上輪 scripts/asd_20260914.py，不重寫，
確保與上輪逐位同口徑。

  uv run --with "numpy>=2" --with pandas --with scipy python scripts/compL_mom20_20260923.py lock
  uv run ... scripts/compL_mom20_20260923.py run
"""
import sys, os, json, datetime
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asd_20260914 as A          # 上輪 harness：load_all/backtest/ic_series/xs_resid/_rank_xs/perf/nw_t
M = A.M

SIM = "SIM-2026-09-23-001"
ER = A.ER
PREREG = ER + SIM + "_prereg.md"
LOCK = ER + SIM + "_replication_lock.json"
RES = ER + SIM + "_results.json"
LEDGER = ER + "search_ledger.jsonl"

TARGET = {"comp_L": {"ic": 0.02054, "sharpe": 0.5488},
          "Mom20": {"ic": -0.02974, "sharpe": 0.8586}}
TOL_IC, TOL_SH = 0.0005, 0.01


def build():
    dfp, SIG, PX, CL, R, F = A.load_all()
    R2 = lambda x: x.reindex(index=SIG.index, columns=SIG.columns)
    ok = R2(M.eligibility(dfp))
    FWD = A.fwd1(R, SIG)
    bar_l, _, _ = (R2(x) for x in M.components(dfp, smooth=A.SMOOTH))
    compL = A._rank_xs(bar_l, ok)
    close = R2(M.close_price(dfp))
    mom_raw = close / close.shift(20) - 1.0
    mom = {"masked_ok": A._rank_xs(mom_raw, ok),
           "unmasked":  A._rank_xs(mom_raw, mom_raw.notna())}
    return dict(ok=ok, FWD=FWD, R=R, F=F, compL=compL, mom=mom, mom_raw=mom_raw)


def metrics(sig, D, drift=True):
    bt = A.backtest(sig, D["R"], D["F"], drift=drift)
    ic = A.ic_series(sig, D["FWD"])
    return {**A.perf(bt["net"]), **A.ic_stats(ic)}, bt


def cmd_lock():
    D = build()
    out = {"session": SIM, "prereg_sha256": A.sha256_file(PREREG),
           "time": datetime.datetime.now().isoformat(timespec="seconds")}
    cl, _ = metrics(D["compL"], D)
    out["comp_L"] = {"ic": cl["rank_ic"], "sharpe": cl["sharpe"],
                     "ok": abs(cl["rank_ic"] - TARGET["comp_L"]["ic"]) <= TOL_IC
                           and abs(cl["sharpe"] - TARGET["comp_L"]["sharpe"]) <= TOL_SH}
    out["Mom20"] = {}
    for tag, s in D["mom"].items():
        m, _ = metrics(s, D)
        out["Mom20"][tag] = {"ic": m["rank_ic"], "sharpe": m["sharpe"],
                             "ok": abs(m["rank_ic"] - TARGET["Mom20"]["ic"]) <= TOL_IC
                                   and abs(m["sharpe"] - TARGET["Mom20"]["sharpe"]) <= TOL_SH}
    good = [t for t, v in out["Mom20"].items() if v["ok"]]
    out["mom20_variant"] = good[0] if len(good) == 1 else None
    out["PASS"] = bool(out["comp_L"]["ok"] and len(good) == 1)
    A.dump(LOCK, out)
    # 只印複製目標本身（上輪已公開的基準），不產生任何新結果
    print(f"comp_L  IC {out['comp_L']['ic']:+.5f} (目標 +0.02054)  "
          f"Sharpe {out['comp_L']['sharpe']:+.4f} (目標 +0.5488)  {'✓' if out['comp_L']['ok'] else '✗'}")
    for t, v in out["Mom20"].items():
        print(f"Mom20[{t:9s}] IC {v['ic']:+.5f} (目標 −0.02974)  "
              f"Sharpe {v['sharpe']:+.4f} (目標 +0.8586)  {'✓' if v['ok'] else '✗'}")
    print("複製鎖:", "PASS，Mom20 採用 " + str(out["mom20_variant"]) if out["PASS"] else "FAIL —— 本輪中止")


def ledger(rows):
    with open(LEDGER, "a") as f:
        for r in rows:
            f.write(json.dumps({"date": "2026-09-23", "session": SIM,
                                "module": "scripts/compL_mom20_20260923.py",
                                "type": "cross-sectional", "asset": "72-coin(Binance UM tick)",
                                "tf": "1d", **r}, ensure_ascii=False) + "\n")


def cmd_run():
    lock = json.load(open(LOCK))
    if not lock.get("PASS"):
        raise SystemExit("複製鎖未通過，不得執行")
    D = build()
    mom = D["mom"][lock["mom20_variant"]]
    res = {"session": SIM, "prereg_sha256": A.sha256_file(PREREG),
           "lock": LOCK, "mom20_variant": lock["mom20_variant"]}

    resid = A._rank_xs(A.xs_resid(D["compL"], [mom]), D["ok"])
    raw = {}
    for drift in (True, False):
        k = "drift" if drift else "nodrift"
        r0, bt0 = metrics(D["compL"], D, drift)
        r1, bt1 = metrics(resid, D, drift)
        raw[k] = bt0
        rho = r1["sharpe"] / r0["sharpe"] if r0["sharpe"] else float("nan")
        res["T2_" + k] = {"raw_sharpe": r0["sharpe"], "resid_sharpe": r1["sharpe"],
                          "resid_nw_t": r1["nw_t"], "rho": rho}
        if drift:
            res["T1"] = {"raw_ic": r0["rank_ic"], "raw_ic_nw_t": r0["ic_nw_t"],
                         "resid_ic": r1["rank_ic"], "resid_ic_nw_t": r1["ic_nw_t"],
                         "artifact_flag": bool(r1["rank_ic"] > r0["rank_ic"])}

    rd, rn = res["T2_drift"]["rho"], res["T2_nodrift"]["rho"]
    if rd < 0.5 and rn < 0.5:
        verdict = "CLOSE"
    elif rd >= 0.5 and rn >= 0.5:
        verdict = "SURVIVE"
    else:
        verdict = "INCONCLUSIVE"
    res["verdict"] = verdict

    # T3 disclosure
    rev = A._rank_xs(A.xs_resid(mom, [D["compL"]]), D["ok"])
    r3, _ = metrics(rev, D, True)
    res["T3_mom20_given_compL"] = {"ic": r3["rank_ic"], "ic_nw_t": r3["ic_nw_t"],
                                   "sharpe": r3["sharpe"], "nw_t": r3["nw_t"]}
    _, btm = metrics(mom, D, True)
    y = raw["drift"]["net"]; x = btm["net"].reindex(y.index)
    m = y.notna() & x.notna()
    beta = float(np.cov(y[m], x[m], ddof=1)[0, 1] / np.var(x[m], ddof=1))
    e = y[m] - beta * x[m]
    res["T3_spanning"] = {"beta": beta, "alpha_ann": float(e.mean() * 365),
                          "alpha_nw_t": A.nw_t(e),
                          "note": "截距 t 以殘差序列 NW t 近似，未計 beta 估計誤差；disclosure only"}
    A.dump(RES, res)

    ledger([
        {"factor": "[P0] comp_L | Mom20 殘差化 排序層(T1,不適格 disclosure)",
         "params": "v2.4§4: Mom20 IC 較強且反號 → 不適格",
         "rank_ic": res["T1"]["resid_ic"], "t_nonoverlap": res["T1"]["resid_ic_nw_t"],
         "verdict": "artifact" if res["T1"]["artifact_flag"] else "disclosure"},
        {"factor": "[P0] comp_L | Mom20 殘差化 美元層 drift=True(T2)", "params": "裁決檢定",
         "net_sharpe": res["T2_drift"]["resid_sharpe"], "net_nw_t": res["T2_drift"]["resid_nw_t"],
         "verdict": f"rho={rd:.3f}"},
        {"factor": "[P0] comp_L | Mom20 殘差化 美元層 drift=False(T2)", "params": "裁決檢定(第二口徑)",
         "net_sharpe": res["T2_nodrift"]["resid_sharpe"], "net_nw_t": res["T2_nodrift"]["resid_nw_t"],
         "verdict": f"rho={rn:.3f}"},
        {"factor": "[P0] Mom20 | comp_L 殘差化(T3)", "params": "disclosure-only",
         "rank_ic": r3["rank_ic"], "t_nonoverlap": r3["ic_nw_t"],
         "net_sharpe": r3["sharpe"], "net_nw_t": r3["nw_t"], "verdict": "揭露"},
        {"factor": "[P0] comp_L 對 Mom20 報酬層 spanning 截距(T3)", "params": "disclosure-only",
         "net_sharpe": None, "net_nw_t": res["T3_spanning"]["alpha_nw_t"], "verdict": "揭露"},
    ])
    print(json.dumps(A.sanitize(res), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"lock": cmd_lock, "run": cmd_run}[sys.argv[1]]()
