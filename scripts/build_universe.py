#!/usr/bin/env python3
"""EQ-SIM-004:建 S&P1500 universe(大/中/小型 tier)。
S&P500(datasets,大)+S&P400(wiki,中,CIK由SEC補)+S&P600(wiki,小,含CIK)。
輸出 data/equity/universe.csv:ticker,cik,sector,tier。
跑: uv run --with pandas --with lxml python scripts/build_universe.py"""
import urllib.request, io, json, os
import pandas as pd

OUT = "/home/anson/factor-lab/data/equity/universe.csv"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (factor-lab research ansonnnnn486@gmail.com)"}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()

# SEC ticker→CIK(補 S&P400)
t2c = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in json.loads(get("https://www.sec.gov/files/company_tickers.json")).values()}
def cik_of(sym):
    for k in (sym, sym.replace(".", "-"), sym.replace(".", ""), sym.replace("-", ".")):
        if k in t2c: return t2c[k]
    return None

rows = []
# 大型 S&P500
sp5 = pd.read_csv(io.BytesIO(get("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv")))
for _, r in sp5.iterrows():
    rows.append((str(r["Symbol"]), str(int(r["CIK"])).zfill(10), r["GICS Sector"], "large"))
# 中型 S&P400 / 小型 S&P600(wiki)
def wiki(url, tier):
    t = pd.read_html(io.BytesIO(get(url)))[0]
    out = []
    for _, r in t.iterrows():
        sym = str(r["Symbol"]).strip()
        cik = str(int(r["CIK"])).zfill(10) if "CIK" in t.columns and pd.notna(r.get("CIK")) else cik_of(sym)
        sect = r.get("GICS Sector", None)
        if cik:
            out.append((sym, cik, sect, tier))
    return out
rows += wiki("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "mid")
rows += wiki("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "small")

u = pd.DataFrame(rows, columns=["ticker", "cik", "sector", "tier"])
order = {"large": 0, "mid": 1, "small": 2}
u = u.sort_values(by="tier", key=lambda s: s.map(order)).drop_duplicates("ticker", keep="first").reset_index(drop=True)
u.to_csv(OUT, index=False)
print(f"存 {OUT}: {len(u)} 檔  tier 分布={u['tier'].value_counts().to_dict()}  有CIK={u['cik'].notna().sum()}")
