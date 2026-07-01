#!/usr/bin/env python3
"""smc_sweep_15m.py — 影片真正教的 intraday SMC 的公平審判（BTC 15m）。

用 15m-tuned 的 FVG / LiqSweep / ORB（＋高流動 session 遮罩）跑本 session 的誠實引擎
（evaluate_strategy，ppy=365*96 正確年化、扣成本、rolling-WF OOS、DSR/PBO、置換 null），
並對照成本 0 vs 10bps —— 這正是舊 combo_backtest_15m 的 bt() 完全忽略、把數字灌水的地方。

跑: uv run --with "numpy>=2" --with pandas python scripts/smc_sweep_15m.py
"""
import sys, os, json, math
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from core.backtest import evaluate_positions, evaluate_strategy

ROOT = Path(__file__).resolve().parent.parent
PPY = 365 * 96                       # 15m bars per year
ANN = math.sqrt(PPY)
DF = None
HILIQ = None
_CACHE: dict = {}


# ── 15m 信號（自 combo_backtest_15m.py，回 ±1/0/NaN 事件序列）──
def fvg_signal(df, lb=80, gap=0.2):
    O = df["open"].values; H = df["high"].values; L = df["low"].values; C = df["close"].values
    n = len(df); sig = np.zeros(n); zones = []
    for i in range(2, n):
        g = C[i] * gap / 100.0
        if L[i - 2] - H[i] > g: zones.append((i, H[i], L[i - 2], +1))
        if L[i] - H[i - 2] > g: zones.append((i, H[i - 2], L[i], -1))
        zones = [z for z in zones if i - z[0] <= lb]
        bull = bear = 0; unmit = []
        for ii, bt, tp, d in zones:
            if d == +1:
                if L[i] <= tp and L[i] >= bt: bear -= 1
                else: unmit.append((ii, bt, tp, d))
            else:
                if H[i] >= bt and H[i] <= tp: bull += 1
                else: unmit.append((ii, bt, tp, d))
        zones = unmit; net = bull + bear
        if net != 0: sig[i] = np.sign(net)
    sig[:lb + 2] = np.nan; sig[-1] = 0
    return pd.Series(sig, index=df.index).shift(1)


def ls_signal(df, slb=80, conf=4):
    H = df["high"].values; L = df["low"].values; C = df["close"].values; n = len(df)
    sig = np.zeros(n); sh = []; sl = []
    for i in range(slb + 2, n - conf):
        ws = i - slb; we = i; mid = i - slb // 2
        if H[mid] >= np.max(H[ws:we + 1]) and mid > ws + 8 and mid < we - 8: sh.append((mid, H[mid]))
        if L[mid] <= np.min(L[ws:we + 1]) and mid > ws + 8 and mid < we - 8: sl.append((mid, L[mid]))
        co = i - 3 * slb; sh = [(j, p) for j, p in sh if j > co]; sl = [(j, p) for j, p in sl if j > co]
        for j, p in sh:
            if H[i] > p and C[i + conf] < p: sig[i + conf] = -1.0; sh = [(k, q) for k, q in sh if k != j]; break
        for j, p in sl:
            if L[i] < p and C[i + conf] > p: sig[i + conf] = +1.0; sl = [(k, q) for k, q in sl if k != j]; break
    sig[:slb + 2 + conf] = np.nan; sig[-1] = 0
    return pd.Series(sig, index=df.index).shift(1)


def orb_signal(df, orb_bars=4):
    H = df["high"].values; L = df["low"].values; C = df["close"].values
    hrs = df.index.hour.values; n = len(df); sig = np.zeros(n); starts = []
    for i in range(1, n):
        if (hrs[i - 1] == 23 and hrs[i] == 0) or (hrs[i - 1] == 6 and hrs[i] == 7) or (hrs[i - 1] == 11 and hrs[i] == 12):
            starts.append(i)
    starts.append(n)
    for k in range(len(starts) - 1):
        s0 = starts[k]; s1 = starts[k + 1]; oe = min(s0 + orb_bars, s1)
        if oe - s0 < orb_bars: continue
        rh = np.max(H[s0:oe]); rl = np.min(L[s0:oe])
        for j in range(oe, s1):
            if C[j] > rh: sig[j] = +1.0
            elif C[j] < rl: sig[j] = -1.0
    sig[:orb_bars + 1] = np.nan; sig[-1] = 0
    return pd.Series(sig, index=df.index).shift(1)


def held(sig, hold):
    s = np.sign(sig); s = s.where(s.abs() > 0)
    return s.ffill(limit=int(hold)).fillna(0.0).clip(-1.0, 1.0)


def _cached(name, fn, sp):
    key = (name, tuple(sorted(sp.items())))
    if key not in _CACHE:
        _CACHE[key] = fn(DF, **sp)
    return _CACHE[key]


def _mp(name, fn, sesh):
    def make_pos(**p):
        p = dict(p); hold = p.pop("hold")
        pos = held(_cached(name, fn, {k: int(v) for k, v in p.items()}), hold)
        return pos.where(HILIQ, 0.0) if sesh else pos
    return make_pos


