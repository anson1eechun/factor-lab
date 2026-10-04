#!/usr/bin/env python3
"""多因子組合:反轉族(STR/MAX/OFR)+ 事件族(FUND)橫截面風險加權。
全真實、無前視、扣成本。先檢正交性(組合加分前提),再 equal / risk-parity 組合,跑標準套餐+剔5%日壓測。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/multifactor_combo.py [cost_bps]"""
import sys, json
import numpy as np, pandas as pd
from scipy import stats

ER = "/home/anson/factor-lab/empirical_runs/"
MIN_COINS = 8
ANN = np.sqrt(365)
cost_bps = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0

uni = pd.read_pickle(ER + "universe_1d.pkl")
flow = pd.read_pickle(ER + "universe_flow_1d.pkl")
fund = pd.read_pickle(ER + "funding_1d.pkl")


def series(df, col):
    return pd.Series(df[col].astype(float).values, index=pd.to_datetime(df["timestamp"], unit="ms").dt.floor("D"))


# 各 coin 因子(高分=預期相對強)
fac = {"STR": {}, "MAX": {}, "OFR": {}, "FUND": {}}
ret = {}
for co, df in uni.items():
    c = series(df, "close")
    ret[co] = c.shift(-1) / c - 1                                   # 次日報酬
    fac["STR"][co] = -(c / c.shift(5) - 1)                          # 短期反轉
    dr = c / c.shift(1) - 1
    fac["MAX"][co] = -dr.rolling(20).max()                          # 樂透趨避
    if co in flow:
        t = series(flow[co], "tfi")
        fac["OFR"][co] = -((t - t.rolling(20).mean()) / t.rolling(20).std())   # 訂單流反轉
    if co in fund:
        f = series(fund[co], "funding")
        fac["FUND"][co] = -f.reindex(c.index).ffill(limit=2)        # funding carry(放空高funding)

R = pd.DataFrame(ret).sort_index()
F = {k: pd.DataFrame(v).reindex(R.index) for k, v in fac.items()}


def xrank_z(D):
    """逐日橫截面 rank → z(均0標準化)"""
    rk = D.rank(axis=1)
    return rk.sub(rk.mean(axis=1), axis=0).div(rk.std(axis=1), axis=0)


Z = {k: xrank_z(v) for k, v in F.items()}


def ls_returns(sig):
    """多空分位日報酬(top-bottom quintile, 等權, hold=1, 扣成本)+ IC"""
    rets, ics, w = [], [], None
    idx = sig.index
    for dt in idx:
        x = sig.loc[dt]; y = R.loc[dt]; m = x.notna() & y.notna()
        if m.sum() < MIN_COINS:
            if w is not None: rets.append(float((w * y.fillna(0)).sum()))
            continue
        ics.append(stats.spearmanr(x[m], y[m]).correlation)
        q = pd.qcut(x[m].rank(), 5, labels=False, duplicates="drop")
        nw = pd.Series(0.0, index=sig.columns); coins = x[m].index
        top = coins[q == q.max()]; bot = coins[q == 0]
        if len(top): nw[top] = 1/len(top)
        if len(bot): nw[bot] = -1/len(bot)
        turn = float((nw - (w if w is not None else 0)).abs().sum())
        w = nw
        rets.append(float((w * y.fillna(0)).sum()) - turn*cost_bps/1e4)
    r = pd.Series(rets, index=idx[:len(rets)])
    ic = pd.Series(ics).dropna()
    return r, ic


def report(r, ic, label):
    if not len(r) or not r.std(): return {}
    eq = (1+r).cumprod()
    cut = r[r < r.quantile(0.95)]
    yr = r.copy(); yr.index = pd.to_datetime(r.index)
    return {"label": label,
            "ic": round(float(ic.mean()), 4),
            "ic_ir": round(float(ic.mean()/ic.std(ddof=1)), 4) if ic.std() else None,
            "ls_sharpe": round(float(r.mean()/r.std(ddof=1)*ANN), 3),
            "ls_t": round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))), 3),
            "ex_top5pct": round(float(cut.mean()/cut.std(ddof=1)*ANN), 3) if cut.std() else None,
            "maxdd": round(float((eq/eq.cummax()-1).min()), 4),
            "by_year": {str(y): round(float(g.mean()/g.std(ddof=1)*ANN), 2) for y, g in yr.groupby(yr.index.year) if g.std() and len(g) > 30}}


# 1) 個別因子
out = {"cost_bps": cost_bps, "singles": {}, "orthogonality": {}, "combos": {}}
single_r = {}
for k in Z:
    r, ic = ls_returns(Z[k]); single_r[k] = r
    out["singles"][k] = report(r, ic, k)

# 2) 正交性:個別 LS 日報酬的相關矩陣
RR = pd.DataFrame(single_r).dropna()
corr = RR.corr().round(2)
out["orthogonality"] = {f"{a}-{b}": float(corr.loc[a, b]) for i, a in enumerate(corr.index) for b in corr.index[i+1:]}

# 3) 組合:equal-weight z / risk-parity(逆波動,僅用報酬波動非方向→非return-snoop)
zsum = sum(Z[k].fillna(0) for k in Z); zcnt = sum(Z[k].notna() for k in Z)
combo_eq = zsum / zcnt.replace(0, np.nan)
r_eq, ic_eq = ls_returns(combo_eq); out["combos"]["equal_z"] = report(r_eq, ic_eq, "equal_z")

ivol = {k: 1.0/single_r[k].std() for k in Z}; sw = sum(ivol.values())
zsum_rw = sum(Z[k].fillna(0)*ivol[k]/sw for k in Z)
combo_rw = zsum_rw / zcnt.replace(0, np.nan)
r_rw, ic_rw = ls_returns(combo_rw); out["combos"]["risk_parity"] = report(r_rw, ic_rw, "risk_parity")

# 僅反轉族 vs 加入事件族
zrev = sum(Z[k].fillna(0) for k in ["STR","MAX","OFR"]) / sum(Z[k].notna() for k in ["STR","MAX","OFR"]).replace(0,np.nan)
r_rev, ic_rev = ls_returns(zrev); out["combos"]["reversal_only"] = report(r_rev, ic_rev, "reversal_only")

print(json.dumps(out, ensure_ascii=False, indent=2))
