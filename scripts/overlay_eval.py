#!/usr/bin/env python3
"""風控 overlay 評估(long-only 減碼)。基準=buy&hold BTC;風險訊號示警時降曝險 w∈[wmin,1],絕不放空。
比較 overlay vs buy&hold:CAGR/Sharpe/MaxDD/Calmar + 是否非單一事件(剔最大跌5%日後是否仍贏)。
風險訊號函數回傳 date-indexed 原始風險分數(越高越危險)。harness lag 後 z 化、套映射、扣成本。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/overlay_eval.py core.signals.<MOD> <riskfunc> [cost_bps] [lag]"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
ANN = np.sqrt(365)


def perf(r):
    r = r.dropna()
    if not len(r) or not r.std():
        return {}
    eq = (1 + r).cumprod(); dd = eq / eq.cummax() - 1
    cagr = float(eq.iloc[-1] ** (365 / len(r)) - 1)
    sh = float(r.mean() / r.std(ddof=1) * ANN)
    mdd = float(dd.min())
    return {"CAGR": round(cagr, 4), "Sharpe": round(sh, 3), "MaxDD": round(mdd, 4),
            "Calmar": round(cagr / abs(mdd), 3) if mdd else None}


def main():
    module = sys.argv[1]; rf = sys.argv[2]
    cost_bps = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    lag = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    b = pd.read_pickle(ER + "btcusdt_1d_1500.pkl")
    b["date"] = pd.to_datetime(b["timestamp"], unit="ms").dt.floor("D")
    px = b.set_index("date")["close"].astype(float).sort_index()
    r = px.pct_change()
    risk = getattr(importlib.import_module(module), rf)()
    z = ((risk - risk.rolling(60).mean()) / risk.rolling(60).std()).reindex(px.index).ffill().shift(lag)

    bh = perf(r)
    res = {"module": module, "risk": rf, "cost_bps": cost_bps, "lag": lag, "buy_hold": bh, "overlays": {}}
    # 多種映射:線性減碼 + 門檻關閉
    grids = {
        "lin_a1_f0.3": lambda z: (1 - 1.0 * z.clip(lower=0)).clip(0.3, 1),
        "lin_a0.5_f0.5": lambda z: (1 - 0.5 * z.clip(lower=0)).clip(0.5, 1),
        "thr1.0_to0": lambda z: pd.Series(np.where(z > 1.0, 0.0, 1.0), index=z.index),
        "thr1.5_to0.5": lambda z: pd.Series(np.where(z > 1.5, 0.5, 1.0), index=z.index),
    }
    for name, fn in grids.items():
        w = fn(z).fillna(1.0).clip(0, 1)
        turn = w.diff().abs().fillna(0)
        sr = (w * r - turn * cost_bps / 10000.0)
        p = perf(sr)
        # 非單一事件檢驗:剔除 buy&hold 最差5%日後,overlay 還贏多少超額
        worst = r < r.quantile(0.05)
        exret_all = float((sr - r).sum())
        exret_ex_worst = float((sr - r)[~worst].sum())
        p["avg_exposure"] = round(float(w.mean()), 3)
        p["excess_total"] = round(exret_all, 4)
        p["excess_ex_worst5pct"] = round(exret_ex_worst, 4)   # 若≈0 或負 → 全靠避開崩盤日
        res["overlays"][name] = p
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
