#!/usr/bin/env python3
"""EQ Phase0:Yahoo 月線收盤(S&P500 universe,~12y),算報酬與市值。免帳戶。
輸出 data/equity/prices_monthly.parquet:date,ticker,close。
跑: uv run --with pandas --with pyarrow python scripts/fetch_yahoo_prices.py"""
import urllib.request, json, time, os
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}
OUT = "/home/anson/factor-lab/data/equity/prices_monthly.parquet"
FACTS = "/home/anson/factor-lab/data/equity/sec_facts.parquet"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

allt = sorted(pd.read_parquet(FACTS)["ticker"].unique())
done = set(pd.read_parquet(OUT)["ticker"].unique()) if __import__("os").path.isfile(OUT) else set()
tickers = [t for t in allt if t not in done]
print(f"universe {len(allt)} 檔,已抓 {len(done)},本次新增 {len(tickers)} 檔...")


def fetch(tic):
    y = tic.replace(".", "-")                       # BRK.B -> BRK-B
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?range=12y&interval=1mo"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read())
    res = d["chart"]["result"][0]
    ts = res["timestamp"]; cl = res["indicators"]["quote"][0]["close"]
    s = pd.DataFrame({"date": pd.to_datetime(ts, unit="s").normalize(), "close": cl, "ticker": tic})
    return s.dropna(subset=["close"])


rows, ok, fail = [], 0, 0
for i, t in enumerate(tickers):
    try:
        rows.append(fetch(t)); ok += 1
    except Exception:
        fail += 1
    if (i + 1) % 100 == 0:
        print(f"  ...{i+1}/{len(tickers)}  ok{ok} fail{fail}")
    time.sleep(0.05)

px = pd.concat(rows, ignore_index=True)
px["date"] = px["date"].values.astype("datetime64[M]").astype("datetime64[ns]")   # 月初對齊
if __import__("os").path.isfile(OUT):                                              # 增量併入
    px = pd.concat([pd.read_parquet(OUT), px], ignore_index=True)
px = px.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"]).reset_index(drop=True)
px.to_parquet(OUT)
print(f"\n存 {OUT}: {ok} 檔, {len(px)} 列, {px['date'].min().date()}→{px['date'].max().date()}")
print(f"  每月平均覆蓋 {px.groupby('date')['ticker'].nunique().tail(60).mean():.0f} 檔(近5年)")