STRATS = {
    "FVG":      (fvg_signal, {"lb": [40, 80], "hold": [4, 8, 16]}),
    "LiqSweep": (ls_signal,  {"slb": [40, 80], "hold": [4, 8, 16]}),
    "ORB":      (orb_signal, {"orb_bars": [2, 4], "hold": [4, 8, 16]}),
}


def main():
    global DF, HILIQ
    b = pd.read_pickle(ROOT / "empirical_runs" / "btc_15m_long.pkl")
    b["dt"] = pd.to_datetime(b["timestamp"], unit="ms", utc=True)
    DF = b.set_index("dt")[["open", "high", "low", "close", "volume"]].astype(float).sort_index()
    px = DF["close"]
    fwd = px.shift(-1) / px - 1
    h = DF.index.hour.values
    HILIQ = pd.Series(((h >= 0) & (h < 4)) | ((h >= 7) & (h < 10)) | ((h >= 12) & (h < 16)), index=DF.index)
    print(f"15m: {len(DF)} bars {DF.index[0].date()}→{DF.index[-1].date()} | HiLiq {HILIQ.mean()*100:.0f}%\n")

    rows = []
    for name, (fn, grid) in STRATS.items():
        for sesh in (False, True):
            tag = f"{name}{'·sesh' if sesh else ''}"
            mp = _mp(name, fn, sesh)
            r = evaluate_strategy(mp, grid, px, cost_bps=10, ppy=PPY, train_days=365, test_days=120)
            best = r["best"]
            s0 = evaluate_positions(mp(**best), px, cost_bps=0, ppy=PPY)["net_sharpe"]
            s10 = evaluate_positions(mp(**best), px, cost_bps=10, ppy=PPY)["net_sharpe"]
            cv = r["wf"].get("cv_sharpe"); dsr = (r["dsr"] or {}).get("dsr")
            rows.append({"name": tag, "best": best, "cv": cv, "dsr": dsr, "pbo": r["pbo"],
                         "plat": r["opt"].get("plateau_score"), "nocost": s0, "cost10": s10, "mp": mp,
                         "robust": (cv or 0) > 0.3 and (r["pbo"] is None or r["pbo"] < 0.5)
                                   and (dsr or 0) > 0.9 and (r["opt"].get("plateau_score") or 0) >= 0.4})
    rows.sort(key=lambda x: -(x["cv"] if x["cv"] is not None else -9))

    br = rows[0]
    ap = evaluate_positions(br["mp"](**br["best"]), px, cost_bps=10, ppy=PPY)["position"]

    def sh(p):
        net = (p * fwd - p.diff().abs().fillna(p.abs()) * 10 / 1e4).fillna(0.0).dropna()
        return float(net.mean() / net.std(ddof=1) * ANN) if net.std(ddof=1) else 0.0

    obs = sh(ap); rng = np.random.default_rng(42); v = ap.values
    null = np.array([sh(pd.Series(np.roll(v, int(k)), index=ap.index)) for k in rng.integers(96, len(v) - 96, 200)])
    pval = float((null >= obs).mean())

    print(f"{'strategy':15s} best                    cv    DSR    PBO  plat  R | 無成本→10bps")
    print("-" * 86)
    for r in rows:
        gap = (r["nocost"] or 0) - (r["cost10"] or 0)
        print(f"{r['name']:15s} {str(r['best']):23s} {(r['cv'] or 0):+5.2f} "
              f"{str(r['dsr'] if r['dsr'] is not None else '—'):>5} "
              f"{str(r['pbo'] if r['pbo'] is not None else '—'):>4} {str(r['plat']):>4}  "
              f"{'✓' if r['robust'] else ' '} | {(r['nocost'] or 0):+.2f} → {(r['cost10'] or 0):+.2f} (成本 {gap:+.2f})")

    robust_n = sum(1 for r in rows if r["robust"])
    avg_gap = np.mean([(r["nocost"] or 0) - (r["cost10"] or 0) for r in rows])
    print("\n## 誠實判讀（intraday，影片真正的玩法）")
    print(f"- **成本真相**：平均「無成本→10bps」掉 {avg_gap:.2f} Sharpe —— 15m 交易密、成本兇；"
          f"舊 bt() 零成本＝最大灌水源。")
    print(f"- **robust：{robust_n}/{len(rows)}**（運氣預期 ≈ {round(len(rows)*0.1,1)}）")
    print(f"- 最佳({br['name']}) 置換 null：obs {obs:+.2f} vs null 中位 {np.median(null):+.2f}，"
          f"p={pval:.3f} → {'timing 特別' if pval < 0.05 else 'timing 不特別'}")
    ok = robust_n > round(len(rows) * 0.1, 1) + 1 and pval < 0.05
    print(f"  → {'有東西，值得 anchored holdout + forward 二驗。' if ok else '沒有可宣稱的真 edge；跟日線、跟鏈上因子一樣的下場。'}")

    out = ROOT / "reports" / "smc_sweep_15m.json"
    out.write_text(json.dumps({"generated": dt.datetime.now().isoformat(timespec="seconds"),
                               "ppy": PPY, "rows": [{k: v for k, v in r.items() if k != "mp"} for r in rows],
                               "permutation": {"strategy": br["name"], "observed": obs,
                                               "null_median": float(np.median(null)), "p_value": pval},
                               "robust_n": robust_n, "avg_cost_gap": float(avg_gap)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
