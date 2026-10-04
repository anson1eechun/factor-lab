#!/usr/bin/env python3
"""
backtest_timeseries.py — 單因子回測,輸出完整時序 + KPI + OHLC + 逐筆交易(JSON),
供 Balaena 控制台 Backtest 面板。LS 時序 quintile,含交易成本/滑價(net of cost)。

跑: uv run --with "numpy>=2" --with pandas python scripts/backtest_timeseries.py \
        core.signals.<MODULE> [func] [cost_bps] [asset] [timeframe]
  cost_bps 每邊;asset=BTC|ETH|XAU|OIL;timeframe=1d|1w(1w 由日線 resample)。
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
ASSETS = {"BTC": ER+"btcusdt_1d_1500.pkl", "ETH": ER+"ethusdt_1d_1000.pkl",
          "XAU": ER+"xau_1d.pkl", "OIL": ER+"oil_1d.pkl"}
INTRADAY = {"5m", "15m", "30m", "45m", "1h", "3h", "4h"}
PPY = {"5m": 105120, "15m": 35040, "30m": 17520, "45m": 11680, "1h": 8760,
       "3h": 2920, "4h": 2190, "1d": 365, "1w": 52}


def to_weekly(df):
    d = df.copy(); d.index = pd.to_datetime(d["timestamp"], unit="ms")
    w = pd.DataFrame({"open": d["open"].resample("W").first(), "high": d["high"].resample("W").max(),
                      "low": d["low"].resample("W").min(), "close": d["close"].resample("W").last(),
                      "volume": d["volume"].resample("W").sum()}).dropna()
    w["timestamp"] = w.index.values.astype("datetime64[ms]").astype("int64")
    return w.reset_index(drop=True)


def stats_block(ret, pos, ppy):
    eq = (1+ret).cumprod(); dd = eq/eq.cummax()-1; nz = ret[pos != 0]
    wins = nz[nz > 0]
    return {"equity": [round(float(x), 5) for x in eq.tolist()],
            "drawdown": [round(float(x), 5) for x in dd.tolist()],
            "total_return": round(float(eq.iloc[-1]-1), 4), "max_drawdown": round(float(dd.min()), 4),
            "sharpe": round(float(ret.mean()/ret.std(ddof=1)*np.sqrt(ppy)), 3) if ret.std() else None,
            "ann_return": round(float(ret.mean()*ppy), 4),
            "win_rate": round(float(len(wins)/max(len(nz), 1)), 4)}


def extract_trades(pos, close, dates, cost_bps):
    """把連續同向部位視為一筆交易(進場=close[i],出場=close[run結束+1])。"""
    pos = pos.values; n = len(pos); rt = 2*cost_bps/10000.0; trades = []; cum = 1.0; i = 0
    while i < n:
        if pos[i] == 0 or np.isnan(pos[i]):
            i += 1; continue
        d = pos[i]; j = i
        while j+1 < n and pos[j+1] == d:
            j += 1
        ex = min(j+1, n-1)
        ep, xp = float(close[i]), float(close[ex])
        gross = (xp/ep - 1) * d
        net = gross - rt
        cum *= (1+net)
        trades.append({"entry": dates[i], "exit": dates[ex], "dir": int(d),
                       "entry_px": round(ep, 2), "exit_px": round(xp, 2),
                       "bars": int(ex-i), "ret": round(float(net), 4), "cum": round(float(cum-1), 4)})
        i = j+1
    return trades


def main():
    a = sys.argv
    module = a[1]; func = a[2] if len(a) > 2 else "factor"
    cost_bps = float(a[3]) if len(a) > 3 else 10.0
    asset = a[4] if len(a) > 4 else "BTC"
    tf = a[5] if len(a) > 5 else "1d"
    if not module.startswith("core.signals."):
        print(json.dumps({"error": "module must be core.signals.*"})); return
    if asset not in ASSETS:
        print(json.dumps({"error": "unknown asset"})); return
    if tf in INTRADAY:
        if asset not in ("BTC", "ETH"):
            print(json.dumps({"error": f"{asset} 無 intraday 資料(僅 BTC/ETH 有 5m–4h)"})); return
        p = f"{ER}{asset.lower()}_{tf}.pkl"
        if not os.path.isfile(p):
            print(json.dumps({"error": f"找不到 {p}(先跑 fetch_intraday.py)"})); return
        df = pd.read_pickle(p)
    else:
        df = pd.read_pickle(ASSETS[asset])
        if tf == "1w":
            df = to_weekly(df)
    ppy = PPY.get(tf, 365)
    c = df["close"].astype(float).reset_index(drop=True)
    fmt = "%Y-%m-%d" if tf in ("1d", "1w") else "%Y-%m-%d %H:%M"
    dt = pd.to_datetime(df["timestamp"], unit="ms"); dates = dt.dt.strftime(fmt).tolist()
    sig = pd.Series(np.asarray(getattr(importlib.import_module(module), func)(df), dtype="float64"))
    fwd = c.shift(-1)/c - 1
    qwin = 252 if tf == "1d" else (52 if tf == "1w" else min(500, max(60, len(df)//5)))
    hi = sig.rolling(qwin, min_periods=qwin//2).quantile(0.8)
    lo = sig.rolling(qwin, min_periods=qwin//2).quantile(0.2)
    pos = pd.Series(0.0, index=sig.index); pos[sig >= hi] = 1.0; pos[sig <= lo] = -1.0
    gross = (pos*fwd).fillna(0.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    net = (gross - turnover*(cost_bps/10000.0)).fillna(0.0)
    g, nn = stats_block(gross, pos, ppy), stats_block(net, pos, ppy)
    years = max(len(df)/ppy, 1e-9)
    trades = extract_trades(pos, c.values, dates, cost_bps)
    mret = net.groupby([dt.dt.year, dt.dt.month]).apply(lambda x: (1+x).prod()-1)
    monthly = [{"year": int(y), "month": int(m), "ret": round(float(v), 4)} for (y, m), v in mret.items()]
    out = {"module": module, "asset": asset, "timeframe": tf, "dates": dates,
           "open": [round(float(x), 2) for x in df["open"].tolist()],
           "high": [round(float(x), 2) for x in df["high"].tolist()],
           "low": [round(float(x), 2) for x in df["low"].tolist()],
           "close": [round(float(x), 2) for x in c.tolist()],
           "equity": nn["equity"], "equity_gross": g["equity"], "drawdown": nn["drawdown"],
           "pnl": [round(float(x), 6) for x in net.tolist()],
           "monthly": monthly, "trades": trades,
           "kpis": {"total_return": nn["total_return"], "total_return_gross": g["total_return"],
                    "max_drawdown": nn["max_drawdown"], "sharpe": nn["sharpe"], "sharpe_gross": g["sharpe"],
                    "ann_return": nn["ann_return"], "win_rate": nn["win_rate"],
                    "ann_turnover": round(float(turnover.sum()/years), 1),
                    "cost_drag_annual": round(float(g["ann_return"]-nn["ann_return"]), 4),
                    "cost_bps": cost_bps, "n_trades": len(trades),
                    "trading_periods": int((pos != 0).sum()), "total_bars": int(len(df))}}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
