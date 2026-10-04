#!/usr/bin/env python3
"""Empiricist 真實評估 — FSIM_CalmStreak(橫截面,稀疏訊號容錯版)。
穩健處理同分/常數日;含 非重疊IC + 子期間regime + 對照組(純low-vol、size相關)。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/empiricist_CalmStreak.py [freq]
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats
from scripts.crosssec_eval import to_weekly, MIN_COINS

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"


def robust_eval(S, F, cost_bps, ann):
    out = {}
    ics = []
    for dt in S.index:
        x, y = S.loc[dt], F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS and x[m].nunique() > 1 and y[m].nunique() > 1:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    out["rank_ic_mean"] = round(float(ics.mean()), 4) if len(ics) else None
    out["ic_ir"] = round(float(ics.mean()/ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None
    out["ic_t"] = round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3) if len(ics) > 1 and ics.std() else None
    out["ic_n_days"] = int(len(ics))
    # LS quintile,容錯同分:用 rank + qcut(duplicates=drop);組數<2 則持有不換倉
    rets, w = [], None
    qstats = {q: [] for q in range(5)}
    for dt in S.index:
        x, y = S.loc[dt], F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() < MIN_COINS or x[m].nunique() < 2:
            if w is not None:
                rets.append(float((w*F.loc[dt].fillna(0)).sum()))
            continue
        xr = x[m].rank(method="first")
        try:
            q = pd.qcut(xr, 5, labels=False, duplicates="drop")
        except Exception:
            if w is not None: rets.append(float((w*F.loc[dt].fillna(0)).sum()))
            continue
        nq = int(np.nanmax(q.values)) if q.notna().any() else 0
        if nq < 1:
            if w is not None: rets.append(float((w*F.loc[dt].fillna(0)).sum()))
            continue
        for qi in range(nq+1):
            qstats.setdefault(qi, []).append(float(y[m][q == qi].mean()))
        neww = pd.Series(0.0, index=S.columns)
        top = x[m].index[q == nq]; bot = x[m].index[q == 0]
        if len(top): neww[top] = 1.0/len(top)
        if len(bot): neww[bot] = -1.0/len(bot)
        turn = float((neww - (w if w is not None else 0)).abs().sum())
        w = neww
        rets.append(float((w*F.loc[dt].fillna(0)).sum()) - turn*cost_bps/10000.0)
    r = pd.Series(rets)
    if len(r) and r.std():
        eq = (1+r).cumprod()
        out["ls_sharpe"] = round(float(r.mean()/r.std(ddof=1)*ann), 3)
        out["ls_max_drawdown"] = round(float((eq/eq.cummax()-1).min()), 4)
        out["ls_t"] = round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))), 3)
    qm = [np.mean(v) for q, v in sorted(qstats.items()) if v]
    out["mono"] = round(float(stats.spearmanr(range(len(qm)), qm).correlation), 3) if len(qm) >= 3 else None
    out["quintile_fwd"] = [round(x, 5) for x in qm]
    return out


def signals(uni, fn):
    S = {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms")
        S[co] = pd.Series(np.asarray(fn(df), dtype="float64").ravel(), index=idx)
    return pd.DataFrame(S).sort_index()


def neg_rv_long(df, w=60):
    """對照組:純 low-vol 因子 = -長期RV(shift1)。"""
    c = df["close"].astype(float).reset_index(drop=True)
    rv = np.log(c).diff().rolling(w).std()
    return (-rv).shift(1).reindex(range(len(df))).reset_index(drop=True)


def log_dvol(df, w=30):
    c = df["close"].astype(float).reset_index(drop=True); v = df["volume"].astype(float).reset_index(drop=True)
    return np.log((c*v).rolling(w).mean()).shift(1).reindex(range(len(df))).reset_index(drop=True)


def xs_corr(A, B):
    cs = []
    for dt in A.index:
        x = A.loc[dt]; y = B.loc[dt] if dt in B.index else None
        if y is None: continue
        m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS and x[m].nunique() > 1 and y[m].nunique() > 1:
            cs.append(stats.spearmanr(x[m], y[m]).correlation)
    cs = pd.Series(cs).dropna()
    return round(float(cs.mean()), 3) if len(cs) else None


def main():
    freq = sys.argv[1] if len(sys.argv) > 1 else "1d"
    uni = pd.read_pickle(UNI)
    if freq == "1w":
        uni = {co: to_weekly(df) for co, df in uni.items()}
    ann = np.sqrt({"1d": 365, "1w": 52}[freq])
    fn = importlib.import_module("core.signals.FSIM_CalmStreak").factor
    S = signals(uni, fn)
    F = pd.DataFrame({co: (pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["timestamp"], unit="ms")).pipe(lambda c: c.shift(-1)/c-1)) for co, df in uni.items()}).reindex(S.index)
    res = {"factor": "FSIM_CalmStreak", "freq": freq, "n_coins": int(S.shape[1]), "n_days": int(S.shape[0])}
    res["base"] = robust_eval(S, F, 10.0, ann)
    # 稀疏度:每日有正值(在calm)的幣比例
    pos_frac = (S > 0).sum(axis=1) / S.notna().sum(axis=1).replace(0, np.nan)
    res["calm_frac_mean"] = round(float(pos_frac.mean()), 3)
    # 非重疊 + regime
    days = list(S.index)[::5]; ics = []
    for dt in days:
        x, y = S.loc[dt], F.loc[dt]; m = x.notna() & y.notna()
        if m.sum() >= MIN_COINS and x[m].nunique() > 1:
            ics.append(stats.spearmanr(x[m], y[m]).correlation)
    ics = pd.Series(ics).dropna()
    res["nonoverlap_ic"] = {"ic_ir": round(float(ics.mean()/ics.std(ddof=1)), 4), "ic_t": round(float(ics.mean()/(ics.std(ddof=1)/np.sqrt(len(ics)))), 3), "n": int(len(ics))} if len(ics) > 1 and ics.std() else None
    n = len(S.index); h = n//2
    res["regime"] = {nm: {k: robust_eval(S.loc[S.index[sl]], F.loc[S.index[sl]], 10.0, ann).get(k) for k in ("rank_ic_mean", "ic_ir", "ls_sharpe", "mono")} for nm, sl in [("first", slice(0, h)), ("second", slice(h, n))]}
    # 對照組:純 low-vol + size 相關
    LV = signals(uni, neg_rv_long); DV = signals(uni, log_dvol)
    res["control_neg_rv_long"] = robust_eval(LV, F, 10.0, ann)
    res["corr_calm_vs_negRVlong"] = xs_corr(S, LV)
    res["corr_calm_vs_logDvol"] = xs_corr(S, DV)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
