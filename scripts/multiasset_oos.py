#!/usr/bin/env python3
"""
多資產 × 多時框 正式 OOS 評估 harness。全真實。
資產:BTC, ETH, XAU(黃金), Oil(WTI)。時框:1d, 1w(由日線 resample)。
策略:對 signal 取 sign 方向 + 波動目標化(只去槓桿)→ 等權組合。
IS/OOS 以日期切分(預設 OOS = 2024-01-01 起)。對 5 門檻。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/multiasset_oos.py [core.signals.MODULE] [func]
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats

ER = "/home/anson/factor-lab/empirical_runs/"
ASSETS = {"BTC": ER+"btcusdt_1d_1500.pkl", "ETH": ER+"ethusdt_1d_1000.pkl",
          "XAU": ER+"xau_1d.pkl", "OIL": ER+"oil_1d.pkl"}
OOS_START = "2024-01-01"
TARGET_VOL_DAILY = 0.02   # ~ 38% 年化目標(crypto 友善);只去槓桿(cap=1)
COST_BPS = 10.0           # 每單位部位變動(每邊)的成本(bps);net = gross - turnover*cost


def to_weekly(df):
    d = df.copy()
    d.index = pd.to_datetime(d["timestamp"], unit="ms")
    w = pd.DataFrame({
        "open": d["open"].resample("W").first(), "high": d["high"].resample("W").max(),
        "low": d["low"].resample("W").min(), "close": d["close"].resample("W").last(),
        "volume": d["volume"].resample("W").sum()}).dropna()
    w["timestamp"] = (w.index.values.astype("datetime64[ms]").astype("int64"))
    return w.reset_index(drop=True)


def strat(df, fn, func, lookbacks, vol_window=20, per="d"):
    c = df["close"].astype(float).reset_index(drop=True)
    sig = pd.Series(np.asarray(fn(df, lookbacks=lookbacks, vol_window=vol_window), dtype="float64"))
    fwd = c.shift(-1) / c - 1
    pos = np.sign(sig)                                   # 趨勢方向
    rvol = c.pct_change().rolling(vol_window, min_periods=vol_window).std().shift(1)
    scale = (TARGET_VOL_DAILY / rvol).clip(upper=1.0)    # 只去槓桿
    posn = pos * scale
    turn = posn.diff().abs().fillna(posn.abs())          # 部位變動(含波動縮放)
    ret = (posn * fwd) - turn * (COST_BPS / 10000.0)     # net of cost
    dt = pd.to_datetime(df["timestamp"], unit="ms")
    return pd.DataFrame({"date": dt, "ret": ret, "sig": sig, "fwd": fwd})


def perf(ret, ppy):
    ret = ret.dropna()
    if len(ret) < 20 or not ret.std():
        return {}
    eq = (1+ret).cumprod(); nz = ret[ret != 0]
    return {"sharpe": round(float(ret.mean()/ret.std(ddof=1)*np.sqrt(ppy)), 3),
            "maxdd": round(float((eq/eq.cummax()-1).min()), 4),
            "t": round(float(nz.mean()/(nz.std(ddof=1)/np.sqrt(len(nz)))), 3) if len(nz) > 1 else None,
            "ann": round(float(ret.mean()*ppy), 4), "n": int(len(ret))}


def ic_ir(frames, win):
    """pooled rolling IC-IR:對每個資產算滾動 IC,合併後取 mean/std。"""
    allic = []
    for d in frames:
        s, f = d["sig"].reset_index(drop=True), d["fwd"].reset_index(drop=True)
        for i in range(win, len(s)):
            ss, ff = s.iloc[i-win:i], f.iloc[i-win:i]
            m = ss.notna() & ff.notna()
            if m.sum() >= 30:
                allic.append(stats.spearmanr(ss[m], ff[m]).correlation)
    ics = pd.Series(allic).dropna()
    return (round(float(ics.mean()), 4), round(float(ics.mean()/ics.std(ddof=1)), 4)) if len(ics) > 1 and ics.std() else (None, None)


def pooled_ic(frames):
    s = pd.concat([d["sig"] for d in frames]); f = pd.concat([d["fwd"] for d in frames])
    m = s.notna() & f.notna()
    return round(float(stats.spearmanr(s[m], f[m]).correlation), 4)


def run_tf(fn, func, label, dfs, ppy, lookbacks):
    frames = {a: strat(df, fn, func, lookbacks, per=label) for a, df in dfs.items()}
    # 組合:等權(依日期對齊,缺資產用其他)
    merged = None
    for a, d in frames.items():
        s = d.set_index("date")["ret"].rename(a)
        merged = s if merged is None else pd.concat([merged, s], axis=1)
    port = merged.mean(axis=1, skipna=True)
    port = pd.Series(port.values, index=merged.index)
    oos_mask = merged.index >= pd.Timestamp(OOS_START)
    out = {"per_asset": {a: perf(d["ret"], ppy) for a, d in frames.items()},
           "portfolio_full": perf(port, ppy),
           "portfolio_oos": perf(port[oos_mask], ppy)}
    out["pooled_ic"] = pooled_ic(list(frames.values()))
    out["ic_mean"], out["ic_ir"] = ic_ir(list(frames.values()), win=60 if label == "1d" else 26)
    return out


def main():
    module = sys.argv[1] if len(sys.argv) > 1 else "core.signals.F22_Time_Series_Momentum"
    func = sys.argv[2] if len(sys.argv) > 2 else "factor"
    fn = getattr(importlib.import_module(module), func)
    daily = {a: pd.read_pickle(p) for a, p in ASSETS.items()}
    res = {"module": module}
    res["1d"] = run_tf(fn, func, "1d", daily, 365, lookbacks=(20,60,120,250))
    weekly = {a: to_weekly(df) for a, df in daily.items()}
    res["1w"] = run_tf(fn, func, "1w", weekly, 52, lookbacks=(4,12,26,52))
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
