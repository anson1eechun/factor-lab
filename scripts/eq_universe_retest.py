#!/usr/bin/env python3
"""EQ-SIM-004:在 S&P1500 大/中/小型分層重測 value + Piotroski。
檢驗「瓶頸是 universe 不是維度」。PIT、月頻、行業中性(各子集內)。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_universe_retest.py [cost_bps=10]"""
import sys
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
cost = (float(sys.argv[1]) if len(sys.argv) > 1 else 10.0) / 1e4
ANN = np.sqrt(12)
facts = pd.read_parquet(EQ + "sec_facts.parquet")
px = pd.read_parquet(EQ + "prices_monthly.parquet")
uni = pd.read_csv(EQ + "universe.csv"); tier = uni.set_index("ticker")["tier"]
sec = facts.groupby("ticker")["sector"].first()
facts["filed"] = facts["filed"].astype("datetime64[ns]"); facts["end"] = facts["end"].astype("datetime64[ns]")
base = px[["date", "ticker", "close"]].copy(); base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
ANNF = facts["form"].astype(str).str.startswith(("10-K", "20-F"))

def asof(concept, annual=False):
    f = facts[(facts["concept"] == concept) & (ANNF if annual else True)][["ticker", "filed", "val"]].dropna().sort_values("filed")
    m = pd.merge_asof(base.sort_values("date"), f.rename(columns={"val": concept}), left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"] - m["filed"]).dt.days > 740, concept] = np.nan
    return m[concept].values

# ---- value 成分 ----
b = base.copy()
ni = asof("NetIncomeLoss", True); se = asof("StockholdersEquity"); shares = asof("CommonStockSharesOutstanding")
rev = None
for cc in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(cc, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
mc = shares * b["close"].values
b["ep"] = ni/mc; b["bp"] = se/mc; b["sp"] = rev/mc

# ---- Piotroski F(年度寬表)----
ann = facts[ANNF].dropna(subset=["end", "val"]).sort_values("filed").groupby(["ticker", "concept", "end"], as_index=False).first()
w = ann.pivot_table(index=["ticker", "end"], columns="concept", values="val", aggfunc="first").reset_index()
w = w.merge(ann.groupby(["ticker", "end"])["filed"].max().reset_index(), on=["ticker", "end"]).sort_values(["ticker", "end"]).reset_index(drop=True)
C = lambda n: w[n] if n in w else pd.Series(np.nan, index=w.index)
cfo = C("NetCashProvidedByUsedInOperatingActivities").fillna(C("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"))
ltd = C("LongTermDebt").fillna(C("LongTermDebtNoncurrent"))
rv = C("RevenueFromContractWithCustomerExcludingAssessedTax").fillna(C("Revenues")).fillna(C("SalesRevenueNet")).fillna(C("RevenueFromContractWithCustomerIncludingAssessedTax"))
g = w.groupby("ticker"); pv = lambda c: g[c].shift(1); gap = (w["end"] - g["end"].shift(1)).dt.days
A, NIc, AC, LC, GP, SH = C("Assets"), C("NetIncomeLoss"), C("AssetsCurrent"), C("LiabilitiesCurrent"), C("GrossProfit"), C("WeightedAverageNumberOfSharesOutstandingBasic")
roa = NIc/A
crit = {"f1": roa > 0, "f2": cfo > 0, "f3": roa > (g["NetIncomeLoss"].shift(1)/g["Assets"].shift(1)),
        "f4": cfo/A > roa, "f5": (ltd/A) < (pv("LongTermDebt").fillna(pv("LongTermDebtNoncurrent"))/pv("Assets")),
        "f6": (AC/LC) > (pv("AssetsCurrent")/pv("LiabilitiesCurrent")), "f7": SH <= pv("WeightedAverageNumberOfSharesOutstandingBasic")*1.01,
        "f8": (GP/rv) > (pv("GrossProfit")/pv("Revenues").fillna(pv("SalesRevenueNet"))), "f9": (rv/A) > (pv("Revenues").fillna(pv("SalesRevenueNet"))/pv("Assets"))}
Cf = pd.DataFrame({k: v.astype(float).values for k, v in crit.items()})
inp = {"f1": [roa], "f2": [cfo], "f3": [roa], "f4": [cfo, A], "f5": [ltd, A], "f6": [AC, LC], "f7": [SH], "f8": [GP, rv], "f9": [rv, A]}
for k, ins in inp.items():
    miss = np.zeros(len(w), bool)
    for x in ins: miss |= pd.isna(np.asarray(x, "float64"))
    Cf[k] = np.where(miss, np.nan, Cf[k].values)
nav = Cf.notna().sum(1); F = np.where((nav >= 7) & (gap.values > 250) & (gap.values < 450), Cf.sum(1, skipna=True)*9/nav, np.nan)
fp = w.assign(F=F)[["ticker", "filed", "F"]].dropna().sort_values("filed")
b["F"] = pd.merge_asof(base, fp, left_on="date", right_on="filed", by="ticker", direction="backward")["F"].values

b["sector"] = b["ticker"].map(sec); b["tier"] = b["ticker"].map(tier)
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1)/b["close"]-1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)

