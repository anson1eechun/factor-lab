#!/usr/bin/env python3
"""EQ-SIM-005:小型股池 低波 + 動能,各測 + 與 value 正交組合。季頻 rebalance、成本25bps/邊。
含:IC_t / LS Sharpe / 多頭超額 / 剔5% / IS-OOS / 換手 / 等權vs市值權(容量) / 正交性 / combo gross-PnL 檢驗。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_lowvol_mom_eval.py"""
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"; ANN = np.sqrt(12); COST = 25/1e4
facts = pd.read_parquet(EQ + "sec_facts.parquet"); px = pd.read_parquet(EQ + "prices_monthly.parquet")
uni = pd.read_csv(EQ + "universe.csv"); tier = uni.set_index("ticker")["tier"]; sec = facts.groupby("ticker")["sector"].first()
facts["filed"] = facts["filed"].astype("datetime64[ns]"); facts["end"] = facts["end"].astype("datetime64[ns]")
base = px[["date", "ticker", "close"]].copy(); base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values(["ticker", "date"]).reset_index(drop=True)
# 價格因子(僅需月線)
base["ret"] = base.groupby("ticker")["close"].pct_change()
base["mom"] = base.groupby("ticker")["close"].shift(1)/base.groupby("ticker")["close"].shift(13)-1   # 12-1 動能
base["vol"] = base.groupby("ticker")["ret"].rolling(12).std().reset_index(0, drop=True)
base["lowvol"] = -base["vol"]
base = base.sort_values("date").reset_index(drop=True)
ANNF = facts["form"].astype(str).str.startswith(("10-K", "20-F"))
def asof(cn, a=False):
    f = facts[(facts["concept"] == cn) & (ANNF if a else True)][["ticker", "filed", "val"]].dropna().sort_values("filed")
    m = pd.merge_asof(base.sort_values("date"), f.rename(columns={"val": cn}), left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"]-m["filed"]).dt.days > 740, cn] = np.nan; return m[cn].values
ni = asof("NetIncomeLoss", True); se = asof("StockholdersEquity"); shr = asof("CommonStockSharesOutstanding")
rev = None
for cc in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]:
    v = asof(cc, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
mc = shr*base["close"].values
base["ep"] = ni/mc; base["bp"] = se/mc; base["sp"] = rev/mc; base["mc"] = mc
base["sector"] = base["ticker"].map(sec); base["tier"] = base["ticker"].map(tier)
base["fwd"] = base.groupby("ticker")["close"].shift(-1)/base["close"]-1
b = base[base["tier"] == "small"].sort_values(["date", "ticker"]).reset_index(drop=True)
def zn(df, c):
    g = df.groupby(["date", "sector"])[c]; return ((df[c]-g.transform("median"))/g.transform(lambda x: x.std())).clip(-3, 3)
b["value"] = pd.concat([zn(b, "ep"), zn(b, "bp"), zn(b, "sp")], axis=1).mean(axis=1)
b["lowvolz"] = zn(b, "lowvol"); b["momz"] = zn(b, "mom")
b["combo"] = b[["value", "lowvolz", "momz"]].mean(axis=1)
def sh(s): s = s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN), 2) if len(s) > 1 and s.std() else 0.0
def ict(s): s = s.dropna(); return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0

def held(sig, freq=3, cost=COST, vw=False):
    dts = sorted(b[b[sig].notna() & b["fwd"].notna()]["date"].unique())
    htop = hbot = None; turns = []; ls, lx, lsg = {}, {}, {}
    for i, dt in enumerate(dts):
        g = b[(b["date"] == dt) & b[sig].notna() & b["fwd"].notna()]
        if len(g) < 30: continue
        if i % freq == 0 or htop is None:
            q = pd.qcut(g[sig].rank(method="first"), 5, labels=False, duplicates="drop")
            if q.max() < 4: continue
            nt = set(g[q == q.max()]["ticker"]); nb = set(g[q == 0]["ticker"])
            if htop: turns.append(len(nt ^ htop)/(len(nt)+len(htop)))
            htop, hbot, reb = nt, nb, True
        else: reb = False
        gt = g[g["ticker"].isin(htop)]; gb = g[g["ticker"].isin(hbot)]
        if not len(gt) or not len(gb): continue
        tr = float((gt["fwd"]*(gt["mc"]/gt["mc"].sum())).sum()) if vw else gt["fwd"].mean()
        c = cost*turns[-1]*2 if (reb and turns) else 0.0
        lsg[dt] = tr-gb["fwd"].mean(); ls[dt] = lsg[dt]-c; lx[dt] = tr-g["fwd"].mean()-c
    L = pd.Series(ls).sort_index(); X = pd.Series(lx).sort_index(); G = pd.Series(lsg).sort_index()
    for s in (L, X, G): s.index = pd.to_datetime(s.index)
    ic = b[b[sig].notna() & b["fwd"].notna()].groupby("date").apply(lambda g: stats.spearmanr(g[sig], g["fwd"]).correlation if len(g) >= 30 else np.nan)
    mid = L.index[len(L)//2]
    ex5 = (lambda s: round(float(s[s < s.quantile(.95)].mean()/s[s < s.quantile(.95)].std(ddof=1)*ANN), 2))(L)
    return dict(ic_t=ict(ic.dropna()), gross=sh(G), ls=sh(L), lx=sh(X), ex5=ex5,
                turn=round(np.mean(turns), 2) if turns else 0, ls_IS=sh(L[L.index < mid]), ls_OOS=sh(L[L.index >= mid]), L=L)

print("EQ-SIM-005 小型股池 低波/動能/value/組合(季頻,25bps)\n")
print(f"{'因子':12}{'IC_t':>6}{'毛LS':>6}{'淨LS':>6}{'多頭超額':>9}{'剔5%':>7}{'換手':>6}{'IS':>6}{'OOS':>6}")
res = {}
for nm, sig in [("value", "value"), ("低波", "lowvolz"), ("動能", "momz"), ("組合EW-z", "combo")]:
    r = held(sig); res[nm] = r
    print(f"{nm:12}{r['ic_t']:>6}{r['gross']:>6}{r['ls']:>6}{r['lx']:>9}{r['ex5']:>7}{r['turn']:>6}{r['ls_IS']:>6}{r['ls_OOS']:>6}")
# 正交性:各因子淨LS月報酬相關
print("\n正交性(淨 LS 月報酬相關):")
M = pd.DataFrame({k: res[k]["L"] for k in ["value", "低波", "動能"]}).dropna()
print(M.corr().round(2).to_string())
# 市值權容量檢驗(combo)
vw = held("combo", vw=True)
print(f"\ncombo 容量檢驗:等權 多頭超額 {res['組合EW-z']['lx']}  vs  市值權 {vw['lx']}")
