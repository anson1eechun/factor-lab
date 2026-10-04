#!/usr/bin/env python3
"""抓訂單流(taker buy/sell imbalance)——用 K 線第9欄 takerBuyBaseVolume,免費免key。
TFI = 2*taker_buy/volume - 1 ∈[-1,1](>0 主動買盤主導)。
universe 日線 + BTC/ETH intraday。跑: uv run --with "numpy>=2" --with pandas python scripts/fetch_orderflow.py"""
import urllib.request, json, time
import pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"


def fetch(symbol, interval, nbars):
    out, end, last = [], None, None
    for _ in range(nbars // 900 + 3):
        if len(out) >= nbars:
            break
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000"
        if end:
            url += f"&endTime={end}"
        try:
            d = json.load(urllib.request.urlopen(url, timeout=25))
        except Exception:
            return None
        if not d:
            break
        out = d + out
        if d[0][0] == last:
            break
        last = d[0][0]; end = d[0][0] - 1
        time.sleep(0.15)
    if len(out) < 100:
        return None
    df = pd.DataFrame(out, columns=range(12))[[0, 4, 5, 9]]   # openTime, close, volume, takerBuyBase
    df.columns = ["timestamp", "close", "volume", "taker_buy"]
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    for c in ["close", "volume", "taker_buy"]:
        df[c] = df[c].astype(float)
    df["timestamp"] = df["timestamp"].astype("int64")
    df["tfi"] = (2 * df["taker_buy"] / df["volume"].replace(0, float("nan")) - 1)   # ∈[-1,1]
    return df.tail(nbars).reset_index(drop=True)


# universe 日線(沿用既有 universe 幣種)
uni_coins = list(pd.read_pickle(ER + "universe_1d.pkl").keys())
uni_flow = {}
for co in uni_coins:
    d = fetch(co + "USDT", "1d", 1200)
    if d is None:
        continue
    uni_flow[co] = d
pd.to_pickle(uni_flow, ER + "universe_flow_1d.pkl")
print(f"universe_flow_1d.pkl: {len(uni_flow)} 幣  (TFI 中位 {pd.concat([d['tfi'] for d in uni_flow.values()]).median():.3f})")

# BTC/ETH intraday
for a, sym in [("btc", "BTCUSDT"), ("eth", "ETHUSDT")]:
    for tf in ["15m", "1h", "4h"]:
        d = fetch(sym, tf, 5000)
        if d is not None:
            d.to_pickle(f"{ER}{a}_flow_{tf}.pkl")
    print(f"{a} intraday flow: 15m/1h/4h 已存")
print("done")
