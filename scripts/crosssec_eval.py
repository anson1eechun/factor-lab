#!/usr/bin/env python3
"""
橫截面因子評估 harness(多幣)。全真實。
把 per-coin signal 函數套到 universe 每個幣 → 每日跨幣排序。
輸出:每日橫截面 Rank IC、IC-IR、t、多空分位組合 Sharpe/MaxDD/t、Mono、成本後淨值。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/crosssec_eval.py core.signals.<MODULE> [func] [cost_bps]
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"
MIN_COINS = 8          # 當日至少要這麼多幣才算 IC/組合
ANN = np.sqrt(365)
PPY = {"1d": 365, "1w": 52}


def to_weekly(df):
    d = df.copy(); d.index = pd.to_datetime(d["timestamp"], unit="ms")
    w = pd.DataFrame({"open": d["open"].resample("W").first(), "high": d["high"].resample("W").max(),
                      "low": d["low"].resample("W").min(), "close": d["close"].resample("W").last(),
                      "volume": d["volume"].resample("W").sum()}).dropna()
    w["timestamp"] = w.index.values.astype("datetime64[ms]").astype("int64")
    return w.reset_index(drop=True)


def evaluate(S, F, cost_bps, ann=ANN, hold=1):
    out = {}
    # 每日橫截面 Rank IC
    ics = []
    for dt in S.index:
        x = S.loc[dt]; y = F.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    out["rank_ic_mean"] = round(float(ics.mean()), 4)
    out["ic_ir"] = round(float(ics.mean()/ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None
    out["ic_t"] = round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3) if len(ics) > 1 and ics.std() else None
    out["ic_n_days"] = int(len(ics))
    # 多空分位組合:每 hold 天才 rebalance(中間持有,成本只在 rebalance 收)
    rets, w, since = [], None, 10**9
    qstats = {q: [] for q in range(5)}
    for dt in S.index:
        x = S.loc[dt]; y = F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() < MIN_COINS:
            if w is not None:
                rets.append(float((w*F.loc[dt].fillna(0)).sum()))   # 持有,無換手
            continue
        xr = x[m].rank(); coins = xr.index
        q = pd.qcut(xr, 5, labels=False, duplicates="drop")
        for qi in range(int(q.max())+1):
            qstats.setdefault(qi, []).append(float(y[m][q == qi].mean()))   # Mono 仍逐期
        if since >= hold:
            neww = pd.Series(0.0, index=S.columns)
            top = coins[q == q.max()]; bot = coins[q == 0]
            if len(top): neww[top] = 1.0/len(top)
            if len(bot): neww[bot] = -1.0/len(bot)
            turn = float((neww - (w if w is not None else 0)).abs().sum())
            w = neww; since = 1
            rets.append(float((w*F.loc[dt].fillna(0)).sum()) - turn*cost_bps/10000.0)
        else:
            rets.append(float((w*F.loc[dt].fillna(0)).sum())); since += 1
    r = pd.Series(rets)
    if len(r) and r.std():
        eq = (1+r).cumprod()
        out["ls_sharpe"] = round(float(r.mean()/r.std(ddof=1)*ann), 3)
        out["ls_max_drawdown"] = round(float((eq/eq.cummax()-1).min()), 4)
        out["ls_t"] = round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))), 3)
        out["ls_ann_return"] = round(float(r.mean()*(ann**2)), 4)
    # Mono:quintile 平均報酬 對 quintile 序
    qm = [np.mean(v) for q, v in sorted(qstats.items()) if v]
    out["mono"] = round(float(stats.spearmanr(range(len(qm)), qm).correlation), 3) if len(qm) >= 3 else None
    out["quintile_fwd"] = [round(x, 5) for x in qm]
    out["n_coins"] = int(S.shape[1]); out["n_days"] = int(S.shape[0])
    return out


def main():
    module = sys.argv[1]; func = sys.argv[2] if len(sys.argv) > 2 else "factor"
    cost_bps = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    freq = sys.argv[4] if len(sys.argv) > 4 else "1d"          # 1d | 1w(bar 頻率)
    hold = int(sys.argv[5]) if len(sys.argv) > 5 else 1        # 持有期(每 hold bar 才 rebalance,降換手)
    fn = getattr(importlib.import_module(module), func)
    uni = pd.read_pickle(UNI)
    if freq == "1w":
        uni = {co: to_weekly(df) for co, df in uni.items()}
    ann = np.sqrt(PPY.get(freq, 365))
    sigs, fwds = {}, {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms"); c = df["close"].astype(float)
        sigs[co] = pd.Series(np.asarray(fn(df), dtype="float64").ravel(), index=idx)
        fwds[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
    S = pd.DataFrame(sigs).sort_index(); F = pd.DataFrame(fwds).reindex(S.index)
    res = {"module": module, "freq": freq, "hold": hold, "universe": list(uni.keys()), **evaluate(S, F, cost_bps, ann, hold)}
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
