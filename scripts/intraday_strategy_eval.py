#!/usr/bin/env python3
"""
日內規則型策略回測 harness(單資產 intraday)。全真實,扣交易成本。
strategy(ohlcv_df, **p) -> position Series ∈ [-1,1](bar t 的部位,持有到 t+1;無前視自理)。
跑: uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/intraday_strategy_eval.py <module> [func] [asset] [tf] [cost_bps]
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
PPY = {"5m": 105120, "15m": 35040, "30m": 17520, "45m": 11680, "1h": 8760, "3h": 2920, "4h": 2190}


def metrics(net, pos, ppy):
    net = net.dropna()
    if not len(net) or not net.std():
        return {}
    eq = (1 + net).cumprod(); dd = eq / eq.cummax() - 1
    ann = np.sqrt(ppy)
    trades = int((pos.diff().abs() > 1e-9).sum())
    active = net[pos.reindex(net.index).abs() > 1e-9]
    return {
        "net_sharpe": round(float(net.mean() / net.std(ddof=1) * ann), 3),
        "ann_return": round(float(net.mean() * ppy), 4),
        "max_drawdown": round(float(dd.min()), 4),
        "t_stat": round(float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))), 3),
        "n_trades": trades, "exposure": round(float((pos.abs() > 1e-9).mean()), 3),
        "win_rate": round(float((active > 0).mean()), 4) if len(active) else None,
        # 壓測:剔除報酬最高 5% bar
        "sharpe_ex_top5pct": round(float((lambda r: r.mean()/r.std(ddof=1)*ann if r.std() else 0)(net[net < net.quantile(0.95)])), 3),
    }


def main():
    a = sys.argv
    module = a[1]; func = a[2] if len(a) > 2 else "strategy"
    asset = a[3] if len(a) > 3 else "btc"
    tf = a[4] if len(a) > 4 else "1h"
    cost_bps = float(a[5]) if len(a) > 5 else 10.0
    p = f"{ER}{asset.lower()}_{tf}.pkl"
    if not os.path.isfile(p):
        print(json.dumps({"error": f"找不到 {p}"})); return
    df = pd.read_pickle(p)
    pos = pd.Series(np.asarray(getattr(importlib.import_module(module), func)(df), dtype="float64")).reset_index(drop=True)
    c = df["close"].astype(float).reset_index(drop=True)
    fwd = c.shift(-1) / c - 1
    gross = (pos * fwd).fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    net = (gross - turn * cost_bps / 10000.0).fillna(0.0)
    out = {"module": module, "asset": asset, "tf": tf, "cost_bps": cost_bps, "bars": int(len(df)),
           **metrics(net, pos, PPY.get(tf, 8760))}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
