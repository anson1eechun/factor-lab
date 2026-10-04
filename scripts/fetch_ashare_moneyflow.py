#!/usr/bin/env python3
"""EQ Phase0 冒煙:抓沪深300個股資金流(akshare,免token,~100交易日)。
東方財富個股資金流:主力/超大單/大單 净额。建長格式面板存 parquet。
跑: uv run --with akshare --with pandas --with pyarrow python scripts/fetch_ashare_moneyflow.py"""
import time
import pandas as pd
import akshare as ak

OUT = "/home/anson/factor-lab/data/ashare/moneyflow_smoke.parquet"
import os
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# 1) 沪深300 成分
try:
    cons = ak.index_stock_cons_csindex(symbol="000300")
    codes = cons["成分券代码"].astype(str).str.zfill(6).tolist()
except Exception:
    cons = ak.index_stock_cons(symbol="000300")
    codes = cons.iloc[:, 0].astype(str).str.zfill(6).tolist()
print(f"沪深300 成分 {len(codes)} 檔")

COLS = {"日期": "date", "收盘价": "close",
        "主力净流入-净额": "main_net", "超大单净流入-净额": "xl_net",
        "大单净流入-净额": "lg_net", "主力净流入-净占比": "main_pct"}


def mkt(c):
    return "sh" if c[0] == "6" else ("bj" if c[0] in "84" else "sz")


rows, ok, fail, first_err = [], 0, 0, None
for i, c in enumerate(codes):
    try:
        d = ak.stock_individual_fund_flow(stock=c, market=mkt(c))
        d = d[list(COLS)].rename(columns=COLS)
        d["code"] = c
        rows.append(d)
        ok += 1
    except Exception as e:
        fail += 1
        if first_err is None:
            first_err = repr(e)[:160]
    if (i + 1) % 50 == 0:
        print(f"  ...{i+1}/{len(codes)}  ok{ok} fail{fail}")
    time.sleep(0.15)

if not rows:
    print(f"\n✗ 全失敗。首個錯誤:{first_err}")
    print("  若是 RemoteDisconnected/ConnectionError → 該 IP 連不上 eastmoney(需中國 IP/能連 eastmoney 的機器)。")
    raise SystemExit(1)
if fail:
    print(f"  (跳過 {fail} 檔,首錯:{first_err})")
panel = pd.concat(rows, ignore_index=True)
panel["date"] = pd.to_datetime(panel["date"])
for col in ["close", "main_net", "xl_net", "lg_net", "main_pct"]:
    panel[col] = pd.to_numeric(panel[col], errors="coerce")
panel = panel.sort_values(["code", "date"]).reset_index(drop=True)
panel.to_parquet(OUT)
print(f"\n存 {OUT}")
print(f"  {ok} 檔 / 日期 {panel['date'].min().date()}→{panel['date'].max().date()} / 共 {len(panel)} 列")
print(f"  每日平均覆蓋 {panel.groupby('date')['code'].nunique().mean():.0f} 檔")
