#!/usr/bin/env python3
"""Empiricist REWORK — FSIM_TCA 救援:市值加權市場(成交額 proxy)+ size 中性化。
- market_ret = dollar-volume-weighted(權重=滯後30日均成交額)
- size 中性化 = 每日橫截面把 TCA 對 log(滾動成交額)殘差化
沿用 crosssec_eval.evaluate 數學。全真實。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/empiricist_TCA_rescue.py [freq] [neutralize 0/1]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats
from scripts.crosssec_eval import evaluate, to_weekly, MIN_COINS
from core.signals.FSIM_TCA import tca_series

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"


def panels(freq):
    uni = pd.read_pickle(UNI)
    if freq == "1w":
        uni = {co: to_weekly(df) for co, df in uni.items()}
    cl, dv = {}, {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms")
        c = df["close"].astype(float).values
        v = (df["close"].astype(float) * df["volume"].astype(float)).values
        cl[co] = pd.Series(c, index=idx); dv[co] = pd.Series(v, index=idx)
    px = pd.DataFrame(cl).sort_index(); dvp = pd.DataFrame(dv).sort_index()
    return px, dvp


def cap_weighted_market(px, dvp):
    rets = px.pct_change()
    w = dvp.rolling(30, min_periods=10).mean().shift(1)     # 滯後權重，防前視
    w = w.where(rets.notna())
    wsum = w.sum(axis=1)
    mkt = (w.mul(rets)).sum(axis=1) / wsum.replace(0, np.nan)
    return mkt


def size_neutralize(S, dvp):
    """每日橫截面把 TCA 對 log(滾動30日成交額)殘差化。"""
    z = np.log(dvp.rolling(30, min_periods=10).mean()).reindex(S.index)
    R = pd.DataFrame(index=S.index, columns=S.columns, dtype="float64")
    for dt in S.index:
        x = S.loc[dt]; zz = z.loc[dt] if dt in z.index else pd.Series(index=S.columns)
        m = x.notna() & zz.notna()
        if m.sum() < MIN_COINS:
            continue
        b, a, *_ = stats.linregress(zz[m].values, x[m].values)
        R.loc[dt, m[m].index] = x[m].values - (a + b * zz[m].values)
    return R


def nonoverlap_ic(S, F, step):
    ics = []
    for dt in list(S.index)[::step]:
        x, y = S.loc[dt], F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    if len(ics) < 2 or not ics.std():
        return None
    return {"ic_ir": round(float(ics.mean()/ics.std(ddof=1)), 4),
            "ic_t": round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3), "n": int(len(ics))}


def regime(S, F, ann):
    n = len(S.index); h = n // 2; out = {}
    for nm, sl in [("first", slice(0, h)), ("second", slice(h, n))]:
        idx = S.index[sl]; r = evaluate(S.loc[idx], F.loc[idx], 10.0, ann, 1)
        out[nm] = {k: r.get(k) for k in ("rank_ic_mean", "ic_ir", "ls_sharpe", "mono")}
    return out


def main():
    freq = sys.argv[1] if len(sys.argv) > 1 else "1d"
    neutral = bool(int(sys.argv[2])) if len(sys.argv) > 2 else True
    ann = np.sqrt({"1d": 365, "1w": 52}[freq])
    px, dvp = panels(freq)
    mkt = cap_weighted_market(px, dvp)
    S = pd.DataFrame({c: tca_series(px[c], mkt, window=90) for c in px.columns}).sort_index()
    tag = "capw_raw"
    if neutral:
        S = size_neutralize(S, dvp); tag = "capw_sizeNeutral"
    F = pd.DataFrame({c: px[c].shift(-1)/px[c]-1 for c in px.columns}).reindex(S.index)
    res = {"factor": "FSIM_TCA", "variant": tag, "freq": freq,
           "base": evaluate(S, F, 10.0, ann, 1),
           "nonoverlap_step5": nonoverlap_ic(S, F, 5),
           "regime": regime(S, F, ann)}
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
