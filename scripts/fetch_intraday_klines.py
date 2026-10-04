#!/usr/bin/env python3
"""抓 data.binance.vision USDT 永續月檔 klines(2023-01 起),存長歷史日內 pkl。
跑: uv run --with pandas python scripts/fetch_intraday_klines.py"""
import urllib.request, io, zipfile, datetime
import pandas as pd

B = "https://data.binance.vision/data/futures/um/monthly/klines"
UA = {"User-Agent": "Mozilla/5.0"}
COLS = ["timestamp", "open", "high", "low", "close", "volume"]

for sym, tf in [("BTCUSDT", "30m"), ("ETHUSDT", "30m"), ("BTCUSDT", "15m"), ("ETHUSDT", "15m")]:
    frames, miss = [], []
    y, m = 2023, 1
    today = datetime.date.today()
    while (y, m) < (today.year, today.month):
        u = f"{B}/{sym}/{tf}/{sym}-{tf}-{y}-{m:02d}.zip"
        try:
            z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(
                urllib.request.Request(u, headers=UA), timeout=30).read()))
            d = pd.read_csv(z.open(z.namelist()[0]), header=None)
            if str(d.iloc[0, 0]).startswith("open"):          # 部分月檔含表頭
                d = d.iloc[1:].reset_index(drop=True)
            d = d.iloc[:, :6]
            d.columns = COLS
            frames.append(d)
        except Exception as e:
            miss.append(f"{y}-{m:02d}")
        m += 1
        if m > 12: y, m = y + 1, 1
    p = pd.concat(frames, ignore_index=True).astype(float)
    p["timestamp"] = p["timestamp"].astype("int64")
    p = p.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    out = f"/home/anson/factor-lab/empirical_runs/{sym[:3].lower()}_{tf}_long.pkl"
    p.to_pickle(out)
    ts = pd.to_datetime(p["timestamp"], unit="ms")
    print(f"{out}: {len(p)} bars {ts.iloc[0].date()}→{ts.iloc[-1].date()} miss={miss}")
