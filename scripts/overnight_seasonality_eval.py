#!/usr/bin/env python3
"""SIM-2026-06-10-017:BTC/ETH overnight/weekend 時段季節性(confirmatory,兩窗口,不掃格)。
窗口:① 美股盤外(NYSE 收盤→次交易日開盤,含週末假日)vs 盤中 ② 週五收→週一開。
NYSE 真實日曆(pandas-market-calendars,含 DST/假日/半日)。成交=邊界後第一根 30m bar 開盤價。
預登錄判準見辯論報告。跑:
uv run --with "numpy>=2" --with pandas --with pyarrow --with scipy --with pandas-market-calendars \
  python scripts/overnight_seasonality_eval.py"""
import numpy as np, pandas as pd
import pandas_market_calendars as mcal
from scipy import stats

ER = "/home/anson/factor-lab/empirical_runs/"
COSTS = [0.0, 2e-4, 5e-4]          # 單邊:0 / maker 2bps / taker 5bps;每時段 2 邊

def sh(s, ppy):
    s = s.dropna()
    return round(float(s.mean()/s.std(ddof=1)*np.sqrt(ppy)), 2) if len(s) > 1 and s.std() else 0.0

def tstat(s):
    s = s.dropna()
    return round(float(s.mean()/(s.std(ddof=1)/np.sqrt(len(s)))), 2)

def maxdd(r):
    eq = (1+r.fillna(0)).cumprod()
    return round(float((eq/eq.cummax()-1).min()), 3)

nyse = mcal.get_calendar("NYSE")
sched = nyse.schedule(start_date="2017-08-01", end_date="2026-06-09")
opens_utc = sched["market_open"].dt.tz_convert("UTC").dt.tz_localize(None)
closes_utc = sched["market_close"].dt.tz_convert("UTC").dt.tz_localize(None)

for asset, f in (("BTC", "btc_30m_full"), ("ETH", "eth_30m_full")):
    px = pd.read_parquet(ER + f + ".parquet")["open"]            # bar 開盤價,index=bar 起始(UTC)
    def price_at(ts_series, lagmin=0):
        t = ts_series + pd.Timedelta(minutes=lagmin)
        idx = px.index.searchsorted(t.values, side="left")        # 邊界後第一根 bar
        ok = idx < len(px)
        out = pd.Series(np.nan, index=ts_series.index)
        out[ok] = px.values[idx[ok]]
        return out

    def build(lagmin=0):
        po = price_at(opens_utc, lagmin); pc = price_at(closes_utc, lagmin)
        d = pd.DataFrame({"open_px": po.values, "close_px": pc.values}, index=sched.index)
        d["r_id"] = d["close_px"]/d["open_px"] - 1                          # 盤中
        d["r_on"] = d["open_px"]/d["close_px"].shift(1) - 1                 # 盤外(前收→今開)
        d["gap_days"] = (opens_utc.values - closes_utc.shift(1).values)/np.timedelta64(1, "D")
        return d.dropna(subset=["r_on", "r_id"])

    d = build()
    yrs = (d.index[-1]-d.index[0]).days/365.25; ppy = len(d)/yrs
    wkd = d[d["gap_days"] > 1.5]                                            # 週末/長假窗口
    print(f"\n{'='*78}\n== {asset} | {d.index[0].date()}→{d.index[-1].date()} | 交易日 {len(d)} | 週末窗 {len(wkd)} ==")

    print(f"[1] 顯著性: 盤外均值 {d['r_on'].mean()*1e4:+.1f}bps t={tstat(d['r_on'])} | 盤中 {d['r_id'].mean()*1e4:+.1f}bps t={tstat(d['r_id'])}"
          f" | 盤外-盤中差 t={tstat(d['r_on']-d['r_id'])} | 週末均值 {wkd['r_on'].mean()*1e4:+.1f}bps t={tstat(wkd['r_on'])}")
    # Bonferroni 家族 4 檢定門檻 p<0.0125 → |t|>2.50
    print(f"    Bonferroni(4 檢定)需 |t|>2.50")

    hodl = (d["close_px"]/d["close_px"].shift(1)-1).dropna()
    print(f"[2] HODL 基準: Sharpe {sh(hodl, ppy)}  MaxDD {maxdd(hodl)}")
    for c in COSTS:
        net = d["r_on"] - 2*c
        ex5 = net[net < net.quantile(.95)]
        mid = len(net)//2
        print(f"[2] 盤外策略@{c*1e4:.0f}bps/邊: 淨Sh {sh(net, ppy)}  MaxDD {maxdd(net)}"
              f"  [3]剔5% {sh(ex5, ppy)}  [4]IS {sh(net.iloc[:mid], ppy)}/OOS {sh(net.iloc[mid:], ppy)}")
    net5 = d["r_on"] - 2*5e-4
    post = net5[net5.index >= "2024-01-11"]                                  # 現貨 ETF 上市
    print(f"[4] 年度淨均值@5bps(bps/日): " + " ".join(f"{y}:{g.mean()*1e4:+.0f}" for y, g in net5.groupby(net5.index.year)))
    print(f"[4] ETF後(2024-01-11→): 淨Sh@5bps {sh(post, ppy)}  t={tstat(post)}  n={len(post)}")
    dl = build(lagmin=30)
    netl = dl["r_on"] - 2*2e-4
    print(f"[6] 延遲30min@maker2bps: 淨Sh {sh(netl, len(dl)/yrs)}")
