#!/usr/bin/env python3
"""EQ-SIM-004 精修:季頻 rebalance + 流動性過濾(市值 proxy)。
針對 OOS 兩限制(換手76%/月、溢酬集中微型股),檢驗降換手+剔微型後 net Sharpe 是否仍穩。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_value_refine.py"""
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
ANN = np.sqrt(12); COST = 25/1e4   # 小型股單邊 25bps
facts = pd.read_parquet(EQ + "sec_facts.parquet"); px = pd.read_parquet(EQ + "prices_monthly.parquet")
uni = pd.read_csv(EQ + "universe.csv"); tier = uni.set_index("ticker")["tier"]
sec = facts.groupby("ticker")["sector"].first()
facts["filed"] = facts["filed"].astype("datetime64[ns]"); facts["end"] = facts["end"].astype("datetime64[ns]")
base = px[["date", "ticker", "close"]].copy(); base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
ANNF = facts["form"].astype(str).str.startswith(("10-K", "20-F"))
def asof(cn, a=False):
    f = facts[(facts["concept"] == cn) & (ANNF if a else True)][["ticker", "filed", "val"]].dropna().sort_values("filed")
    m = pd.merge_asof(base.sort_values("date"), f.rename(columns={"val": cn}), left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"]-m["filed"]).dt.days > 740, cn] = np.nan; return m[cn].values
b = base.copy()
ni = asof("NetIncomeLoss", True); se = asof("StockholdersEquity"); shrs = asof("CommonStockSharesOutstanding")
rev = None
for cc in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(cc, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
b["mc"] = shrs*b["close"].values; b["ep"] = ni/b["mc"]; b["bp"] = se/b["mc"]; b["sp"] = rev/b["mc"]
b["sector"] = b["ticker"].map(sec); b["tier"] = b["ticker"].map(tier)
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1)/b["close"]-1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True); b = b[b["tier"] == "small"].copy()
def zn(df, c):
    g = df.groupby(["date", "sector"])[c]; return ((df[c]-g.transform("median"))/g.transform(lambda x: x.std())).clip(-3, 3)
b["sig"] = pd.concat([zn(b, "ep"), zn(b, "bp"), zn(b, "sp")], axis=1).mean(axis=1)
def sh(s): s = s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN), 2) if len(s) > 1 and s.std() else 0.0

def run(freq=1, keep=1.0, vw=False):
    dts = sorted(b[b["sig"].notna() & b["fwd"].notna()]["date"].unique())
    htop = hbot = None; turns = []
    ls, lx = {}, {}
    for i, dt in enumerate(dts):
        g = b[(b["date"] == dt) & b["sig"].notna() & b["fwd"].notna()].copy()
        if keep < 1.0:                                            # 流動性過濾:剔最小市值
            g = g[g["mc"] >= g["mc"].quantile(1-keep)]
        if len(g) < 30:
            continue
        reb = (i % freq == 0) or htop is None
        if reb:
            q = pd.qcut(g["sig"].rank(method="first"), 5, labels=False, duplicates="drop")
            if q.max() < 4: continue
            nt = set(g[q == q.max()]["ticker"]); nb = set(g[q == 0]["ticker"])
            if htop is not None:
                turns.append(len(nt ^ htop)/(len(nt)+len(htop)))
            htop, hbot = nt, nb
        gt = g[g["ticker"].isin(htop)]; gb = g[g["ticker"].isin(hbot)]
        if not len(gt) or not len(gb): continue
        tr = float((gt["fwd"]*(gt["mc"]/gt["mc"].sum())).sum()) if vw else gt["fwd"].mean()
        c = COST*turns[-1]*2 if (reb and turns) else 0.0           # 成本只在 rebalance 收
        ls[dt] = tr - gb["fwd"].mean() - c; lx[dt] = tr - g["fwd"].mean() - c
    L = pd.Series(ls).sort_index(); X = pd.Series(lx).sort_index()
    L.index = pd.to_datetime(L.index); X.index = pd.to_datetime(X.index)
    ex5 = (lambda s: round(float((s[s < s.quantile(.95)].mean()/s[s < s.quantile(.95)].std(ddof=1))*ANN), 2))(L)
    mid = L.index[len(L)//2]
    return dict(n=len(L), turn=round(np.mean(turns), 2) if turns else 0, ls=sh(L), lx=sh(X), ex5=ex5,
                ls_IS=sh(L[L.index < mid]), ls_OOS=sh(L[L.index >= mid]))

print(f"小型股 Value 精修(成本 25bps/邊,成本只在 rebalance 收)\n")
print(f"{'設定':30}{'換手':>6}{'LS_Sh':>7}{'多頭超額':>9}{'剔5%':>7}{'LS_IS':>7}{'LS_OOS':>7}")
grid = [("月頻 無過濾(原版)", 1, 1.0, False), ("季頻 無過濾", 3, 1.0, False),
        ("季頻 +剔最小30%", 3, 0.7, False), ("季頻 +剔最小50%", 3, 0.5, False),
        ("季頻 剔30% 市值權", 3, 0.7, True), ("月頻 +剔最小30%", 1, 0.7, False)]
for nm, f, k, vw in grid:
    r = run(f, k, vw)
    print(f"{nm:30}{r['turn']:>6}{r['ls']:>7}{r['lx']:>9}{r['ex5']:>7}{r['ls_IS']:>7}{r['ls_OOS']:>7}")
