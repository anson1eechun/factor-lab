#!/usr/bin/env python3
"""SIM-016 衍生品定位策略 —— 樣本外延伸重跑。

背景:SIM-2026-06-09-016 用 BTC 2022-01→2026-06 的 deriv_btc.pkl 評估四個策略,全部 REJECT。
本次**不改任何參數、不改訊號程式、不做任何選擇**,只把資料期間往前延伸到 2020-09
(crypto-datalake 回填,與原 fetch_deriv_metrics.py 口徑一致、重疊期逐欄驗證相同),
用原辯論從未見過的期間檢驗當初的拒絕是否成立。

窗口:
  OOS_PRE   2020-09-01 → 2022-04-27   原辯論未見(價格檔起點之前)
  IS        2022-04-28 → 2026-06-05   原辯論評估期(用於確認重現)
  OOS_POST  2026-06-06 → 最新         原辯論之後新增
價格用 empirical_runs/universe_1d.pkl 的 BTC(與 btcusdt_1d_1500.pkl 在 1499/1500 日相同,
唯一差異是後者最末日為未收完的當日 bar),不足處以 Binance 現貨日線 REST 補齊並驗證接縫。

跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/deriv_oos_rerun.py
"""
import importlib, json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from core.backtest import evaluate_positions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "empirical_runs", "deriv_btc_ext.pkl")
ANN = np.sqrt(365)
FUNCS = ["contra_global_ls", "follow_top_pos", "smart_dumb_div", "oi_breakout"]
# SIM-2026-06-09-016 報告的原始結果(10bps, lag=1),用於確認重現
ORIG = {"contra_global_ls": 0.735, "follow_top_pos": -0.657,
        "smart_dumb_div": 0.059, "oi_breakout": -0.065}
WINDOWS = [("OOS_PRE", "2020-09-01", "2022-04-27"),
           ("IS", "2022-04-28", "2026-06-05"),
           ("OOS_POST", "2026-06-06", "2099-01-01"),
           ("FULL", "2020-09-01", "2099-01-01")]


def btc_price():
    """BTC 日收盤:以 universe_1d 為主,尾端不足處用 Binance 現貨 REST 補並驗證接縫。"""
    u = pd.read_pickle(os.path.join(ROOT, "empirical_runs", "universe_1d.pkl"))["BTC"]
    s = pd.Series(u["close"].astype(float).values,
                  index=pd.to_datetime(u["timestamp"], unit="ms").dt.floor("D")).sort_index()
    s = s.iloc[:-1]        # 末根是抓取當下未收完的 bar（btcusdt_1d_1500.pkl 亦同），丟棄
    url = ("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=200")
    try:
        raw = json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "factor-lab"}), timeout=30))
        r = pd.Series([float(k[4]) for k in raw],
                      index=pd.to_datetime([k[0] for k in raw], unit="ms").floor("D"))
        r = r[r.index < pd.Timestamp.now("UTC").normalize().tz_localize(None)]  # 丟未收完當日
        ov = s.index.intersection(r.index)
        if len(ov) >= 20:
            d = float(((s[ov] - r[ov]).abs() / s[ov]).max())
            print(f"[價格] 接縫驗證 {len(ov)} 日重疊,最大相對差 {d:.2e}"
                  f"{'  ✓' if d < 1e-6 else '  ✗ 來源不一致,只用 universe_1d'}")
            if d >= 1e-6:
                return s
        s = pd.concat([s, r[~r.index.isin(s.index)]]).sort_index()
    except Exception as e:
        print(f"[價格] REST 補齊失敗({e}),只用 universe_1d")
    return s


def metrics(pos, px, lo, hi, cost_bps=10.0, lag=1):
    lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
    p, q = pos[(pos.index >= lo) & (pos.index <= hi)], px[(px.index >= lo) & (px.index <= hi)]
    if len(p) < 60 or len(q) < 60:
        return None
    m = evaluate_positions(p, q, cost_bps=cost_bps, lag=lag)
    net = m["net_returns"]
    ex5 = net[net < net.quantile(0.95)]
    return {"days": int((m["position"].abs() > 0).sum()),
            "net_sharpe": m["net_sharpe"], "t_stat": m["t_stat"],
            "ex_top5": round(float(ex5.mean() / ex5.std(ddof=1) * ANN), 3)
                       if len(ex5) > 1 and ex5.std(ddof=1) else 0.0,
            "ann_return": m["ann_return"], "max_dd": m["max_drawdown"],
            "exposure": m["exposure"]}


def main():
    if not os.path.exists(EXT):
        sys.exit(f"缺 {EXT},先跑 crypto-datalake/tools/export_to_factorlab.py")
    mod = importlib.import_module("core.signals.FSIM_Deriv_Positioning")
    mod.P = EXT                                     # 只換資料來源,程式與參數原封不動
    d = pd.read_pickle(EXT)
    px = btc_price()
    print(f"[資料] deriv {len(d)} 日 {d.date.min().date()}→{d.date.max().date()} | "
          f"price {len(px)} 日 {px.index.min().date()}→{px.index.max().date()}\n")

    rows = []
    for fn in FUNCS:
        pos = getattr(mod, fn)()
        for wname, lo, hi in WINDOWS:
            m = metrics(pos, px, lo, hi)
            if m:
                rows.append({"strategy": fn, "window": wname, **m})

    R = pd.DataFrame(rows)
    print(f"{'策略':18s} {'窗口':9s} {'日數':>5s} {'netSharpe':>10s} {'t':>7s} "
          f"{'剔5%':>7s} {'年化':>8s} {'MaxDD':>8s}")
    for fn in FUNCS:
        for _, r in R[R.strategy == fn].iterrows():
            print(f"{r.strategy:18s} {r.window:9s} {r.days:5d} {r.net_sharpe:10.3f} "
                  f"{r.t_stat:7.2f} {r.ex_top5:7.2f} {r.ann_return:8.3f} {r.max_dd:8.3f}")
        print()

    print("重現檢查(IS 窗口 vs SIM-016 原報告):")
    for fn in FUNCS:
        w = R[(R.strategy == fn) & (R.window == "IS")]
        if len(w):
            got, want = float(w.net_sharpe.iloc[0]), ORIG[fn]
            print(f"  {fn:18s} 本次 {got:+.3f}  原報告 {want:+.3f}  差 {got-want:+.3f}")

    out = os.path.join(ROOT, "empirical_runs", "SIM-016_oos_extension.json")
    R.to_json(out, orient="records", indent=1)
    print(f"\n結果 → {out}")


if __name__ == "__main__":
    main()
