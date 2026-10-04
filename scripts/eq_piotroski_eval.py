#!/usr/bin/env python3
"""EQ-SIM-003:Piotroski F-score(9項財報健康度,品質)。高分=健康→做多。
排除金融/地產(無分類資產負債表)。逐年算YoY,PIT按10-K filed≤T對齊。月頻行業中性,含分段衰減。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_piotroski_eval.py [sector_neutral=1] [cost_bps=10]"""
import sys, json
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
SN = (sys.argv[1] if len(sys.argv) > 1 else "1") == "1"
cost_bps = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
ANN = np.sqrt(12)
facts = pd.read_parquet(EQ + "sec_facts.parquet")
px = pd.read_parquet(EQ + "prices_monthly.parquet")
sec = facts.groupby("ticker")["sector"].first()
facts["filed"] = facts["filed"].astype("datetime64[ns]"); facts["end"] = facts["end"].astype("datetime64[ns]")

# 年度寬表(每財年末,首次申報值)
ann = facts[facts["form"].astype(str).str.startswith(("10-K", "20-F"))].dropna(subset=["end", "val"])
ann = ann.sort_values("filed").groupby(["ticker", "concept", "end"], as_index=False).first()
wide = ann.pivot_table(index=["ticker", "end"], columns="concept", values="val", aggfunc="first").reset_index()
filed = ann.groupby(["ticker", "end"])["filed"].max().reset_index()
wide = wide.merge(filed, on=["ticker", "end"]).sort_values(["ticker", "end"]).reset_index(drop=True)

def col(name): return wide[name] if name in wide else pd.Series(np.nan, index=wide.index)
cfo = col("NetCashProvidedByUsedInOperatingActivities").fillna(col("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"))
ltd = col("LongTermDebt").fillna(col("LongTermDebtNoncurrent"))
rev = col("RevenueFromContractWithCustomerExcludingAssessedTax").fillna(col("Revenues")).fillna(col("SalesRevenueNet")).fillna(col("RevenueFromContractWithCustomerIncludingAssessedTax"))
ni, assets, ac, lc, gp, sh_ = col("NetIncomeLoss"), col("Assets"), col("AssetsCurrent"), col("LiabilitiesCurrent"), col("GrossProfit"), col("WeightedAverageNumberOfSharesOutstandingBasic")
wide = wide.assign(ni=ni, assets=assets, cfo=cfo, ltd=ltd, rev=rev, ac=ac, lc=lc, gp=gp, sh=sh_)

g = wide.groupby("ticker")
prevend = g["end"].shift(1); gap = (wide["end"] - prevend).dt.days
def pv(c): return g[c].shift(1)
roa = wide["ni"]/wide["assets"]; roa_p = pv("ni")/pv("assets")
crit = {
 "f1": roa > 0,
 "f2": wide["cfo"] > 0,
 "f3": roa > roa_p,
 "f4": wide["cfo"]/wide["assets"] > roa,
 "f5": (wide["ltd"]/wide["assets"]) < (pv("ltd")/pv("assets")),
 "f6": (wide["ac"]/wide["lc"]) > (pv("ac")/pv("lc")),
 "f7": wide["sh"] <= pv("sh")*1.01,
 "f8": (wide["gp"]/wide["rev"]) > (pv("gp")/pv("rev")),
 "f9": (wide["rev"]/wide["assets"]) > (pv("rev")/pv("assets")),
}
# 每項:True=1, False=0;再依輸入是否缺值改 NaN(比較對 NaN 會給 False,須另外標)
C = pd.DataFrame({k: v.astype(float).values for k, v in crit.items()})
inputs = {"f1":[roa],"f2":[wide["cfo"]],"f3":[roa,roa_p],"f4":[wide["cfo"],wide["assets"],roa],
 "f5":[wide["ltd"],wide["assets"],pv("ltd"),pv("assets")],"f6":[wide["ac"],wide["lc"],pv("ac"),pv("lc")],
 "f7":[wide["sh"],pv("sh")],"f8":[wide["gp"],wide["rev"],pv("gp"),pv("rev")],"f9":[wide["rev"],wide["assets"],pv("rev"),pv("assets")]}
