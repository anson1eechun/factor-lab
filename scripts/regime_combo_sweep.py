#!/usr/bin/env python3
"""regime_combo_sweep.py — 第二輪掃描：regime-conditioning + pre-registered combinations。

延續 universe_sweep 的誠實紀律（pre-register、DSR 對 grid 試驗校正、多重比較判讀）。

A) regime-conditioning：對 base（單因子、經濟方向）OOS cv>0 的 factor，套 4 個**固定** regime 遮罩
   （趨勢上/下、波動高/低），regime 外歸零，重跑 grid+WF+DSR；看 conditioning 有沒有改善、且撐得住更高門檻。
B) pre-registered combinations：**等權合成**（不挖所有 pair）：all13、flow_pressure。

共用 core.backtest.evaluate_strategy（與 quick_research 同一套）。
跑: uv run --with "numpy>=2" --with pandas --with pyyaml python scripts/regime_combo_sweep.py
"""
import sys, os, json
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data import load, meta, available  # noqa: E402
from core.signal_models import auto_signal, data_profile, regime_masks, condition_on_regime, composite  # noqa: E402
from core.backtest import load_btc_price, evaluate_strategy  # noqa: E402
from quick_research import infer_direction, DEFAULT_W, _grid_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WGRID = [10, 20, 30, 40, 50, 60]
FLOW = ["btc_exchange_netflow", "btc_exchange_outflow_total", "btc_miner_netflow_total",
        "stablecoin_exchange_netflow"]


def _spec(stem):
    s = load(stem)
    mdl = data_profile(s)["recommended_model"]
    d, lw, _ = infer_direction(meta(stem).get("trading_signal"), mdl)
    return s, mdl, (d if d is not None else 1), (lw is not None)


def _robust(r):
    cv = r["wf"].get("cv_sharpe") or 0
    dsr = (r["dsr"] or {}).get("dsr") or 0
    plat = r["opt"].get("plateau_score") or 0
    return cv > 0.3 and (r["pbo"] is None or r["pbo"] < 0.5) and dsr > 0.9 and plat >= 0.4


def _conditioned(s, mdl, d, mask):
    return lambda **p: condition_on_regime(auto_signal(s, direction=d, model=mdl, **p), mask)


def _composite_mp(members):
    return lambda **p: composite([auto_signal(s, direction=d, model=mdl, **p) for (s, mdl, d) in members])


