#!/usr/bin/env python3
"""EQ-SIM-006:Small-Cap Value 跨 universe OOS — Russell 2000 ex-S&P1500 獨立池。
信號/PIT/znorm/評估邏輯照搬 eq_universe_retest + eq_value_refine,不調任何參數。
tier='small' 同跑作為對照(應重現 validated 數字)。
預登錄 PASS(r2k_ex 須同時):① IC_t≥2 同向 ② 季頻淨LS(25bps)>0 且多頭超額>0
③ 剔5%仍正 ④ IS/OOS 兩半同向 ⑤ 十分位 Spearman>0
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/eq_r2k_oos.py"""
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
ANN = np.sqrt(12); COST = 25/1e4
facts = pd.read_parquet(EQ + "sec_facts_v2.parquet"); px = pd.read_parquet(EQ + "prices_monthly.parquet")
uni = pd.read_csv(EQ + "universe.csv"); tier = uni.set_index("ticker")["tier"]
sec = uni.set_index("ticker")["sector"]
facts["filed"] = facts["filed"].astype("datetime64[ns]"); facts["end"] = facts["end"].astype("datetime64[ns]")
base = px[["date", "ticker", "close"]].copy(); base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
ANNF = facts["form"].astype(str).str.startswith(("10-K", "20-F"))

