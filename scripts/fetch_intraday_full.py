#!/usr/bin/env python3
"""SIM-017:抓 BTC/ETH 30m spot K 線全史(data.binance.vision 月度 zip,免費)。
輸出 empirical_runs/{btc,eth}_30m_full.parquet(UTC index, open/high/low/close/volume)。
跑: uv run --with pandas --with pyarrow python scripts/fetch_intraday_full.py"""
import urllib.request, io, zipfile, os, time
import pandas as pd

OUTDIR = "/home/anson/factor-lab/empirical_runs"
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "qvol", "ntrades", "tb_base", "tb_quote", "ignore"]

def fetch_month(sym, ym):
    u = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/30m/{sym}-30m-{ym}.zip"
    try:
        raw = urllib.request.urlopen(u, timeout=60).read()
    except Exception:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=COLS)
    if str(df.iloc[0, 0]).startswith("open"):      # 部分月份含表頭
        df = df.iloc[1:].reset_index(drop=True)
    df = df.astype({"open_time": "int64", "open": "float64", "high": "float64",
                    "low": "float64", "close": "float64", "volume": "float64"})
    # 2025 起 Binance 改用微秒 timestamp
    unit = "us" if df["open_time"].iloc[0] > 1e14 else "ms"
    df["ts"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    return df[["ts", "open", "high", "low", "close", "volume"]]

months = pd.period_range("2017-08", "2026-05", freq="M").astype(str).tolist()
for sym, out in (("BTCUSDT", "btc_30m_full"), ("ETHUSDT", "eth_30m_full")):
    parts, miss = [], []
    for ym in months:
        d = fetch_month(sym, ym)
        if d is None:
            miss.append(ym)
        else:
            parts.append(d)
        time.sleep(0.15)
    px = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts").set_index("ts")
    px.index = px.index.tz_localize(None)          # 存 UTC naive
    px.to_parquet(f"{OUTDIR}/{out}.parquet")
    print(f"{sym}: {len(px)} bars  {px.index.min()} → {px.index.max()}  缺月 {miss}")