def znorm(df, col):
    gg = df.groupby(["date", "sector"])[col]
    return ((df[col]-gg.transform("median"))/gg.transform(lambda x: x.std())).clip(-3, 3)

def evalsig(df, signame):
    ics, ls, lx = {}, {}, {}
    for dt, gd in df[df[signame].notna() & df["fwd"].notna()].groupby("date"):
        if len(gd) < 30: continue
        ics[dt] = stats.spearmanr(gd[signame], gd["fwd"]).correlation
        q = pd.qcut(gd[signame].rank(method="first"), 5, labels=False, duplicates="drop")
        if q.max() < 4: continue
        ls[dt] = gd[q == q.max()]["fwd"].mean()-gd[q == 0]["fwd"].mean()
        lx[dt] = gd[q == q.max()]["fwd"].mean()-gd["fwd"].mean()
    ic = pd.Series(ics); r = pd.Series(ls)-cost; x = pd.Series(lx)-cost
    if len(ic) < 12: return None
    ict = ic.mean()/(ic.std(ddof=1)/np.sqrt(len(ic)))
    sh = lambda s: s.mean()/s.std(ddof=1)*ANN if s.std() else 0
    ex5 = lambda s: (lambda c: c.mean()/c.std(ddof=1)*ANN if c.std() else 0)(s[s < s.quantile(.95)])
    r36 = r.sort_index().tail(36)
    return dict(n=len(ic), univ=int(df[df[signame].notna()].groupby("date")["ticker"].count().mean()),
                ic=round(ic.mean(), 4), ic_t=round(ict, 2), ls_sh=round(sh(r), 2), ls_ex5=round(ex5(r), 2),
                long_ex=round(sh(x), 2), ls_sh_36m=round(sh(r36), 2))

print(f"{'因子/tier':22}{'univ':>5}{'IC':>9}{'IC_t':>7}{'LS_Sh':>7}{'剔5%':>7}{'多頭超額':>9}{'近36m_LS':>9}")
for fac, sig, exfin in [("Value", "vsig", False), ("Piotroski", "F", True)]:
    for tg in ["all", "large", "mid", "small"]:
        sub = b if tg == "all" else b[b["tier"] == tg]
        if exfin: sub = sub[~sub["sector"].isin(["Financials", "Real Estate"])]
        sub = sub.copy()
        if fac == "Value":
            sub["vsig"] = pd.concat([znorm(sub, "ep"), znorm(sub, "bp"), znorm(sub, "sp")], axis=1).mean(axis=1)
            sn = "vsig"
        else:
            sub["Fz"] = znorm(sub, "F"); sn = "Fz"
        m = evalsig(sub, sn)
        if m: print(f"{fac+'/'+tg:22}{m['univ']:>5}{m['ic']:>9}{m['ic_t']:>7}{m['ls_sh']:>7}{m['ls_ex5']:>7}{m['long_ex']:>9}{m['ls_sh_36m']:>9}")
        else: print(f"{fac+'/'+tg:22}  (樣本不足)")
