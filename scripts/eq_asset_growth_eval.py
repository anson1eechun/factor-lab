#!/usr/bin/env python3
"""EQ-SIM-002:資產成長異象(Cooper-Gulen-Schill)。因子=-資產成長(做多低成長)。
PIT:YoY 由連續年度 Assets 算,按新報告 filed 日對齊(filed≤T)。月頻,行業中性。
直接含分段衰減檢驗。跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_asset_growth_eval.py [sector_neutral=1] [cost_bps=10]"""
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

base = px[["date", "ticker", "close"]].copy()
base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)

# 年度 Assets → YoY 成長,可得日=新報告 filed
ann = facts["form"].astype(str).str.startswith(("10-K", "20-F"))
ag = facts[(facts["concept"] == "Assets") & ann][["ticker", "end", "filed", "val"]].dropna()
ag = ag.sort_values("filed").groupby(["ticker", "end"], as_index=False).first()        # 每財年首次申報(原始值,非重述)
ag = ag.sort_values(["ticker", "end"])
ag["prev"] = ag.groupby("ticker")["val"].shift(1)
gap = (ag["end"] - ag.groupby("ticker")["end"].shift(1)).dt.days
ag["growth"] = np.where((gap > 250) & (gap < 450), ag["val"] / ag["prev"] - 1, np.nan)
agf = ag[["ticker", "filed", "growth"]].dropna().sort_values("filed")

m = pd.merge_asof(base.sort_values("date"), agf, left_on="date", right_on="filed", by="ticker", direction="backward")
m.loc[(m["date"] - m["filed"]).dt.days > 740, "growth"] = np.nan
b = base.copy()
b["growth"] = m["growth"].values
b["sector"] = b["ticker"].map(sec)
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1) / b["close"] - 1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)
b["sig"] = -b["growth"]                                                                # 低成長=高分
if SN:
    g = b.groupby(["date", "sector"])["sig"]
    b["sig"] = ((b["sig"] - g.transform("median")) / g.transform(lambda x: x.std())).clip(-3, 3)

ics, lsr, lex = {}, {}, {}
for dt, gg in b[b["sig"].notna() & b["fwd"].notna()].groupby("date"):
    if len(gg) < 30:
        continue
    ics[dt] = stats.spearmanr(gg["sig"], gg["fwd"]).correlation
    q = pd.qcut(gg["sig"].rank(method="first"), 5, labels=False)
    lsr[dt] = gg[q == 4]["fwd"].mean() - gg[q == 0]["fwd"].mean()
    lex[dt] = gg[q == 4]["fwd"].mean() - gg["fwd"].mean()
ic = pd.Series(ics).sort_index(); ls = pd.Series(lsr).sort_index() - cost_bps/1e4; lx = pd.Series(lex).sort_index() - cost_bps/1e4
for s in (ic, ls, lx):
    s.index = pd.to_datetime(s.index)

def sh(s): s = s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN), 2) if len(s) > 1 and s.std() else 0.0
def ict(s): s = s.dropna(); return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0
def ex5(s): s = s.dropna(); c = s[s < s.quantile(.95)]; return round(float(c.mean()/c.std(ddof=1)*ANN), 2) if c.std() else None

out = {"factor": "asset_growth(-)", "sector_neutral": SN, "cost_bps": cost_bps,
       "n_months": int(len(ls)), "span": f"{ls.index.min().date()}→{ls.index.max().date()}",
       "rank_ic": round(float(ic.mean()), 4), "ic_ir": round(float(ic.mean()/ic.std(ddof=1)), 3),
       "ic_t": ict(ic), "avg_universe": int(b[b["sig"].notna()].groupby("date")["ticker"].count().mean()),
       "FULL": {"LS_sharpe": sh(ls), "LS_t": ict(ls), "LS_ex_top5": ex5(ls),
                "long_excess_sharpe": sh(lx), "long_excess_ex_top5": ex5(lx)}}
# 分段衰減
n = len(ls); segs = [("2014-18", 0, n//3), ("中段", n//3, 2*n//3), ("近段", 2*n//3, n)]
out["segments"] = {nm: {"span": f"{ls.iloc[a:c].index.min().date()}→{ls.iloc[a:c].index.max().date()}",
                        "ic_t": ict(ic.iloc[a:c]), "LS_sh": sh(ls.iloc[a:c]), "long_ex_sh": sh(lx.iloc[a:c])}
                   for nm, a, c in segs}
out["recent"] = {f"near{k}m": {"ic_t": ict(ic.tail(k)), "LS_sh": sh(ls.tail(k)), "long_ex_sh": sh(lx.tail(k))} for k in (36, 24)}
print(json.dumps(out, ensure_ascii=False, indent=2))
