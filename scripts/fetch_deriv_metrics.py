#!/usr/bin/env python3
"""抓 data.binance.vision 期貨 metrics 日檔(BTCUSDT,2022起),聚合成日線面板。
含:多空帳戶比(global/top-trader account)、頂級持倉比、OI、OI價值、taker比。免費免key。
跑: uv run --with pandas python scripts/fetch_deriv_metrics.py"""
import urllib.request, io, zipfile, datetime, time
import pandas as pd

OUT = "/home/anson/factor-lab/empirical_runs/deriv_btc.pkl"
UA = {"User-Agent": "Mozilla/5.0"}
B = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-"
COLS = {"sum_open_interest": "oi", "sum_open_interest_value": "oi_val",
        "count_long_short_ratio": "global_acct_ls", "count_toptrader_long_short_ratio": "top_acct_ls",
        "sum_toptrader_long_short_ratio": "top_pos_ls", "sum_taker_long_short_vol_ratio": "taker_ls"}

d0 = datetime.date(2022, 1, 1); d1 = datetime.date.today()
rows, ok, miss = [], 0, 0
day = d0
while day <= d1:
    u = B + day.strftime("%Y-%m-%d") + ".zip"
    try:
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read()))
        df = pd.read_csv(z.open(z.namelist()[0]))
        last = df.iloc[-1]                                       # 當日末筆(UTC日終快照)→ 對齊收盤
        rec = {"date": pd.Timestamp(day)}
        for src, dst in COLS.items():
            rec[dst] = float(last[src]) if src in df else None
        rows.append(rec); ok += 1
    except Exception:
        miss += 1
    if ok and ok % 200 == 0 and (day.day == 1 or miss % 50 == 0):
        print(f"  ...{day} ok{ok} miss{miss}")
    day += datetime.timedelta(days=1)
    time.sleep(0.03)

p = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
p["timestamp"] = p["date"].values.astype("datetime64[ms]").astype("int64")
p.to_pickle(OUT)
print(f"存 {OUT}: {ok} 日 ({p['date'].min().date()}→{p['date'].max().date()}), miss {miss}")
print(p.tail(3).to_string())
