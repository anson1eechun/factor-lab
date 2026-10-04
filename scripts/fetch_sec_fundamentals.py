#!/usr/bin/env python3
"""EQ Phase0:SEC EDGAR 抓 S&P500 基本面(point-in-time,每筆帶 filed 申報日)。
免帳戶免key,UA 需含聯絡信箱(SEC fair-use ≤10req/s)。
輸出長格式 data/equity/sec_facts.parquet:ticker,concept,end,filed,fp,form,val。
跑: uv run --with pandas --with pyarrow python scripts/fetch_sec_fundamentals.py"""
import urllib.request, json, io, time, os
import pandas as pd

UA = {"User-Agent": "factor-lab research ansonnnnn486@gmail.com"}
OUT = "/home/anson/factor-lab/data/equity/sec_facts.parquet"
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()


# 概念:flow(年度,做估值/品質分子)+ stock(資產負債表項)+ Piotroski 所需
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
                        recs.append((tic, sector, concept, e.get("end"), e["filed"],
                                     e.get("fp"), e.get("form"), float(e["val"])))
        ok += 1
    except Exception as ex:
        fail += 1
        if ferr is None:
            ferr = repr(ex)[:120]
    if (i + 1) % 50 == 0:
        print(f"  ...{i+1}/{len(todo)}  ok{ok} fail{fail}")
    time.sleep(0.12)

df = pd.DataFrame(recs, columns=["ticker", "sector", "concept", "end", "filed", "fp", "form", "val"])
df["filed"] = pd.to_datetime(df["filed"]); df["end"] = pd.to_datetime(df["end"], errors="coerce")
if os.path.isfile(OUT):                                    # 增量:併入既有
    df = pd.concat([pd.read_parquet(OUT), df], ignore_index=True)
df = df.drop_duplicates(["ticker", "concept", "end", "filed", "val"])
df.to_parquet(OUT)
print(f"\n存 {OUT}: 新增 {ok} 檔, 總 {df['ticker'].nunique()} 檔 {len(df)} 筆 facts")
print(f"  概念覆蓋: {df.groupby('concept')['ticker'].nunique().to_dict()}")
if fail:
    print(f"  (跳過 {fail} 檔,首錯 {ferr})")
