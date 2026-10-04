#!/usr/bin/env python3
"""抓 universe 各幣的 Binance 永續 funding rate 全史(分頁),日彙總,存 funding_1d.pkl。
funding 每 8h 一次(0/8/16 UTC);日彙總 = 當日三次 funding 之和(= 當日持倉成本)。
跑: uv run --with "numpy>=2" --with pandas python scripts/fetch_funding.py"""
import urllib.request, json, time, datetime
import pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
BASE = "https://fapi.binance.com/fapi/v1/fundingRate"
START = int(datetime.datetime(2019, 9, 1).timestamp() * 1000)


def fetch_funding(symbol):
    out, st = [], START
    for _ in range(20):
        try:
            d = json.load(urllib.request.urlopen(f"{BASE}?symbol={symbol}&startTime={st}&limit=1000", timeout=25))
        except Exception:
            return None
        if not d:
            break
        out += d
        last = d[-1]["fundingTime"]
        if last <= st or len(d) < 1000:
            break
        st = last + 1
        time.sleep(0.15)
    if len(out) < 100:
        return None
    df = pd.DataFrame(out)
    df["fundingTime"] = df["fundingTime"].astype("int64")
    df["fundingRate"] = df["fundingRate"].astype(float)
    df = df.drop_duplicates("fundingTime").sort_values("fundingTime")
    # 日彙總(UTC 日):當日 funding 之和
    df["date"] = pd.to_datetime(df["fundingTime"], unit="ms").dt.floor("D")
    daily = df.groupby("date")["fundingRate"].sum().reset_index()
    daily["timestamp"] = daily["date"].values.astype("datetime64[ms]").astype("int64")
    return daily[["timestamp", "fundingRate"]].rename(columns={"fundingRate": "funding"}).reset_index(drop=True)


uni = list(pd.read_pickle(ER + "universe_1d.pkl").keys())
out = {}
for co in uni:
    d = fetch_funding(co + "USDT")
    if d is None:
        print(f"  {co}: 無 perp/funding,跳過"); continue
    out[co] = d
    print(f"  {co}: {len(d)} 日  {pd.to_datetime(d.timestamp.iloc[0],unit='ms').date()}→{pd.to_datetime(d.timestamp.iloc[-1],unit='ms').date()}  最新funding={d.funding.iloc[-1]:.5f}")
pd.to_pickle(out, ER + "funding_1d.pkl")
print(f"已存 funding_1d.pkl,共 {len(out)} 幣有 funding 資料")
