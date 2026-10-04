#!/usr/bin/env python3
"""EQ-SIM-004 OOS 穩健性驗證(Small-Cap Value)。無參數因子→驗時間holdout/執行延遲/單調性/真實換手/成分/行業/加權。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_value_oos.py"""
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
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

b = base.copy()
ni = asof("NetIncomeLoss", True); se = asof("StockholdersEquity"); shares = asof("CommonStockSharesOutstanding")
rev = None
for cc in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(cc, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
mc = shares * b["close"].values
b["ep"] = ni/mc; b["bp"] = se/mc; b["sp"] = rev/mc; b["mc"] = mc
b["sector"] = b["ticker"].map(sec); b["tier"] = b["ticker"].map(tier)
b = b.sort_values(["ticker", "date"]); b["fwd"] = b.groupby("ticker")["close"].shift(-1)/b["close"]-1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)
b = b[b["tier"] == "small"].copy()                                       # 聚焦小型股

def znorm(df, col):
    g = df.groupby(["date", "sector"])[col]
    return ((df[col]-g.transform("median"))/g.transform(lambda x: x.std())).clip(-3, 3)
b["sig"] = pd.concat([znorm(b, "ep"), znorm(b, "bp"), znorm(b, "sp")], axis=1).mean(axis=1)

def sh(s): s = s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN), 2) if len(s) > 1 and s.std() else 0.0
def ict(s): s = s.dropna(); return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0

def series(sigcol, lag=0, cost=10/1e4, vw=False):
    """回傳 (IC series, LS series 扣成本, long超額 series, 月換手 list, 多頭行業集中 list)"""
    ic, ls, lx, turn, secc = {}, {}, {}, [], []
    prevtop = None
    for dt, gd in b[b[sigcol].notna() & b["fwd"].notna()].groupby("date"):
        s = gd[sigcol]
        if lag:                                                          # 用 lag 月前的訊號
            pass
        if len(gd) < 30:
            continue
        ic[dt] = stats.spearmanr(s, gd["fwd"]).correlation
        q = pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop")
        if q.max() < 4:
            continue
        top = gd[q == q.max()]; bot = gd[q == 0]
        if vw:
            wt = top["mc"]/top["mc"].sum(); tr = float((top["fwd"]*wt).sum())
        else:
            tr = top["fwd"].mean()
        ls[dt] = tr - bot["fwd"].mean(); lx[dt] = tr - gd["fwd"].mean()
        cur = set(top["ticker"])
        if prevtop is not None:
            turn.append(len(cur ^ prevtop)/(len(cur)+len(prevtop)))       # 對稱換手比
        prevtop = cur
        secc.append(top["sector"].value_counts(normalize=True).max())     # 多頭最大行業占比
    icS = pd.Series(ic).sort_index(); lsS = pd.Series(ls).sort_index()-cost; lxS = pd.Series(lx).sort_index()-cost
    for s in (icS, lsS, lxS): s.index = pd.to_datetime(s.index)
    return icS, lsS, lxS, turn, secc

ic, ls, lx, turn, secc = series("sig")
print(f"小型股 Value | 月數 {len(ls)} | {ls.index.min().date()}→{ls.index.max().date()}\n")

print("=== 1. 時間 holdout(IS 前半 / OOS 後半)===")
mid = ls.index[len(ls)//2]
for nm, msk in [("全期", slice(None)), ("IS 前半", ls.index < mid), ("OOS 後半", ls.index >= mid)]:
    i2, l2, x2 = ic[msk], ls[msk], lx[msk]
    print(f"  {nm:8}: IC_t {ict(i2):>5}  LS Sh {sh(l2):>5}  多頭超額 Sh {sh(x2):>5}  ({l2.index.min().date()}→{l2.index.max().date()})")

print("\n=== 2. 執行延遲(用 k 月前訊號交易)===")
for lag in (0, 1, 2):
    if lag == 0:
        ic2, ls2, lx2 = ic, ls, lx
    else:
        b["lsig"] = b.groupby("ticker")["sig"].shift(lag)
        ic2, ls2, lx2, _, _ = series("lsig")
    print(f"  lag={lag}月: IC_t {ict(ic2):>5}  LS Sh {sh(ls2):>5}  多頭超額 Sh {sh(lx2):>5}")

print("\n=== 3. 十分位單調性(各 decile 平均次月報酬 %)===")
dec = {}
for dt, gd in b[b["sig"].notna() & b["fwd"].notna()].groupby("date"):
    if len(gd) < 30: continue
    d = pd.qcut(gd["sig"].rank(method="first"), 10, labels=False, duplicates="drop")
    for di in range(int(d.max())+1):
        dec.setdefault(di, []).append(gd["fwd"][d == di].mean())
mono = [np.mean(v)*100 for k, v in sorted(dec.items())]
print("  D1(貴)→D10(便宜): " + " ".join(f"{x:+.2f}" for x in mono))
print(f"  單調性 Spearman(decile序, 報酬) = {stats.spearmanr(range(len(mono)), mono).correlation:.2f}")

print("\n=== 4. 真實換手與成本 ===")
tm = np.mean(turn)
print(f"  多頭分位月均換手 {tm:.1%}  →  若單邊成本25bps,月成本≈{tm*2*25:.0f}bps,年化拖累≈{tm*2*25*12/100:.1f}%")

print("\n=== 5. 三成分各自(行業中性 IC_t / 多頭超額 Sh)===")
for cmp in ["ep", "bp", "sp"]:
    b["c1"] = znorm(b, cmp); ic3, ls3, lx3, _, _ = series("c1")
    print(f"  {cmp}: IC_t {ict(ic3):>5}  多頭超額 Sh {sh(lx3):>5}")

print("\n=== 6. 行業集中 & 7. 加權法 ===")
print(f"  多頭分位最大行業占比 月均 {np.mean(secc):.0%}(<~30% 為分散)")
_, lsV, lxV, _, _ = series("sig", vw=True)
print(f"  等權 多頭超額 Sh {sh(lx):>5}  vs  市值權 多頭超額 Sh {sh(lxV):>5}")
