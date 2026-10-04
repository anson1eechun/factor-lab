#!/usr/bin/env python3
"""Empiricist 真實評估 — FSIM_TCA(橫截面，需注入等權市場報酬)。
沿用 crosssec_eval.evaluate 的指標數學；額外加 非重疊IC + 子期間regime。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/empiricist_TCA.py [cost_bps] [freq] [window]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats
from scripts.crosssec_eval import evaluate, to_weekly, MIN_COINS
from core.signals.FSIM_TCA import tca_series

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"


def build_panels(freq, window):
    uni = pd.read_pickle(UNI)
    if freq == "1w":
        uni = {co: to_weekly(df) for co, df in uni.items()}
    closes = {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms")
        closes[co] = pd.Series(df["close"].astype(float).values, index=idx)
    px = pd.DataFrame(closes).sort_index()
    rets = px.pct_change()
    mkt = rets.mean(axis=1)                      # 等權市場報酬（每日對有效幣均值）
    sigs, fwds = {}, {}
    for co in px.columns:
        sigs[co] = tca_series(px[co], mkt, window=window)
        fwds[co] = px[co].shift(-1) / px[co] - 1
    S = pd.DataFrame(sigs).sort_index()
    F = pd.DataFrame(fwds).reindex(S.index)
    return S, F


def nonoverlap_ic(S, F, step):
    """非重疊取樣的 Rank IC（每 step 天取一個橫截面）+ t。"""
    days = list(S.index)[::step]
    ics = []
    for dt in days:
        x, y = S.loc[dt], F.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    if len(ics) < 2 or not ics.std():
        return None
    return {"ic_mean": round(float(ics.mean()), 4),
            "ic_ir": round(float(ics.mean()/ics.std(ddof=1)), 4),
            "ic_t": round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3),
            "n": int(len(ics))}


def regime_split(S, F, ann):
    n = len(S.index); h = n // 2
    out = {}
    for name, sl in [("first_half", slice(0, h)), ("second_half", slice(h, n))]:
        idx = S.index[sl]
        r = evaluate(S.loc[idx], F.loc[idx], 10.0, ann, 1)
        out[name] = {k: r.get(k) for k in ("rank_ic_mean", "ic_ir", "ls_sharpe", "mono")}
    return out


def main():
    cost = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    freq = sys.argv[2] if len(sys.argv) > 2 else "1d"
    window = int(sys.argv[3]) if len(sys.argv) > 3 else 90
    ann = np.sqrt({"1d": 365, "1w": 52}[freq])
    S, F = build_panels(freq, window)
    res = {"factor": "FSIM_TCA", "freq": freq, "window": window, "cost_bps": cost,
           "n_coins": int(S.shape[1]), "n_days": int(S.shape[0])}
    res["base"] = evaluate(S, F, cost, ann, 1)
    res["nonoverlap_ic_step5"] = nonoverlap_ic(S, F, 5)
    res["regime"] = regime_split(S, F, ann)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
