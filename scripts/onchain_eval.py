#!/usr/bin/env python3
"""鏈上時序策略 harness(單資產 BTC 日線)。

回測核心（對齊價格 / lag 杜前視 / 扣換手成本 / 年化 Sharpe）**委派給 core.backtest.evaluate_positions
（唯一真相）**；本檔只在其上加報表欄位：gross_bps/打平、剔最高 5% 日壓測、年度 regime。
strategy() -> position Series(date-indexed, ∈[-1,1])。鏈上資料有回報延遲 → 預設 lag=1(用前一日訊號)。

跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/onchain_eval.py core.signals.<MOD> [func] [cost_bps] [lag]
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from core.backtest import load_btc_price, evaluate_positions

ANN = np.sqrt(365)


def _sharpe(r):
    return round(float(r.mean() / r.std(ddof=1) * ANN), 3) if len(r) > 1 and r.std(ddof=1) else 0.0


def main():
    module = sys.argv[1]
    func = sys.argv[2] if len(sys.argv) > 2 else "strategy"
    cost_bps = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    lag = int(sys.argv[4]) if len(sys.argv) > 4 else 1

    px = load_btc_price()
    fwd = px.shift(-1) / px - 1
    pos = getattr(importlib.import_module(module), func)()
    m = evaluate_positions(pos, px, cost_bps=cost_bps, lag=lag)  # ← 唯一回測核心
    apos, net = m["position"], m["net_returns"]
    turn = float(apos.diff().abs().fillna(apos.abs()).mean())
    gross_bps = float((apos * fwd).dropna().mean() * 1e4)
    out = {
        "module": module, "func": func, "cost_bps": cost_bps, "lag": lag,
        "days": int((apos.abs() > 0).sum()),
        "net_sharpe": m["net_sharpe"], "ann_return": m["ann_return"],
        "max_drawdown": m["max_drawdown"], "t_stat": m["t_stat"],
        "turnover_per_day": m["turnover_per_day"], "gross_bps_per_day": round(gross_bps, 3),
        "breakeven_bps": round(gross_bps / turn, 3) if turn else None,
        "exposure": m["exposure"],
        "sharpe_ex_top5pct": _sharpe(net[net < net.quantile(0.95)]),
        "sharpe_by_year": {str(y): round(float(g.mean() / g.std(ddof=1) * ANN), 2)
                           for y, g in net.groupby(net.index.year) if g.std(ddof=1) and len(g) > 30},
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
