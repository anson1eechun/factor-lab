#!/usr/bin/env python3
"""smc_sweep.py — 把現有 SMC (FSMC) 信號丟進本 session 的誠實引擎。

戳破舊 15m harness 的三宗罪：零成本 + ~200 組挑最好 + 無 OOS。這裡對 FVG/LiqSweep/OrderBlock/POC
（BTC 日線、anti-lookahead）跑：grid → rolling-WF(OOS) → DSR/PBO → **成本 0 vs 10bps 對照** → 最佳做置換 null。

跑: uv run --with "numpy>=2" --with pandas python scripts/smc_sweep.py
"""
import sys, os, json, math
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from core.backtest import evaluate_positions, evaluate_strategy
from core.signals.FSMC_FVG import factor as fvg
from core.signals.FSMC_LiqSweep import factor as liqsweep
from core.signals.FSMC_OrderBlock import factor as orderblock
from core.signals.FSMC_POC import factor as poc

ROOT = Path(__file__).resolve().parent.parent
ANN = math.sqrt(365)

SIGNALS = {
    "FVG":        (fvg,        {"fvg_lookback": [10, 20, 40],   "hold": [1, 3, 5]}),
    "LiqSweep":   (liqsweep,   {"pivot_window": [3, 5, 10],     "hold": [1, 3, 5]}),
    "OrderBlock": (orderblock, {"ob_lookback": [20, 30, 50],    "hold": [1, 3, 5]}),
    "POC":        (poc,        {"profile_window": [10, 20, 40], "hold": [1, 3, 5]}),
}


def load_ohlc():
    b = pd.read_pickle(ROOT / "empirical_runs" / "btcusdt_1d_1500.pkl")
    b["date"] = pd.to_datetime(b["timestamp"], unit="ms").dt.floor("D")
    return b.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float).sort_index()


def held(sig, hold):
    """事件信號(±N/0/NaN) → 持倉 ∈[-1,1]：事件日取 sign，往後持有 hold 日。"""
    s = np.sign(sig)
    s = s.where(s.abs() > 0)            # ±1 at events, else NaN
    return s.ffill(limit=int(hold)).fillna(0.0).clip(-1.0, 1.0)


def _mp(fn, df):
    def make_pos(**p):
        p = dict(p)
        hold = p.pop("hold")
        return held(fn(df, **{k: int(v) for k, v in p.items()}), hold)
    return make_pos


def _robust(cv, dsr, pbo, plat):
    return (cv or 0) > 0.3 and (pbo is None or pbo < 0.5) and (dsr or 0) > 0.9 and (plat or 0) >= 0.4


def main():
    df = load_ohlc()
    px = df["close"]
    fwd = px.shift(-1) / px - 1
    rows = []
    for name, (fn, grid) in SIGNALS.items():
        mp = _mp(fn, df)
        r = evaluate_strategy(mp, grid, px)          # 預設 10bps 成本
        best = r["best"]
        cv = r["wf"].get("cv_sharpe")
        dsr = (r["dsr"] or {}).get("dsr")
        s0 = evaluate_positions(mp(**best), px, cost_bps=0)["net_sharpe"]
        s10 = evaluate_positions(mp(**best), px, cost_bps=10)["net_sharpe"]
        rows.append({"name": name, "best": best, "cv": cv, "dsr": dsr, "pbo": r["pbo"],
                     "plat": r["opt"].get("plateau_score"), "nocost": s0, "cost10": s10,
                     "robust": _robust(cv, dsr, r["pbo"], r["opt"].get("plateau_score")), "mp": mp})
    rows.sort(key=lambda x: -(x["cv"] if x["cv"] is not None else -9))

    # 置換 null（最佳信號的部位對次日報酬環移）
    br = rows[0]
    ap = evaluate_positions(br["mp"](**br["best"]), px, cost_bps=10)["position"]

    def sh(p):
        net = (p * fwd - p.diff().abs().fillna(p.abs()) * 10 / 1e4).fillna(0.0).dropna()
        return float(net.mean() / net.std(ddof=1) * ANN) if net.std(ddof=1) else 0.0

    obs = sh(ap)
    rng = np.random.default_rng(42)
    v = ap.values
    null = np.array([sh(pd.Series(np.roll(v, int(k)), index=ap.index)) for k in rng.integers(30, len(v) - 30, 300)])
    pval = float((null >= obs).mean())

    # ── 報告 ──
    print("# SMC (FSMC) 信號 × 誠實引擎（BTC 日線，10bps 成本，OOS）\n")
    print(f"{'signal':11s} best              cv    DSR    PBO  plat  robust | 無成本→10bps 對照")
    print("-" * 84)
    for r in rows:
        gap = (r["nocost"] or 0) - (r["cost10"] or 0)
        print(f"{r['name']:11s} {str(r['best']):17s} "
              f"{(r['cv'] if r['cv'] is not None else 0):+5.2f} "
              f"{str(r['dsr'] if r['dsr'] is not None else '—'):>5} "
              f"{str(r['pbo'] if r['pbo'] is not None else '—'):>4} "
              f"{str(r['plat']):>4}  {'✓' if r['robust'] else ' '}    | "
              f"{(r['nocost'] or 0):+.2f} → {(r['cost10'] or 0):+.2f}  (成本吃掉 {gap:.2f})")

    n = len(rows)
    robust_n = sum(1 for r in rows if r["robust"])
    exp_false = round(n * 0.10, 1)
    avg_gap = np.mean([(r["nocost"] or 0) - (r["cost10"] or 0) for r in rows])
    print("\n## 誠實判讀")
    print(f"- 4 信號 × 9 組參數 = 36 configs；DSR 已對每信號 9 試驗校正，跨 4 信號選最佳是額外搜尋。")
    print(f"- **成本的真相**：平均「無成本→10bps」掉了 {avg_gap:.2f} Sharpe —— 舊 15m harness 零成本，"
          f"這段全是假象。")
    print(f"- **robust（cv>0.3 且 DSR>0.9 且 PBO<0.5 且 plat≥0.4）：{robust_n}/{n}**（運氣預期 ≈ {exp_false}）")
    print(f"- 最佳({br['name']}) 置換 null：observed {obs:+.2f} vs null 中位 {np.median(null):+.2f}，"
          f"p={pval:.3f} → {'timing 特別' if pval < 0.05 else 'timing 不特別（≈隨機相位）'}")
    verdict = ("與運氣同量級 + 置換 null 未過 → **SMC 日線信號沒有可宣稱的真 edge**；舊報告的漂亮數字主要來自"
               "「零成本 + 挑最好 + 無 OOS」。" if robust_n <= exp_false + 1 or pval >= 0.05 else
               f"{br['name']} 撐住了，值得比照 base coinbase 做 anchored holdout + forward 二驗。")
    print(f"  → {verdict}")

    out = ROOT / "reports" / "smc_sweep.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": dt.datetime.now().isoformat(timespec="seconds"),
                               "rows": [{k: v for k, v in r.items() if k != "mp"} for r in rows],
                               "permutation": {"signal": br["name"], "observed": obs,
                                               "null_median": float(np.median(null)), "p_value": pval},
                               "robust_n": robust_n, "avg_cost_gap": float(avg_gap)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
