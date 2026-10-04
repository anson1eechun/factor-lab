#!/usr/bin/env python3
"""抓多幣 USDT 日線(Binance,分頁)存成 universe dict pkl,供橫截面因子用。
跑: uv run --with "numpy>=2" --with pandas python scripts/fetch_universe.py"""
import urllib.request, json, time
import pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
COINS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
         "LTC", "BCH", "ATOM", "NEAR", "UNI", "AAVE", "FIL", "ETC", "XLM", "TRX",
         # 擴充至 ~60(抓不到/太短者 fetch() 回 None 自動跳過)
         "MATIC", "POL", "SHIB", "APT", "ARB", "OP", "INJ", "SUI", "SEI", "TIA",
         "RENDER", "IMX", "STX", "GRT", "ALGO", "FTM", "S", "MKR", "LDO", "SAND",
         "MANA", "AXS", "GALA", "CHZ", "CRV", "SNX", "COMP", "DYDX", "1INCH", "ENS",
         "RUNE", "KAVA", "ZEC", "DASH", "EOS", "NEO", "IOTA", "QTUM", "WAVES", "THETA",
         "EGLD", "FLOW", "XTZ", "CAKE", "ROSE", "ICP", "HBAR", "VET", "JUP", "PYTH",
         "WLD", "ORDI", "JTO", "PENDLE", "ENA", "AR", "GMT", "FET", "MINA", "KSM"]
NBARS = 2500


def fetch(symbol, nbars=NBARS):
    out, end, last = [], None, None
    for _ in range(nbars // 900 + 3):
        if len(out) >= nbars:
            break
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=1000"
        if end:
            url += f"&endTime={end}"
        try:
            data = json.load(urllib.request.urlopen(url, timeout=25))
        except Exception:
            return None
        if not data:
            break
        out = data + out
        if data[0][0] == last:
            break
        last = data[0][0]; end = data[0][0] - 1
        time.sleep(0.2)
    if len(out) < 200:
        return None
    df = pd.DataFrame(out, columns=range(12))[[0, 1, 2, 3, 4, 5]]
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["timestamp"] = df["timestamp"].astype("int64")
    return df.tail(nbars).reset_index(drop=True)


uni = {}
for co in COINS:
    df = fetch(co + "USDT")
    if df is None:
        print(f"  {co}: 跳過(抓取失敗/太短)"); continue
    uni[co] = df
    print(f"  {co}: {df.shape}  {pd.to_datetime(df.timestamp.iloc[0],unit='ms').date()}→{pd.to_datetime(df.timestamp.iloc[-1],unit='ms').date()}")
pd.to_pickle(uni, ER + "universe_1d.pkl")
print(f"已存 universe_1d.pkl,共 {len(uni)} 幣")
