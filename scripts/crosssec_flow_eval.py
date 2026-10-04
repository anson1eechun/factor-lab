#!/usr/bin/env python3
"""訂單流橫截面評估 harness。讀 universe_flow_1d.pkl(close/volume/taker_buy/tfi)。
與 crosssec_eval 同輸出(RankIC/IC-IR/t/LS-Sharpe/MaxDD/Mono),外加剔最高5%日壓測。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/crosssec_flow_eval.py core.signals.<MOD> [func] [cost_bps] [hold]"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats

FLOW = "/home/anson/factor-lab/empirical_runs/universe_flow_1d.pkl"
MIN_COINS = 8
ANN = np.sqrt(365)


def evaluate(S, F, cost_bps, hold=1):
    out = {}
    ics = []
    for dt in S.index:
        x = S.loc[dt]; y = F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    out["rank_ic_mean"] = round(float(ics.mean()), 4)
    out["ic_ir"] = round(float(ics.mean()/ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None
    out["ic_t"] = round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3) if len(ics) > 1 and ics.std() else None
    out["ic_n_days"] = int(len(ics))
    rets, rdates, w, since = [], [], None, 10**9
    qstats = {}
    for dt in S.index:
        x = S.loc[dt]; y = F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() < MIN_COINS:
            if w is not None:
                rets.append(float((w*F.loc[dt].fillna(0)).sum())); rdates.append(dt)
            continue
        xr = x[m].rank(); coins = xr.index
        q = pd.qcut(xr, 5, labels=False, duplicates="drop")
        for qi in range(int(q.max())+1):
            qstats.setdefault(qi, []).append(float(y[m][q == qi].mean()))
        if since >= hold:
            neww = pd.Series(0.0, index=S.columns)
            top = coins[q == q.max()]; bot = coins[q == 0]
            if len(top): neww[top] = 1.0/len(top)
            if len(bot): neww[bot] = -1.0/len(bot)
            turn = float((neww - (w if w is not None else 0)).abs().sum())
            w = neww; since = 1
            rets.append(float((w*F.loc[dt].fillna(0)).sum()) - turn*cost_bps/10000.0); rdates.append(dt)
        else:
            rets.append(float((w*F.loc[dt].fillna(0)).sum())); rdates.append(dt); since += 1
    r = pd.Series(rets)
    if len(r) and r.std():
        eq = (1+r).cumprod()
        out["ls_sharpe"] = round(float(r.mean()/r.std(ddof=1)*ANN), 3)
        out["ls_max_drawdown"] = round(float((eq/eq.cummax()-1).min()), 4)
        out["ls_t"] = round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))), 3)
        out["ls_ann_return"] = round(float(r.mean()*(ANN**2)), 4)
        # 壓測:剔除報酬最高 5% 日(肥尾鑑別器)
        cut = r[r < r.quantile(0.95)]
        out["ls_sharpe_ex_top5pct"] = round(float(cut.mean()/cut.std(ddof=1)*ANN), 3) if cut.std() else None
        # 年度 regime
        yr = r.copy(); yr.index = pd.to_datetime(pd.Index(rdates))
        out["ls_sharpe_by_year"] = {str(y): round(float(g.mean()/g.std(ddof=1)*ANN), 2)
                                    for y, g in yr.groupby(yr.index.year) if g.std() and len(g) > 30}
    qm = [np.mean(v) for q, v in sorted(qstats.items()) if v]
    out["mono"] = round(float(stats.spearmanr(range(len(qm)), qm).correlation), 3) if len(qm) >= 3 else None
    out["quintile_fwd"] = [round(x, 5) for x in qm]
    out["n_coins"] = int(S.shape[1]); out["n_days"] = int(S.shape[0])
    return out


def main():
    module = sys.argv[1]; func = sys.argv[2] if len(sys.argv) > 2 else "factor"
    cost_bps = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    hold = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    fn = getattr(importlib.import_module(module), func)
    flow = pd.read_pickle(FLOW)
    sigs, fwds = {}, {}
    for co, df in flow.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms"); c = df["close"].astype(float)
        sigs[co] = pd.Series(np.asarray(fn(df), dtype="float64").ravel(), index=idx)
        fwds[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
    S = pd.DataFrame(sigs).sort_index(); F = pd.DataFrame(fwds).reindex(S.index)
    res = {"module": module, "func": func, "cost_bps": cost_bps, "hold": hold, **evaluate(S, F, cost_bps, hold)}
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
