#!/usr/bin/env python3
"""validate_coinbase_trendup.py — 對唯一倖存策略 coinbase_premium_gap × trend_up 做最嚴格的二驗。

⚠ 誠實前提：真 OOS 已不可能 —— 策略結構(coinbase×sign_flow×trend_up)是用**全部** BTC 日線歷史
選出來的（round1 從 13 條選因子、round2 從 4 regime 選 trend_up）。以下做能做的最嚴驗證：
  1) anchored 參數 holdout（w 只在 train 選，test 全新）
  2) regime 閾值敏感度（SMA n）
  3) 成本敏感度
  4) 置換 null（trend_up 遮罩隨機環移，比對 net Sharpe → trend_up 的擇時是否特別）
  5) 年度穩定

跑: uv run --with "numpy>=2" --with pandas python scripts/validate_coinbase_trendup.py
"""
import sys, os, json
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from core.data import load
from core.signal_models import sign_flow, condition_on_regime
from core.backtest import load_btc_price, evaluate_positions, grid_optimize

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = [10, 15, 20, 25, 30, 40, 50, 60]
SPLIT = "2025-01-01"  # train < SPLIT ≤ test


def _trend(px, n):
    return (px > px.rolling(n).mean()).fillna(False)


def _eval(pos, px, cost=10.0, lag=1):
    return evaluate_positions(pos, px, cost_bps=cost, lag=lag)


