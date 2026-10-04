#!/usr/bin/env python3
"""EQ Phase0:Tushare 抓 CSI300 个股资金流(moneyflow)+ 收盘,建多日面板。
token 從環境變數 TUSHARE_TOKEN 讀(不寫死)。api.tushare.pro 此機可達。
用法:
  export TUSHARE_TOKEN=你的token
  uv run --with akshare --with pandas --with pyarrow --with requests python scripts/fetch_ashare_tushare.py [起始YYYYMMDD]
moneyflow 需 2000 積分;不足會在自測時明確報錯。"""
import os, sys, time, datetime
import pandas as pd, requests

TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()
if not TOKEN:
    _tf = os.path.expanduser("~/.tushare_token")          # 退路:從私有檔讀(不必貼進對話)
    if os.path.isfile(_tf):
        TOKEN = open(_tf).read().strip()
OUT = "/home/anson/factor-lab/data/ashare/moneyflow_panel.parquet"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
START = sys.argv[1] if len(sys.argv) > 1 else (datetime.date.today() - datetime.timedelta(days=400)).strftime("%Y%m%d")
END = datetime.date.today().strftime("%Y%m%d")
API = "https://api.tushare.pro"

if not TOKEN:
    print("✗ 未設 TUSHARE_TOKEN。請先 `export TUSHARE_TOKEN=你的token`"); raise SystemExit(1)


def call(api_name, params, fields=""):
    r = requests.post(API, json={"api_name": api_name, "token": TOKEN, "params": params, "fields": fields}, timeout=30)
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(j.get("msg", "unknown"))
    d = j["data"]
    return pd.DataFrame(d["items"], columns=d["fields"])


# 0) 自測 token + 積分
try:
    call("moneyflow", {"ts_code": "600519.SH", "start_date": START, "end_date": END},
         "trade_date,net_mf_amount")
    print("✓ token/積分 OK(moneyflow 可調)")
except Exception as e:
    print(f"✗ moneyflow 調用失敗:{e}")
    print("  若為積分不足 → 改用北向资金:見檔末註解的 moneyflow_hsgt 退路,或先充積分。")
    raise SystemExit(1)

# 1) CSI300 成分(akshare csindex,此機可達)
import akshare as ak
cons = ak.index_stock_cons_csindex(symbol="000300")
codes = cons["成分券代码"].astype(str).str.zfill(6).tolist()
ts_codes = [c + (".SH" if c[0] == "6" else ".SZ") for c in codes]
print(f"CSI300 {len(ts_codes)} 檔,期間 {START}→{END}")

# 2) 逐檔抓 moneyflow + daily(close),合併
rows, ok, fail, ferr = [], 0, 0, None
for i, tc in enumerate(ts_codes):
    try:
        mf = call("moneyflow", {"ts_code": tc, "start_date": START, "end_date": END},
                  "trade_date,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount")
        px = call("daily", {"ts_code": tc, "start_date": START, "end_date": END}, "trade_date,close")
        d = mf.merge(px, on="trade_date", how="inner")
        for col in d.columns:
            if col != "trade_date":
                d[col] = pd.to_numeric(d[col], errors="coerce")
        d["main_net"] = d["net_mf_amount"]                                         # 主力净流入(万元)
        d["lg_net"] = (d["buy_lg_amount"] + d["buy_elg_amount"]) - (d["sell_lg_amount"] + d["sell_elg_amount"])  # 大+超大单净
        d["code"] = tc
        rows.append(d[["trade_date", "code", "close", "main_net", "lg_net"]])
        ok += 1
    except Exception as e:
        fail += 1
        if ferr is None:
            ferr = str(e)[:120]
    if (i + 1) % 50 == 0:
        print(f"  ...{i+1}/{len(ts_codes)}  ok{ok} fail{fail}")
    time.sleep(0.13)                                                              # 控速(Tushare 每分鐘上限)

if not rows:
    print(f"✗ 全失敗,首錯:{ferr}"); raise SystemExit(1)
panel = pd.concat(rows, ignore_index=True)
panel["trade_date"] = pd.to_datetime(panel["trade_date"])
panel = panel.sort_values(["code", "trade_date"]).reset_index(drop=True)
panel.to_parquet(OUT)
print(f"\n存 {OUT}")
print(f"  {ok} 檔 / {panel['trade_date'].min().date()}→{panel['trade_date'].max().date()} / {len(panel)} 列")
print(f"  每日平均覆蓋 {panel.groupby('trade_date')['code'].nunique().mean():.0f} 檔")
if fail:
    print(f"  (跳過 {fail} 檔,首錯:{ferr})")

# ── 退路:積分不足時改北向资金(門檻低)──
# hsgt = call("moneyflow_hsgt", {"start_date": START, "end_date": END},
#             "trade_date,north_money")   # 北向净流入(市場層級);個股需 hk_hold
