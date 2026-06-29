#!/usr/bin/env python3
"""validate_coinbase_base.py — 對殘留候選「未條件化 base coinbase premium」做同樣嚴格二驗。

誠實前提：coinbase 是 R1 從 13 條選出的倖存者（結構用全歷史選），真 OOS 不可能。
  1) anchored 參數 holdout（w 只在 train<2025 選，test 全新）+ t-stat（看 OOS 顯著性）
  2) window 敏感度/plateau
  3) 成本敏感度
  4) 置換 null（部位對 BTC 次日報酬隨機環移 → coinbase 擇時是否真的預測，而非平滑訊號的自相關假象）
  5) 年度穩定

跑: uv run --with "numpy>=2" --with pandas python scripts/validate_coinbase_base.py
"""
import sys, os, json
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from core.data import load
from core.signal_models import sign_flow
from core.backtest import load_btc_price, evaluate_positions, grid_optimize

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = [10, 15, 20, 25, 30, 40, 50, 60]
SPLIT = "2025-01-01"
ANN = np.sqrt(365)


def main():
    px = load_btc_price()
    cb = load("coinbase_premium_gap")
    fwd = px.shift(-1) / px - 1

    def sig(w):
        return sign_flow(cb, w=int(w), direction=1)

    def ev(w, px_eval, cost=10.0):
        return evaluate_positions(sig(w), px_eval, cost_bps=cost, lag=1)

    print("# base coinbase premium（未條件化）獨立二驗\n")
    print("⚠ 真 OOS 不可能（coinbase 是 13 選 1 倖存者）；下列 anchored-holdout + 敏感度 + 置換 null。\n")

    # ── 1) anchored holdout ──
    tr, te = px[px.index < SPLIT], px[px.index >= SPLIT]
    opt = grid_optimize(lambda w: sig(w), {"w": WINDOWS}, tr)
    w_tr = (opt["best_params"] or {"w": 30})["w"]
    t = ev(w_tr, te)
    sig_note = "顯著" if abs(t["t_stat"]) > 2 else ("接近顯著" if abs(t["t_stat"]) > 1.5 else "不顯著")
    print(f"## 1) anchored 參數 holdout（w 只在 train<{SPLIT} 選 = {w_tr}，test 全新）")
    print(f"   test {te.index.min().date()}..{te.index.max().date()}（{len(te)} 日）: "
          f"net_sharpe={t['net_sharpe']:+.2f}  t-stat={t['t_stat']:+.2f}  "
          f"ann={t['ann_return']*100:+.1f}%  MDD={t['max_drawdown']*100:.1f}%")
    print(f"   → OOS {'正' if t['net_sharpe'] > 0 else '負'}報酬，統計上{sig_note}(t={t['t_stat']:+.2f})")

    # ── 2) window plateau ──
    wfull = {w: ev(w, px)["net_sharpe"] for w in WINDOWS}
    wtest = {w: ev(w, te)["net_sharpe"] for w in WINDOWS}
    print("\n## 2) window 敏感度（plateau）")
    print("   w   : " + "  ".join(f"{w:>5}" for w in WINDOWS))
    print("   full: " + "  ".join(f"{wfull[w]:+5.2f}" for w in WINDOWS))
    print("   test: " + "  ".join(f"{wtest[w]:+5.2f}" for w in WINDOWS))
    plat_full = sum(1 for v in wfull.values() if v > 0.3) / len(WINDOWS)
    plat_test = sum(1 for v in wtest.values() if v > 0.3) / len(WINDOWS)
    print(f"   full plateau(>0.3)={plat_full:.0%}  test plateau={plat_test:.0%}")

    # ── 3) cost ──
    cost = {c: ev(w_tr, px, cost=c)["net_sharpe"] for c in (10, 20, 30, 50)}
    print(f"\n## 3) 成本敏感度（w={w_tr}, 全樣本）: "
          + "  ".join(f"{c}bps={v:+.2f}" for c, v in cost.items()))

    # ── 4) 置換 null：部位對次日報酬環移（破壞時間對齊、保留部位自相關/duty）──
    ap = pd.Series(sig(w_tr)).reindex(px.index).ffill().shift(1).fillna(0.0).clip(-1, 1)

    def _sh(p):
        turn = p.diff().abs().fillna(p.abs())
        net = (p * fwd - turn * 10 / 1e4).fillna(0.0).dropna()
        return float(net.mean() / net.std(ddof=1) * ANN) if net.std(ddof=1) else 0.0

    obs = _sh(ap)
    rng = np.random.default_rng(42)
    v = ap.values
    null = np.array([_sh(pd.Series(np.roll(v, int(k)), index=ap.index))
                     for k in rng.integers(60, len(v) - 60, 500)])
    p = float((null >= obs).mean())
    print(f"\n## 4) 置換 null（部位對次日報酬環移 500 次）")
    print(f"   observed net_sharpe={obs:+.2f}  null 中位={np.median(null):+.2f}  "
          f"95 分位={np.quantile(null, 0.95):+.2f}  p=P(null≥obs)={p:.3f}")

    # ── 5) yearly ──
    net = (ap * fwd - ap.diff().abs().fillna(ap.abs()) * 10 / 1e4).fillna(0.0)
    yearly = {str(y): round(float(g.mean() / g.std(ddof=1) * ANN), 2)
              for y, g in net.groupby(net.index.year) if g.std(ddof=1) and len(g) > 30}
    print(f"\n## 5) 年度 net Sharpe：{yearly}")

    # ── 判讀 ──
    checks = {
        "holdout test sharpe>0.3": t["net_sharpe"] > 0.3,
        "holdout OOS 顯著(t>2)": abs(t["t_stat"]) > 2,
        "window plateau(full)≥60%": plat_full >= 0.6,
        "成本到30bps>0.3": cost[30] > 0.3,
        "置換 null p<0.05": p < 0.05,
        "年度≥3年正": sum(1 for x in yearly.values() if x > 0) >= 3,
    }
    print("\n## 判讀")
    for k, val in checks.items():
        print(f"   [{'PASS' if val else 'FAIL'}] {k}")
    decisive = checks["holdout test sharpe>0.3"] and checks["置換 null p<0.05"]
    npass = sum(checks.values())
    if decisive:
        extra = "" if checks["holdout OOS 顯著(t>2)"] else "（但 OOS t 未達 2，樣本內顯著性弱）"
        verdict = (f"{npass}/6，兩個決定性測試(holdout OOS 正 + 置換 null 特別)都過{extra} → "
                   f"base coinbase 是**目前唯一還站得住的弱候選**，值得在真新資料/別資產做最終確認，仍勿直接上線。")
    elif not checks["置換 null p<0.05"]:
        verdict = (f"{npass}/6，但**置換 null p={p:.2f}** → coinbase 部位擇時與隨機相位無異、"
                   f"預測力非統計上特別 → 二驗未過，base coinbase 也只是 13 選 1 的運氣殘留。")
    else:
        verdict = f"{npass}/6，holdout OOS 不正 → 二驗未過。"
    print(f"\n→ {verdict}")

    out = ROOT / "reports" / "validate_coinbase_base.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "generated": dt.datetime.now().isoformat(timespec="seconds"), "w_selected_on_train": int(w_tr),
        "holdout": {"test_sharpe": t["net_sharpe"], "test_t_stat": t["t_stat"], "test_start": str(te.index.min().date())},
        "window_full": wfull, "window_test": wtest, "cost": cost,
        "permutation": {"observed": obs, "null_median": float(np.median(null)), "p_value": p},
        "yearly": yearly, "checks": checks, "n_pass": npass,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
