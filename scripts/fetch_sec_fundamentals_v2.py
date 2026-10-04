#!/usr/bin/env python3
"""EQ-SIM-006 v2 抓取:同 fetch_sec_fundamentals,但補存 start(期間起日)。
原因:同一申報(filed)含本期+前期比較+季度值,缺 start 無法分辨年度 flow,
舊管線靠不穩定排序任意取值→結果不可重現(已實證)。全量重抓,輸出新檔不動舊檔。
跑: uv run --with pandas --with pyarrow python scripts/fetch_sec_fundamentals_v2.py"""
import urllib.request, json, time, os
import pandas as pd

UA = {"User-Agent": "factor-lab research ansonnnnn486@gmail.com"}
OUT = "/home/anson/factor-lab/data/equity/sec_facts_v2.parquet"

def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()

FLOW = ["NetIncomeLoss", "GrossProfit",
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "WeightedAverageNumberOfSharesOutstandingBasic"]
STOCK = ["StockholdersEquity", "Assets", "CommonStockSharesOutstanding",
         "AssetsCurrent", "LiabilitiesCurrent", "LongTermDebtNoncurrent", "LongTermDebt"]
WANT = set(FLOW + STOCK)

uni = pd.read_csv("/home/anson/factor-lab/data/equity/universe.csv")
uni["cik"] = uni["cik"].astype(str).str.zfill(10)
done_tk = set(pd.read_parquet(OUT)["ticker"].unique()) if os.path.isfile(OUT) else set()
todo = uni[~uni["ticker"].isin(done_tk)].reset_index(drop=True)
print(f"universe {len(uni)} 檔,已抓 {len(done_tk)},本次新增 {len(todo)} 檔...")

recs, ok, fail, ferr = [], 0, 0, None
for i, row in todo.iterrows():
    tic, cik, sector = row["ticker"], row["cik"], row["sector"]
    try:
        cf = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))
        gaap = cf.get("facts", {}).get("us-gaap", {})
        for concept in WANT:
            if concept not in gaap:
                continue
            for uk, arr in gaap[concept]["units"].items():
                for e in arr:
                    if e.get("filed") and e.get("val") is not None:
                        recs.append((tic, sector, concept, e.get("start"), e.get("end"), e["filed"],
                                     e.get("fp"), e.get("form"), float(e["val"])))
        ok += 1
    except Exception as ex:
        fail += 1
        if ferr is None:
            ferr = repr(ex)[:120]
    if (i + 1) % 100 == 0:
        print(f"  ...{i+1}/{len(todo)}  ok{ok} fail{fail}")
    time.sleep(0.12)

df = pd.DataFrame(recs, columns=["ticker", "sector", "concept", "start", "end", "filed", "fp", "form", "val"])
for c in ("start", "end"):
    df[c] = pd.to_datetime(df[c], errors="coerce")
df["filed"] = pd.to_datetime(df["filed"])
if os.path.isfile(OUT):
    df = pd.concat([pd.read_parquet(OUT), df], ignore_index=True)
df = df.drop_duplicates(["ticker", "concept", "start", "end", "filed", "val"])
df.to_parquet(OUT)
print(f"\n存 {OUT}: 新增 {ok} 檔, 總 {df['ticker'].nunique()} 檔 {len(df)} 筆")
if fail:
    print(f"  (跳過 {fail} 檔,首錯 {ferr})")
