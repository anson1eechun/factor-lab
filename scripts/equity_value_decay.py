#!/usr/bin/env python3
"""EQ-SIM-001 REWORK #1:行業中性 Value 衰減檢驗。
重建月度 LS 分位 + 多頭超額序列,做滾動24m Sharpe + 分段(三段/近24·36m)IC與Sharpe。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/equity_value_decay.py"""
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
ANN = np.sqrt(12)
facts = pd.read_parquet(EQ + "sec_facts.parquet")
px = pd.read_parquet(EQ + "prices_monthly.parquet")
sec = facts.groupby("ticker")["sector"].first()

base = px[["date", "ticker", "close"]].copy()
base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
facts["filed"] = facts["filed"].astype("datetime64[ns]")
ANNUAL = facts["form"].astype(str).str.startswith(("10-K", "20-F"))


def asof(concept, annual=False):
    f = facts[(facts["concept"] == concept) & (ANNUAL if annual else True)][["ticker", "filed", "val"]].dropna().sort_values("filed")
    m = pd.merge_asof(base.sort_values("date"), f.rename(columns={"val": concept}),
                      left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"] - m["filed"]).dt.days > 740, concept] = np.nan
    return m[concept].values


b = base.copy()
b["ni"] = asof("NetIncomeLoss", True); b["se"] = asof("StockholdersEquity"); b["shares"] = asof("CommonStockSharesOutstanding")
rev = None
for c in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(c, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
b["rev"] = rev
b["mktcap"] = b["shares"] * b["close"]
b["ep"] = b["ni"]/b["mktcap"]; b["bp"] = b["se"]/b["mktcap"]; b["sp"] = b["rev"]/b["mktcap"]
b["sector"] = b["ticker"].map(sec)
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1)/b["close"]-1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)

def xz(col):
    g = b.groupby(["date", "sector"])[col]
    return ((b[col]-g.transform("median"))/g.transform(lambda x: x.std())).clip(-3, 3)
b["sig"] = pd.concat([xz("ep"), xz("bp"), xz("sp")], axis=1).mean(axis=1)

# 月度序列
ics, lsr, lex = {}, {}, {}
for dt, g in b[b["sig"].notna() & b["fwd"].notna()].groupby("date"):
    if len(g) < 30:
        continue
    ics[dt] = stats.spearmanr(g["sig"], g["fwd"]).correlation
    q = pd.qcut(g["sig"].rank(method="first"), 5, labels=False)
    lsr[dt] = g[q == 4]["fwd"].mean() - g[q == 0]["fwd"].mean()
    lex[dt] = g[q == 4]["fwd"].mean() - g["fwd"].mean()
ic = pd.Series(ics).sort_index(); ls = pd.Series(lsr).sort_index(); lx = pd.Series(lex).sort_index()
ls.index = pd.to_datetime(ls.index); lx.index = pd.to_datetime(lx.index); ic.index = pd.to_datetime(ic.index)

def sh(s): s = s.dropna(); return float(s.mean()/s.std(ddof=1)*ANN) if len(s) > 1 and s.std() else 0.0
def ict(s): s = s.dropna(); return float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))) if len(s) > 1 and s.std() else 0.0

print(f"樣本 {ls.index.min().date()} → {ls.index.max().date()}  共 {len(ls)} 月\n")
print("=== 逐年 ===")
print(f"{'年':6}{'IC':>8}{'LS_Sh':>8}{'多頭超額_Sh':>12}{'月數':>5}")
for y in sorted(set(ls.index.year)):
    m = ls.index.year == y
    print(f"{y:<6}{ic[ic.index.year==y].mean():>8.3f}{sh(ls[m]):>8.2f}{sh(lx[m]):>12.2f}{m.sum():>5}")

print("\n=== 三等分時段 ===")
n = len(ls); thirds = [(0, n//3), (n//3, 2*n//3), (2*n//3, n)]
for a, c in thirds:
    seg_ls = ls.iloc[a:c]; seg_ic = ic.iloc[a:c]; seg_lx = lx.iloc[a:c]
    print(f"  {seg_ls.index.min().date()}→{seg_ls.index.max().date()}: IC {seg_ic.mean():+.3f}(t{ict(seg_ic):+.2f})  LS Sh {sh(seg_ls):+.2f}  多頭超額 Sh {sh(seg_lx):+.2f}")

print("\n=== 近端窗 ===")
for k in (36, 24, 12):
    print(f"  近{k}月: IC {ic.tail(k).mean():+.3f}(t{ict(ic.tail(k)):+.2f})  LS Sh {sh(ls.tail(k)):+.2f}  多頭超額 Sh {sh(lx.tail(k)):+.2f}")

print("\n=== 滾動24m LS Sharpe 軌跡(每6月取點)===")
roll = ls.rolling(24).apply(lambda x: x.mean()/x.std(ddof=1)*ANN if x.std() else 0)
r = roll.dropna()
for i in range(0, len(r), 6):
    print(f"  {r.index[i].date()}  {r.iloc[i]:+.2f}")
print(f"  最新 {r.index[-1].date()}  {r.iloc[-1]:+.2f}  | 滾動 min {r.min():+.2f} max {r.max():+.2f}")
