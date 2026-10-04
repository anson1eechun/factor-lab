#!/usr/bin/env python3
"""EQ-SIM-006:建 Russell 2000 ex-S&P1500 獨立 OOS universe。
Vanguard VTWO holdings(R2000 proxy)→ 剔除 universe.csv 既有(S&P1500)→ SEC 補 CIK +
SIC→sector 桶(行業中性用)→ 以 tier='r2k_ex' 併入 universe.csv。
跑: uv run --with pandas python scripts/build_universe_r2k.py"""
import urllib.request, json, time, os
import pandas as pd

UNI = "/home/anson/factor-lab/data/equity/universe.csv"
UA = {"User-Agent": "factor-lab research ansonnnnn486@gmail.com"}

def get(u, hdr=None):
    return urllib.request.urlopen(urllib.request.Request(u, headers=hdr or UA), timeout=40).read()

# 1) VTWO holdings(分頁 500)
tickers = []
for start in (1, 501, 1001, 1501):
    u = f"https://investor.vanguard.com/investment-products/etfs/profile/api/VTWO/portfolio-holding/stock?start={start}&count=500"
    d = json.loads(get(u, {"User-Agent": "Mozilla/5.0"}))
    ents = d.get("fund", {}).get("entity", [])
    tickers += [e["ticker"].strip() for e in ents if e.get("ticker")]
    if not ents:
        break
    time.sleep(0.3)
tickers = sorted(set(t for t in tickers if t and t.isascii()))
print(f"VTWO 成分 {len(tickers)} 檔")

# 2) 剔除既有 S&P1500 池(validated 測試池,確保零重疊)
uni = pd.read_csv(UNI)
have = set(uni["ticker"])
new = [t for t in tickers if t not in have and t.replace("-", ".") not in have]
print(f"剔除既有 universe 後剩 {len(new)} 檔")

# 3) SEC CIK 對映
t2c = {v["ticker"]: str(v["cik_str"]).zfill(10)
       for v in json.loads(get("https://www.sec.gov/files/company_tickers.json")).values()}
def cik_of(sym):
    for k in (sym, sym.replace("-", "."), sym.replace(".", "-"), sym.replace("-", ""), sym.replace(".", "")):
        if k in t2c:
            return t2c[k]
    return None
new = [(t, cik_of(t)) for t in new]
miss = [t for t, c in new if c is None]
new = [(t, c) for t, c in new if c]
print(f"CIK 對映成功 {len(new)} 檔(失敗 {len(miss)},如 {miss[:8]})")

# 4) SIC → sector 桶(行業中性 znorm 用;一致即可,不求精確 GICS)
def sic_sector(sic):
    if sic is None: return "Unknown"
    s = int(sic)
    if 100 <= s < 1000: return "Materials"
    if 1000 <= s < 1300: return "Materials"
    if 1300 <= s < 1400: return "Energy"
    if 1400 <= s < 1500: return "Materials"
    if 1500 <= s < 1800: return "Industrials"
    if 2000 <= s < 2400: return "Consumer Staples"
    if 2400 <= s < 2800: return "Materials"
    if 2830 <= s < 2840 or s == 2836: return "Health Care"
    if 2800 <= s < 2900: return "Materials"
    if 2900 <= s < 3000: return "Energy"
    if 3000 <= s < 3400: return "Materials"
    if s in (3826,) or 3840 <= s < 3852: return "Health Care"
    if 3570 <= s < 3580 or 3660 <= s < 3700 or 3670 <= s < 3680 or 3812 <= s < 3813: return "Information Technology"
    if 3400 <= s < 4000: return "Industrials"
    if 4800 <= s < 4900: return "Communication Services"
    if 4900 <= s < 5000: return "Utilities"
    if 4000 <= s < 4800: return "Industrials"
    if 5000 <= s < 5200: return "Consumer Discretionary"
    if 5200 <= s < 6000: return "Consumer Discretionary"
    if 6500 <= s < 6600 or s == 6798: return "Real Estate"
    if 6000 <= s < 6800: return "Financials"
    if 7370 <= s < 7380: return "Information Technology"
    if 8000 <= s < 8100 or s == 8731: return "Health Care"
    if 7000 <= s < 9000: return "Consumer Discretionary"
    return "Unknown"

rows, fail = [], 0
for i, (t, c) in enumerate(new):
    try:
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{c}.json"))
        rows.append((t, c, sic_sector(sub.get("sic") or None), "r2k_ex"))
    except Exception:
        fail += 1
    if (i + 1) % 200 == 0:
        print(f"  ...SIC {i+1}/{len(new)}")
    time.sleep(0.11)
print(f"SIC 完成 {len(rows)} 檔(失敗 {fail})")

add = pd.DataFrame(rows, columns=["ticker", "cik", "sector", "tier"])
out = pd.concat([uni, add], ignore_index=True).drop_duplicates("ticker", keep="first")
out.to_csv(UNI, index=False)
print(f"universe.csv 更新: 總 {len(out)} 檔  tier={out['tier'].value_counts().to_dict()}")
print(f"r2k_ex sector 分布: {add['sector'].value_counts().to_dict()}")
