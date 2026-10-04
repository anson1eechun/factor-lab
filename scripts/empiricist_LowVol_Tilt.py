#!/usr/bin/env python3
"""Empiricist 真實評估 — FSIM_LowVol_Tilt(long-only 低波動傾斜 vs 等權基準)。
構造 A:逆波動加權(long-only);構造 B:低波動 quintile 等權(long-only)。
核心:對等權基準的超額 Sharpe / IR(Sharpe 對槓桿不變,故超額 Sharpe = tilt − EW)。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/empiricist_LowVol_Tilt.py [freq] [cost_bps]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats
from scripts.crosssec_eval import to_weekly, MIN_COINS

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"


def perf(r, ann):
    r = pd.Series(r).dropna()
    if len(r) < 2 or not r.std():
        return {}
    eq = (1 + r).cumprod()
    return {"sharpe": round(float(r.mean()/r.std(ddof=1)*ann), 3),
            "ann_return": round(float(r.mean()*ann**2), 4),
            "ann_vol": round(float(r.std(ddof=1)*ann), 4),
            "max_drawdown": round(float((eq/eq.cummax()-1).min()), 4),
            "t": round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))), 3)}


def run(freq, cost_bps):
    uni = pd.read_pickle(UNI)
    if freq == "1w":
        uni = {co: to_weekly(df) for co, df in uni.items()}
    ann = np.sqrt({"1d": 365, "1w": 52}[freq])
    RV, FWD, DV = {}, {}, {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms")
        c = df["close"].astype(float)
        rv = np.log(c).diff().rolling(60, min_periods=30).std(ddof=1).shift(1)
        RV[co] = pd.Series(rv.values, index=idx)
        FWD[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
        DV[co] = pd.Series((c*df["volume"].astype(float)).rolling(30).mean().shift(1).values, index=idx)
    RV = pd.DataFrame(RV).sort_index(); F = pd.DataFrame(FWD).reindex(RV.index); DV = pd.DataFrame(DV).reindex(RV.index)

    rA, rB, rEW, wA_prev, wB_prev, wE_prev = [], [], [], None, None, None
    qstats = {q: [] for q in range(5)}
    for dt in RV.index:
        v = RV.loc[dt]; y = F.loc[dt]; m = v.notna() & y.notna() & (v > 0)
        if m.sum() < MIN_COINS:
            for arr, wp in ((rA, wA_prev), (rB, wB_prev), (rEW, wE_prev)):
                arr.append(float((wp*F.loc[dt].fillna(0)).sum()) if wp is not None else np.nan)
            continue
        vv = v[m]; coins = vv.index
        # A: 逆波動權重(long-only)
        iv = 1.0/vv; wA = pd.Series(0.0, index=RV.columns); wA[coins] = (iv/iv.sum()).values
        # B: 低波動 quintile(底 20% RV)等權 long-only
        rank = vv.rank(); thr = rank.quantile(0.2)
        low = coins[rank <= thr]; wB = pd.Series(0.0, index=RV.columns)
        if len(low): wB[low] = 1.0/len(low)
        # EW 基準
        wE = pd.Series(0.0, index=RV.columns); wE[coins] = 1.0/len(coins)
        # quintile 報酬(Mono;0=高RV..4=低RV)
        q = pd.qcut(vv.rank(method="first"), 5, labels=False, duplicates="drop")
        for qi in range(int(np.nanmax(q.values))+1):
            qstats.setdefault(qi, []).append(float(y[m][q == qi].mean()))
        for arr, w, wp in ((rA, wA, wA_prev), (rB, wB, wB_prev), (rEW, wE, wE_prev)):
            turn = float((w - (wp if wp is not None else 0)).abs().sum())
            arr.append(float((w*F.loc[dt].fillna(0)).sum()) - turn*cost_bps/10000.0)
        wA_prev, wB_prev, wE_prev = wA, wB, wE
    rA, rB, rEW = pd.Series(rA), pd.Series(rB), pd.Series(rEW)

    def excess(rp):
        d = (rp - rEW).dropna()
        ir = round(float(d.mean()/d.std(ddof=1)*ann), 3) if len(d) > 1 and d.std() else None
        return {"excess_ann": round(float(d.mean()*ann**2), 4), "IR": ir,
                "excess_sharpe": round((perf(rp, ann).get("sharpe", 0) - perf(rEW, ann).get("sharpe", 0)), 3)}

    qm = [np.mean(v) for q, v in sorted(qstats.items()) if v]
    out = {"freq": freq, "cost_bps": cost_bps, "n_days": int(len(rA)),
           "EW_benchmark": perf(rEW, ann),
           "A_invvol": {**perf(rA, ann), **excess(rA)},
           "B_lowvol_quintile": {**perf(rB, ann), **excess(rB)},
           "mono_RV_quintile(低RV=高q)": round(float(stats.spearmanr(range(len(qm)), qm).correlation), 3) if len(qm) >= 3 else None,
           "quintile_fwd(0=高RV..4=低RV)": [round(x, 5) for x in qm]}
    # regime 子期間(超額 Sharpe)
    h = len(rEW)//2
    out["regime_excess_sharpe_A"] = {
        "first": round(perf(rA[:h], ann).get("sharpe", 0) - perf(rEW[:h], ann).get("sharpe", 0), 3),
        "second": round(perf(rA[h:], ann).get("sharpe", 0) - perf(rEW[h:], ann).get("sharpe", 0), 3)}
    # size 檢查:低波動分數(-RV)vs log 成交額 橫截面相關
    cs = []
    for dt in RV.index:
        x = -RV.loc[dt]; z = np.log(DV.loc[dt]); mm = x.notna() & z.notna()
        if mm.sum() >= MIN_COINS and x[mm].nunique() > 1:
            cs.append(stats.spearmanr(x[mm], z[mm]).correlation)
    out["corr_lowvol_vs_size"] = round(float(pd.Series(cs).dropna().mean()), 3)
    return out


def main():
    freq = sys.argv[1] if len(sys.argv) > 1 else "1d"
    cost = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    print(json.dumps(run(freq, cost), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
