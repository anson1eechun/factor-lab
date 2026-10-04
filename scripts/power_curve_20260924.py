#!/usr/bin/env python3
"""factor-lab crypto 橫截面流水線的檢定力曲線。

問題：在 T≈5.55 年、每日約 47 幣的宇宙裡，一個「真實效應為 X」的因子，
通過現行閘門的機率是多少？這不是假說檢定，不耗 ledger 配額。

做法：不假設常態。取 SIM-2026-09-14-001 / 09-23-001 的**真實**日淨報酬與每日 IC 序列
（保留 crypto 的厚尾與 5 日重疊持倉的自相關），去均值後加上指定的真實效應，
以 stationary block bootstrap（平均區塊 20 天）重抽出 T 年的樣本，計算閘門通過率。

  uv run --with "numpy>=2" --with pandas --with scipy --with pyarrow python scripts/power_curve_20260924.py
"""
import sys, os, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asd_20260914 as A
import compL_mom20_20260923 as C

REPS, BLOCK, NW = 2000, 20, 10
RNG = np.random.default_rng(20260924)
OUT = A.ER + "power_curve_20260924.json"


def boot_idx(n, T):
    """stationary bootstrap 的索引矩陣 (REPS, T)。"""
    start = RNG.integers(0, n, (REPS, T))
    new = RNG.random((REPS, T)) < 1.0 / BLOCK
    new[:, 0] = True
    pos = np.arange(T)[None, :]
    last = np.maximum.accumulate(np.where(new, pos, 0), axis=1)
    base = np.take_along_axis(start, last, axis=1)
    return (base + (pos - last)) % n


def nw_t_rows(X, L=NW):
    """逐列 Newey-West t（Bartlett），與 A.nw_t 同一公式的向量化版。"""
    n = X.shape[1]; mu = X.mean(1, keepdims=True); e = X - mu
    s = (e * e).sum(1) / n
    for l in range(1, L + 1):
        s += 2 * (1 - l / (L + 1)) * (e[:, l:] * e[:, :-l]).sum(1) / n
    return mu[:, 0] / np.sqrt(s / n)


def power(series, grid, to_mean, gate):
    x = np.asarray(series, float); x = x[~np.isnan(x)]
    z = x - x.mean(); T = len(x)
    idx = boot_idx(T, T); Z = z[idx]
    out = []
    for g in grid:
        X = Z + to_mean(g, x)
        out.append(float(gate(X).mean()))
    return T, out


def main():
    D = C.build()
    dfp, SIG, PX, CL, R, F = A.load_all()
    res = {"reps": REPS, "block_days": BLOCK, "nw_lag": NW, "series": {}}

    series = {}
    for name, sig in (("comp_L", D["compL"]), ("ASD", SIG.reindex(index=D["compL"].index, columns=D["compL"].columns))):
        bt = A.backtest(sig, D["R"], D["F"])
        ic = A.ic_series(sig, D["FWD"])
        g, n = bt["gross"], bt["net"]
        series[name] = (n, ic)
        res["series"][name] = {
            "T_years": len(n) / 365, "net_sharpe": float(n.mean() / n.std(ddof=1) * A.ANN),
            "gross_sharpe": float(g.mean() / g.std(ddof=1) * A.ANN),
            "ann_vol": float(n.std(ddof=1) * A.ANN), "turn_mean": float(bt["turn"].mean()),
            "cost_ann": float(bt["cost"].mean() * 365), "ic": float(ic.mean()),
            "ic_sd": float(ic.std(ddof=1)), "skew": float(n.skew()), "exkurt": float(n.kurt())}

    # 美元層閘門 G2(i)：淨 Sharpe >= 0.7 且 NW t >= 2.0
    sh_grid = [round(v, 2) for v in np.arange(0.0, 2.01, 0.1)]
    def sh_mean(S, x): return S * x.std(ddof=1) / A.ANN
    def g2(X): return ((X.mean(1) / X.std(1, ddof=1) * A.ANN) >= 0.7) & (nw_t_rows(X) >= 2.0)
    # 排序層閘門：|IC| > 0.02 且 NW t >= 2.0（skill 橫截面門檻）
    ic_grid = [round(v, 4) for v in np.arange(0.0, 0.0401, 0.0025)]
    def ic_mean(I, x): return I
    def rank_gate(X): return (X.mean(1) > 0.02) & (nw_t_rows(X) >= 2.0)
    def rank_t_only(X): return nw_t_rows(X) >= 2.0

    for name, (n, ic) in series.items():
        T, p_sh = power(n.values, sh_grid, sh_mean, g2)
        _, p_ic = power(ic.values, ic_grid, ic_mean, rank_gate)
        _, p_ict = power(ic.values, ic_grid, ic_mean, rank_t_only)
        res["series"][name].update({"dollar_power": dict(zip(map(str, sh_grid), p_sh)),
                                    "rank_power": dict(zip(map(str, ic_grid), p_ic)),
                                    "rank_t_only_power": dict(zip(map(str, ic_grid), p_ict))})
    A.dump(OUT, res)
    for name, r in res["series"].items():
        print(f"\n===== 以 {name} 的真實序列為底（T={r['T_years']:.2f} 年，淨報酬偏度 {r['skew']:+.2f}、超額峰度 {r['exkurt']:.1f}）=====")
        print(f"  觀測：IC {r['ic']:+.4f}  毛 Sharpe {r['gross_sharpe']:.3f}  淨 Sharpe {r['net_sharpe']:.3f}  "
              f"日換手 {r['turn_mean']:.3f}  年化成本 {r['cost_ann']:.1%}  年化波動 {r['ann_vol']:.1%}")
        print("  美元層 G2(i) 通過率 vs 真實淨 Sharpe：")
        print("   " + "  ".join(f"{k:>5s}" for k in list(r["dollar_power"])[::2]))
        print("   " + "  ".join(f"{v:5.0%}" for v in list(r["dollar_power"].values())[::2]))
        print("  排序層通過率 vs 真實 IC（|IC|>0.02 且 t>=2 ／ 只看 t>=2）：")
        print("   " + "  ".join(f"{k:>6s}" for k in list(r["rank_power"])[::2]))
        print("   " + "  ".join(f"{v:6.0%}" for v in list(r["rank_power"].values())[::2]))
        print("   " + "  ".join(f"{v:6.0%}" for v in list(r["rank_t_only_power"].values())[::2]))


if __name__ == "__main__":
    main()