for k, ins in inputs.items():
    miss = np.zeros(len(wide), dtype=bool)
    for x in ins:
        miss |= pd.isna(np.asarray(x, dtype="float64"))
    C[k] = np.where(miss, np.nan, C[k].values)
navail = C.notna().sum(axis=1); fraw = C.sum(axis=1, skipna=True)
fscore = np.where((navail >= 7) & (gap.values > 250) & (gap.values < 450), fraw * 9.0/navail, np.nan)
wide["F"] = fscore; wide["filed_av"] = wide["filed"]
fpanel = wide[["ticker", "filed_av", "F"]].dropna().rename(columns={"filed_av": "filed"}).sort_values("filed")

base = px[["date", "ticker", "close"]].copy(); base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
m = pd.merge_asof(base, fpanel, left_on="date", right_on="filed", by="ticker", direction="backward")
m.loc[(m["date"] - m["filed"]).dt.days > 740, "F"] = np.nan
b = base.copy(); b["F"] = m["F"].values; b["sector"] = b["ticker"].map(sec)
b = b[~b["sector"].isin(["Financials", "Real Estate"])]                      # Piotroski 排除金融地產
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1)/b["close"]-1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)
b["sig"] = b["F"]
if SN:
    gg = b.groupby(["date", "sector"])["sig"]
    b["sig"] = ((b["sig"]-gg.transform("median"))/gg.transform(lambda x: x.std())).clip(-3, 3)

ics, lsr, lex = {}, {}, {}
for dt, gd in b[b["sig"].notna() & b["fwd"].notna()].groupby("date"):
    if len(gd) < 30:
        continue
    ics[dt] = stats.spearmanr(gd["sig"], gd["fwd"]).correlation
    q = pd.qcut(gd["sig"].rank(method="first"), 5, labels=False, duplicates="drop")
    if q.max() < 4:
        continue
    lsr[dt] = gd[q == q.max()]["fwd"].mean()-gd[q == 0]["fwd"].mean()
    lex[dt] = gd[q == q.max()]["fwd"].mean()-gd["fwd"].mean()
ic = pd.Series(ics).sort_index(); ls = pd.Series(lsr).sort_index()-cost_bps/1e4; lx = pd.Series(lex).sort_index()-cost_bps/1e4
for s in (ic, ls, lx): s.index = pd.to_datetime(s.index)
def sh(s): s=s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN),2) if len(s)>1 and s.std() else 0.0
def ict(s): s=s.dropna(); return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))),2) if len(s)>1 and s.std() else 0.0
def ex5(s): s=s.dropna(); c=s[s<s.quantile(.95)]; return round(float(c.mean()/c.std(ddof=1)*ANN),2) if c.std() else None
out={"factor":"Piotroski_F","sector_neutral":SN,"n_months":int(len(ls)),"span":f"{ls.index.min().date()}→{ls.index.max().date()}",
 "rank_ic":round(float(ic.mean()),4),"ic_ir":round(float(ic.mean()/ic.std(ddof=1)),3),"ic_t":ict(ic),
 "avg_universe":int(b[b['sig'].notna()].groupby('date')['ticker'].count().mean()),
 "FULL":{"LS_sharpe":sh(ls),"LS_t":ict(ls),"LS_ex_top5":ex5(ls),"long_excess_sharpe":sh(lx),"long_excess_ex_top5":ex5(lx)}}
n=len(ls)
out["segments"]={nm:{"span":f"{ls.iloc[a:c].index.min().date()}→{ls.iloc[a:c].index.max().date()}","ic_t":ict(ic.iloc[a:c]),"LS_sh":sh(ls.iloc[a:c]),"long_ex_sh":sh(lx.iloc[a:c])} for nm,a,c in [("前",0,n//3),("中",n//3,2*n//3),("近",2*n//3,n)]}
out["recent"]={f"near{k}m":{"ic_t":ict(ic.tail(k)),"LS_sh":sh(ls.tail(k)),"long_ex_sh":sh(lx.tail(k))} for k in (36,24)}
print(json.dumps(out,ensure_ascii=False,indent=2))