def main():
    px = load_btc_price()
    masks = regime_masks(px)

    # ── base：13 條單因子（經濟方向）找 OOS cv>0 的 survivors ──
    base = {}
    for stem in available():
        s, mdl, d, preg = _spec(stem)
        r = evaluate_strategy(lambda **p: auto_signal(s, direction=d, model=mdl, **p),
                              _grid_for(mdl, DEFAULT_W), px)
        base[stem] = {"s": s, "mdl": mdl, "d": d, "cv": r["wf"].get("cv_sharpe")}
    survivors = [k for k, v in base.items() if (v["cv"] or 0) > 0]

    # ── A) regime-conditioning ──
    reg_rows = []
    for stem in survivors:
        v = base[stem]
        grid = _grid_for(v["mdl"], DEFAULT_W)
        for rname, mask in masks.items():
            r = evaluate_strategy(_conditioned(v["s"], v["mdl"], v["d"], mask), grid, px)
            reg_rows.append({"factor": stem.replace("btc_", ""), "regime": rname, "base_cv": round(v["cv"], 2),
                             "cv": r["wf"].get("cv_sharpe"), "dsr": (r["dsr"] or {}).get("dsr"),
                             "pbo": r["pbo"], "plateau": r["opt"].get("plateau_score"), "robust": _robust(r)})

    # ── B) pre-registered combinations ──
    combos = {"all13": available(), "flow_pressure": FLOW}
    combo_rows = []
    for cname, stems in combos.items():
        members = [(*_spec(st)[:3],) for st in stems]  # (s, mdl, d)
        r = evaluate_strategy(_composite_mp(members), {"w": WGRID}, px)
        combo_rows.append({"composite": cname, "n": len(members), "cv": r["wf"].get("cv_sharpe"),
                           "dsr": (r["dsr"] or {}).get("dsr"), "pbo": r["pbo"],
                           "plateau": r["opt"].get("plateau_score"), "robust": _robust(r)})

    # ── 報告 ──
    def fcv(x):
        return "  —  " if x is None else f"{x:+5.2f}"

    print("# 第二輪：regime-conditioning + combinations（誠實掃描）\n")
    print(f"base 單因子 OOS cv>0 的 survivors（{len(survivors)} 條）：",
          ", ".join(f"{k.replace('btc_','')}({base[k]['cv']:+.2f})" for k in survivors))

    print("\n## A) regime-conditioning（regime 外歸零）")
    print(f"{'factor':22s} {'regime':11s} base_cv  cv    DSR    PBO  plat  R  改善?")
    print("-" * 74)
    reg_rows.sort(key=lambda r: -((r["cv"] or -9)))
    for r in reg_rows:
        better = "↑" if (r["cv"] or -9) > r["base_cv"] else " "
        print(f"{r['factor']:22s} {r['regime']:11s} {r['base_cv']:+5.2f}  {fcv(r['cv'])} "
              f"{str(r['dsr'] if r['dsr'] is not None else '—'):>5} "
              f"{str(r['pbo'] if r['pbo'] is not None else '—'):>4} "
              f"{str(r['plateau']):>4}  {'✓' if r['robust'] else ' '}  {better}")

    print("\n## B) pre-registered combinations（等權合成）")
    print(f"{'composite':16s} n   cv    DSR    PBO  plateau robust")
    for r in combo_rows:
        print(f"{r['composite']:16s} {r['n']:>2}  {fcv(r['cv'])} "
              f"{str(r['dsr'] if r['dsr'] is not None else '—'):>5} "
              f"{str(r['pbo'] if r['pbo'] is not None else '—'):>4} "
              f"{str(r['plateau']):>6}  {'✓' if r['robust'] else ''}")

    n_tests = len(reg_rows) + len(combo_rows)
    robust_n = sum(1 for r in reg_rows + combo_rows if r["robust"])
    improved = sum(1 for r in reg_rows if (r["cv"] or -9) > r["base_cv"])
    exp_false = round(n_tests * 0.10, 1)
    print("\n## 誠實判讀")
    print(f"- 本輪新增 {n_tests} 個策略（{len(reg_rows)} regime-conditioned + {len(combo_rows)} composites）。"
          f"regime 是每條 factor 的 4 選 1，屬額外搜尋。")
    print(f"- regime-conditioning 改善 base cv 的：{improved}/{len(reg_rows)}（多數應變差，因歸零=樣本變少）。")
    print(f"- **robust（cv>0.3 且 DSR>0.9 且 PBO<0.5 且 plateau≥0.4）：{robust_n}/{n_tests}**")
    print(f"- 多重比較：{n_tests} 次測試、DSR>0.9，純運氣預期假陽性 ≈ {exp_false} 條。")
    verdict = ("與運氣同量級 → combos/regime **沒有救出真 edge**；維持上一輪結論。"
               if robust_n <= exp_false + 1 else
               "高於運氣 → 挑出 robust 者做獨立資料的二次驗證。")
    print(f"  → robust={robust_n} vs 運氣≈{exp_false}：{verdict}")
    robs = ([f"{r['factor']}×{r['regime']}" for r in reg_rows if r["robust"]]
            + [f"composite:{r['composite']}" for r in combo_rows if r["robust"]])
    if robs:
        print(f"- 通過 robust 的：{', '.join(robs)}。但 regime 是 4 選 1 的額外搜尋（DSR 只對 grid 校正、"
              f"未對 4 個 regime 校正），且通常是上一輪就活的 factor 被合理 regime 收窄、非新發現 → "
              f"仍須獨立新資料二驗，勿當可上線結論。")

    out = ROOT / "reports" / "regime_combo_sweep.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": dt.datetime.now().isoformat(timespec="seconds"),
                               "survivors": survivors, "regime": reg_rows, "combinations": combo_rows,
                               "n_tests": n_tests, "robust_n": robust_n, "expected_false_positives": exp_false},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
