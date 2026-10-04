#!/usr/bin/env python3
"""抓 BTC/ETH intraday(Binance,分頁)+ 衍生 45m/3h,存 empirical_runs/{asset}_{tf}.pkl。
跑: uv run --with "numpy>=2" --with pandas python scripts/fetch_intraday.py"""
import urllib.request, json, time
import numpy as np, pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}
NATIVE = ["5m", "15m", "30m", "1h", "4h"]
NBARS = 5000


def fetch(symbol, interval, nbars):
    out, end, last = [], None, None
    for _ in range(nbars // 900 + 3):
        if len(out) >= nbars:
            break
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000"
        if end:
            url += f"&endTime={end}"
        data = json.load(urllib.request.urlopen(url, timeout=25))
        if not data:
            break
        out = data + out
        oldest = data[0][0]
        if oldest == last:           # 沒再往前(到頂)
            break
        last = oldest; end = oldest - 1
        time.sleep(0.25)
    df = pd.DataFrame(out, columns=range(12))[[0, 1, 2, 3, 4, 5]]
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["timestamp"] = df["timestamp"].astype("int64")
    return df.tail(nbars).reset_index(drop=True)


def resample(df, rule):
    d = df.copy(); d.index = pd.to_datetime(d["timestamp"], unit="ms")
    r = pd.DataFrame({"open": d["open"].resample(rule).first(), "high": d["high"].resample(rule).max(),
                      "low": d["low"].resample(rule).min(), "close": d["close"].resample(rule).last(),
                      "volume": d["volume"].resample(rule).sum()}).dropna()
    r["timestamp"] = r.index.values.astype("datetime64[ms]").astype("int64")
    return r.reset_index(drop=True)


for a, sym in SYMS.items():
    store = {}
    for tf in NATIVE:
        df = fetch(sym, tf, NBARS)
        df.to_pickle(f"{ER}{a}_{tf}.pkl"); store[tf] = df
        print(f"{a}_{tf}: {df.shape}  {pd.to_datetime(df.timestamp.iloc[0],unit='ms')}→{pd.to_datetime(df.timestamp.iloc[-1],unit='ms')}")
    # 衍生
    r45 = resample(store["15m"], "45min"); r45.to_pickle(f"{ER}{a}_45m.pkl"); print(f"{a}_45m: {r45.shape}(由15m)")
    r3h = resample(store["1h"], "3h"); r3h.to_pickle(f"{ER}{a}_3h.pkl"); print(f"{a}_3h: {r3h.shape}(由1h)")
print("done")