def asof(cn, a=False):
    # 修正(v2 資料):同一申報(filed)含本期+前期比較+季度值。
    # 年度 flow → 只取期間 300–400 天(真年度),再每 (ticker,filed) 取最新 end;
    # instant(資產負債表/股數)→ 每 (ticker,filed) 取最新 end。全程穩定排序,結果可重現。
    f = facts[(facts["concept"] == cn) & (ANNF if a else True)][["ticker", "filed", "start", "end", "val"]].dropna(subset=["ticker", "filed", "val"])
    if a:
        dur = (f["end"] - f["start"]).dt.days
        f = f[(dur >= 300) & (dur <= 400)]
    f = f.sort_values(["filed", "end"], kind="mergesort").groupby(["ticker", "filed"], as_index=False).last()
    f = f.sort_values("filed", kind="mergesort")
    m = pd.merge_asof(base, f[["ticker", "filed", "val"]].rename(columns={"val": cn}), left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"]-m["filed"]).dt.days > 740, cn] = np.nan
    return m[cn].values

B = base.copy()
ni = asof("NetIncomeLoss", True); se = asof("StockholdersEquity"); shrs = asof("CommonStockSharesOutstanding")
rev = None
for cc in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(cc, True); rev = v if rev is None else np.where(pd.isna(rev), v, rev)
B["mc"] = shrs*B["close"].values; B["ep"] = ni/B["mc"]; B["bp"] = se/B["mc"]; B["sp"] = rev/B["mc"]
B["sector"] = B["ticker"].map(sec); B["tier"] = B["ticker"].map(tier)
B = B.sort_values(["ticker", "date"]); B["fwd"] = B.groupby("ticker")["close"].shift(-1)/B["close"]-1
B = B.sort_values(["date", "ticker"]).reset_index(drop=True)

def zn(df, c):
    g = df.groupby(["date", "sector"])[c]
    return ((df[c]-g.transform("median"))/g.transform(lambda x: x.std())).clip(-3, 3)

def sh(s): s = s.dropna(); return round(float(s.mean()/s.std(ddof=1)*ANN), 2) if len(s) > 1 and s.std() else 0.0
def ict(s): s = s.dropna(); return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0

def run_quarterly(b, freq=3, keep=1.0, vw=False, cost=COST):
    """季頻 LS/多頭超額(成本只在 rebalance 收),照搬 eq_value_refine.run"""
    dts = sorted(b[b["sig"].notna() & b["fwd"].notna()]["date"].unique())
    htop = hbot = None; turns = []; ls, lx = {}, {}
    for i, dt in enumerate(dts):
        g = b[(b["date"] == dt) & b["sig"].notna() & b["fwd"].notna()].copy()
        if keep < 1.0:
            g = g[g["mc"] >= g["mc"].quantile(1-keep)]
        if len(g) < 30: continue
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
        c = cost*turns[-1]*2 if (reb and turns) else 0.0
        ls[dt] = tr - gb["fwd"].mean() - c; lx[dt] = tr - g["fwd"].mean() - c
    L = pd.Series(ls).sort_index(); X = pd.Series(lx).sort_index()
    L.index = pd.to_datetime(L.index); X.index = pd.to_datetime(X.index)
    return L, X, turns

for tg in ["small", "r2k_ex"]:
    b = B[B["tier"] == tg].copy()
    b["sig"] = pd.concat([zn(b, "ep"), zn(b, "bp"), zn(b, "sp")], axis=1).mean(axis=1)
    val = b[b["sig"].notna() & b["fwd"].notna()]
    if not len(val):
        print(f"== {tg}: 無資料 =="); continue
    cov = val.groupby("date")["ticker"].count()
    print(f"\n{'='*72}\n== {tg} | 月均覆蓋 {cov.mean():.0f} 檔 | {val['date'].min().date()}→{val['date'].max().date()} ==")

    # --- 月頻 IC(判準①)+ 十分位(判準⑤)---
    ic, dec = {}, {}
    for dt, gd in val.groupby("date"):
        if len(gd) < 30: continue
        ic[dt] = stats.spearmanr(gd["sig"], gd["fwd"]).correlation
        d = pd.qcut(gd["sig"].rank(method="first"), 10, labels=False, duplicates="drop")
        for di in range(int(d.max())+1):
            dec.setdefault(di, []).append(gd["fwd"][d == di].mean())
    icS = pd.Series(ic).sort_index(); icS.index = pd.to_datetime(icS.index)
    mono = [np.mean(v)*100 for k, v in sorted(dec.items())]
    mono_sp = stats.spearmanr(range(len(mono)), mono).correlation
    print(f"[①] 月頻 IC {icS.mean():+.4f}  IC_t {ict(icS)}  (n={len(icS)})")
    print(f"[⑤] 十分位 D1(貴)→D10(便宜): " + " ".join(f"{x:+.2f}" for x in mono) + f"  Spearman {mono_sp:+.2f}")

    # --- 季頻 LS(判準②③④)---
    L, X, turns = run_quarterly(b)
    ex5 = L[L < L.quantile(.95)]
    mid = L.index[len(L)//2]
    print(f"[②] 季頻 25bps: 淨LS Sh {sh(L)}  多頭超額 Sh {sh(X)}  (換手/rebal {np.mean(turns):.2f}, n={len(L)})")
    print(f"[③] 剔最高5%月: LS Sh {sh(ex5)}")
    print(f"[④] IS({L.index.min().date()}→{mid.date()}): LS {sh(L[L.index < mid])}  |  OOS(→{L.index.max().date()}): LS {sh(L[L.index >= mid])}")
    print(f"[-] 近36m LS Sh {sh(L.sort_index().tail(36))}")

    # --- 附報:成本敏感度 / EW vs VW / 流動性分層 ---
    for cbps in (10, 30):
        L2, X2, _ = run_quarterly(b, cost=cbps/1e4)
        print(f"[-] 成本{cbps}bps: 淨LS {sh(L2)}  多頭超額 {sh(X2)}")
    _, Xv, _ = run_quarterly(b, vw=True)
    print(f"[-] 加權: 等權多頭超額 {sh(X)}  vs  市值權 {sh(Xv)}")
    for keep, nm in ((0.7, "剔最小30%"), (0.5, "剔最小50%")):
        L3, X3, _ = run_quarterly(b, keep=keep)
        print(f"[-] 流動性 {nm}: 淨LS {sh(L3)}  多頭超額 {sh(X3)}")