def main():
    px = load_btc_price()
    cb = load("coinbase_premium_gap")
    trend100 = _trend(px, 100)

    def strat(w, mask, px_eval, cost=10.0):
        return _eval(condition_on_regime(sign_flow(cb, w=int(w), direction=1), mask), px_eval, cost)

    # ── 1) anchored 參數 holdout ──
    tr = px[px.index < SPLIT]
    te = px[px.index >= SPLIT]
    opt = grid_optimize(lambda w: condition_on_regime(sign_flow(cb, w=int(w), direction=1), trend100),
                        {"w": WINDOWS}, tr)
    w_tr = (opt["best_params"] or {"w": 30})["w"]
    test_cond = strat(w_tr, trend100, te)
    test_base = _eval(sign_flow(cb, w=int(w_tr), direction=1), te)  # 同期未條件化對照
    print("# 獨立二驗：coinbase_premium_gap × trend_up\n")
    print("⚠ 真 OOS 不可能（結構用全歷史選出）；下列為 anchored-holdout + 敏感度 + 置換 null。\n")
    print(f"## 1) anchored 參數 holdout（w 只在 train<{SPLIT} 選 = {w_tr}，test 全新）")
    print(f"   test 期 {te.index.min().date()}..{te.index.max().date()}（{len(te)} 日）")
    print(f"   conditioned : net_sharpe={test_cond['net_sharpe']:+.2f}  ann={test_cond['ann_return']*100:+.1f}%  "
          f"MDD={test_cond['max_drawdown']*100:.1f}%  t={test_cond['t_stat']:+.2f}")
    print(f"   (對照)未條件: net_sharpe={test_base['net_sharpe']:+.2f}  → 條件化在 test 期"
          f"{'有加分' if test_cond['net_sharpe'] > test_base['net_sharpe'] else '沒加分'}")

    # ── 2) regime 閾值敏感度（全樣本 net_sharpe）──
    print(f"\n## 2) regime 閾值敏感度（SMA n；w={w_tr} 固定）")
    sma_rows = {}
    for n in (50, 100, 150, 200):
        sh = strat(w_tr, _trend(px, n), px)["net_sharpe"]
        sma_rows[n] = sh
        print(f"   SMA {n:>3}d: net_sharpe={sh:+.2f}")
    sma_ok = sum(1 for v in sma_rows.values() if v > 0.3)

    # ── 3) 成本敏感度 ──
    print(f"\n## 3) 成本敏感度（w={w_tr}, trend100, 全樣本）")
    cost_rows = {}
    for c in (10, 20, 30, 50):
        sh = strat(w_tr, trend100, px, cost=c)["net_sharpe"]
        cost_rows[c] = sh
        print(f"   {c:>2}bps: net_sharpe={sh:+.2f}")

    # ── 4) 置換 null（trend_up 遮罩隨機環移）──
    obs = strat(w_tr, trend100, px)["net_sharpe"]
    mv = trend100.values.astype(bool)
    rng = np.random.default_rng(42)
    null = []
    for _ in range(500):
        sh = rng.integers(60, len(mv) - 60)
        shifted = pd.Series(np.roll(mv, sh), index=trend100.index)
        null.append(strat(w_tr, shifted, px)["net_sharpe"])
    null = np.array(null)
    p = float((null >= obs).mean())
    print(f"\n## 4) 置換 null（trend_up 環移 500 次，同形狀/duty-cycle、隨機相位）")
    print(f"   duty-cycle(在場比例)={mv.mean():.0%}  observed net_sharpe={obs:+.2f}")
    print(f"   null 中位={np.median(null):+.2f}  95 分位={np.quantile(null, 0.95):+.2f}  "
          f"p=P(null≥obs)={p:.3f}")

    # ── 5) 年度穩定 ──
    net = strat(w_tr, trend100, px)["net_returns"]
    yearly = {str(y): round(float(g.mean() / g.std(ddof=1) * np.sqrt(365)), 2)
              for y, g in net.groupby(net.index.year) if g.std(ddof=1) and len(g) > 30}
    print(f"\n## 5) 年度 net Sharpe：{yearly}")

    # ── 判讀 ──
    print("\n## 判讀")
    checks = {
        "holdout test cv>0.3 且 ≥未條件化": test_cond["net_sharpe"] > 0.3 and test_cond["net_sharpe"] >= test_base["net_sharpe"],
        "閾值穩定(≥3/4 SMA 過 0.3)": sma_ok >= 3,
        "成本到 30bps 仍 >0.3": cost_rows[30] > 0.3,
        "置換 null p<0.05(trend_up 擇時特別)": p < 0.05,
        "年度 ≥3 年為正": sum(1 for v in yearly.values() if v > 0) >= 3,
    }
    for k, v in checks.items():
        print(f"   [{'PASS' if v else 'FAIL'}] {k}")
    npass = sum(checks.values())
    # 決定性測試＝真 OOS holdout + 置換 null（其餘三項是全樣本穩健度，策略就是在全樣本選出的，不算獨立）
    decisive = (checks["holdout test cv>0.3 且 ≥未條件化"]
                and checks["置換 null p<0.05(trend_up 擇時特別)"])
    if decisive and npass >= 4:
        verdict = "兩個決定性測試(holdout OOS + 置換 null)都過 → 值得在真新資料/別資產做最終確認（仍非保證）。"
    elif not decisive:
        verdict = (f"{npass}/5，但**兩個決定性測試(holdout OOS、置換 null)至少一個失敗** → "
                   f"trend_up 條件化是選擇性假象，二驗未過。殘留的只有未條件化的 base coinbase 訊號"
                   f"（test 期 net_sharpe={test_base['net_sharpe']:+.2f}），而它本身也是 13 選 1 的倖存者 → "
                   f"僅算弱候選、別上線。")
    else:
        verdict = f"{npass}/5 → 半信半疑，弱候選。"
    print(f"\n→ {verdict}")

    out = ROOT / "reports" / "validate_coinbase_trendup.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "generated": dt.datetime.now().isoformat(timespec="seconds"), "w_selected_on_train": int(w_tr),
        "holdout": {"test_conditioned_sharpe": test_cond["net_sharpe"], "test_base_sharpe": test_base["net_sharpe"],
                    "test_start": str(te.index.min().date())},
        "sma_sensitivity": sma_rows, "cost_sensitivity": cost_rows,
        "permutation": {"observed": obs, "null_median": float(np.median(null)), "p_value": p},
        "yearly": yearly, "checks": checks, "n_pass": npass,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
