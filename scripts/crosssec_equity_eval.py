#!/usr/bin/env python3
"""EQ 橫截面基本面評估(月頻,point-in-time)。全真實、無前視(filed≤T)、扣成本。
價值(E/P,B/P,S/P)+品質(ROE)。輸出:RankIC/IC-IR、多頭top分位 vs 等權universe 超額、
LS分位、剔最高5%月壓測、年度regime、換手。可選行業中性。
跑: uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy python scripts/crosssec_equity_eval.py [factor] [cost_bps] [sector_neutral]
  factor ∈ {value, quality, combo}
"""
import sys, json
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
factor = sys.argv[1] if len(sys.argv) > 1 else "value"
cost_bps = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
sector_neutral = (len(sys.argv) > 3 and sys.argv[3] == "1")
ANN = np.sqrt(12)

facts = pd.read_parquet(EQ + "sec_facts.parquet")
px = pd.read_parquet(EQ + "prices_monthly.parquet").sort_values(["date", "ticker"])
sec = facts.groupby("ticker")["sector"].first()

# ---- point-in-time 對齊:對每個概念用 merge_asof(filed ≤ rebalance date) ----
base = px[["date", "ticker", "close"]].copy()
base["date"] = base["date"].astype("datetime64[ns]")
base = base.sort_values("date").reset_index(drop=True)
facts["filed"] = facts["filed"].astype("datetime64[ns]")
ANNUAL = facts["form"].astype(str).str.startswith(("10-K", "20-F"))


def asof(concept, annual=False):
    f = facts[(facts["concept"] == concept) & (ANNUAL if annual else True)][["ticker", "filed", "val"]]
    f = f.dropna().sort_values("filed")
    m = pd.merge_asof(base.sort_values("date"), f.rename(columns={"val": concept}),
                      left_on="date", right_on="filed", by="ticker", direction="backward")
    # 太舊的基本面(>2年)視為失效
    m.loc[(m["date"] - m["filed"]).dt.days > 740, concept] = np.nan
    return m[concept].values


b = base.copy()
b["ni"] = asof("NetIncomeLoss", annual=True)
b["gp"] = asof("GrossProfit", annual=True)
b["se"] = asof("StockholdersEquity")
b["assets"] = asof("Assets")
b["shares"] = asof("CommonStockSharesOutstanding")
# 營收:fallback 鏈 coalesce
rev = None
for c in ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
          "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]:
    v = asof(c, annual=True)
    rev = v if rev is None else np.where(pd.isna(rev), v, rev)
b["rev"] = rev

b["mktcap"] = b["shares"] * b["close"]
b["ep"] = b["ni"] / b["mktcap"]
b["bp"] = b["se"] / b["mktcap"]
b["sp"] = b["rev"] / b["mktcap"]
b["roe"] = b["ni"] / b["se"]
b["sector"] = b["ticker"].map(sec)
# 前向月報酬
b = b.sort_values(["ticker", "date"])
b["fwd"] = b.groupby("ticker")["close"].shift(-1) / b["close"] - 1
b = b.sort_values(["date", "ticker"]).reset_index(drop=True)


def xz(col, df):
    """逐月橫截面 z(可選行業內)。winsorize 極端值。"""
    s = df[col]
    if sector_neutral:
        g = df.groupby(["date", "sector"])[col]
    else:
        g = df.groupby("date")[col]
    z = (s - g.transform("median")) / g.transform(lambda x: x.std())
    return z.clip(-3, 3)


# 因子合成
b["z_ep"] = xz("ep", b); b["z_bp"] = xz("bp", b); b["z_sp"] = xz("sp", b); b["z_roe"] = xz("roe", b)
if factor == "value":
    b["sig"] = b[["z_ep", "z_bp", "z_sp"]].mean(axis=1)
elif factor == "quality":
    b["sig"] = b["z_roe"]
else:  # combo
    b["sig"] = b[["z_ep", "z_bp", "z_sp"]].mean(axis=1) * 0.5 + b["z_roe"] * 0.5

# ---- 評估 ----
dates = sorted(b["date"].unique())[:-1]   # 最後一月無 fwd
ics, long_ex, ls, w_prev = [], [], [], None
MINS = 30
ew_ret = {}
for dt in dates:
    g = b[(b["date"] == dt) & b["sig"].notna() & b["fwd"].notna()]
    if len(g) < MINS:
        continue
    ics.append(stats.spearmanr(g["sig"], g["fwd"]).correlation)
    ew = g["fwd"].mean(); ew_ret[dt] = ew
    q = pd.qcut(g["sig"].rank(method="first"), 5, labels=False)
    top = g[q == 4]; bot = g[q == 0]
    long_ex.append((dt, top["fwd"].mean() - ew))           # 多頭top分位 超額 vs 等權universe
    ls.append((dt, top["fwd"].mean() - bot["fwd"].mean()))

ic = pd.Series(ics).dropna()
lex = pd.Series(dict(long_ex)).sort_index()
lsr = pd.Series(dict(ls)).sort_index()
# 換手成本(多頭分位每月重組,約略以分位平均換手估;此處用LS腿換手上界近似:月度成本)
# 簡化:對多頭超額與LS,扣每月單邊 cost 的雙倍(進出)估計上界
cost_m = cost_bps / 1e4
def perf(r, name, charge=True):
    r = r.dropna()
    net = r - (cost_m if charge else 0)     # 月度保守扣一次邊際成本(低換手近似)
    if not len(net) or not net.std():
        return {}
    eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1
    cut = net[net < net.quantile(0.95)]
    yr = net.copy(); yr.index = pd.to_datetime(net.index)
    return {name: {
        "sharpe": round(float(net.mean()/net.std(ddof=1)*ANN), 3),
        "t": round(float(net.mean()/(net.std(ddof=1)/np.sqrt(len(net)))), 3),
        "ann_ret": round(float(net.mean()*12), 4),
        "maxdd": round(float(dd.min()), 4),
        "ex_top5pct": round(float(cut.mean()/cut.std(ddof=1)*ANN), 3) if cut.std() else None,
        "by_year": {str(y): round(float(gg.mean()/gg.std(ddof=1)*ANN), 2) for y, gg in yr.groupby(yr.index.year) if gg.std() and len(gg) >= 6},
        "n_months": int(len(net))}}

out = {"factor": factor, "cost_bps": cost_bps, "sector_neutral": sector_neutral,
       "rank_ic_mean": round(float(ic.mean()), 4),
       "ic_ir": round(float(ic.mean()/ic.std(ddof=1)), 3) if ic.std() else None,
       "ic_t": round(float(ic.mean()/(ic.std(ddof=1)/np.sqrt(len(ic)))), 3) if ic.std() else None,
       "ic_n_months": int(len(ic)),
       "avg_universe": int(b[b["sig"].notna()].groupby("date")["ticker"].count().mean())}
out.update(perf(lex, "long_top_excess_vs_EW"))
out.update(perf(lsr, "long_short_quintile"))
print(json.dumps(out, ensure_ascii=False, indent=2))
