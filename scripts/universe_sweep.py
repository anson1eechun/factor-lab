#!/usr/bin/env python3
"""universe_sweep.py — 對全部 13 條鏈上 factor 做 honest 預註冊掃描。

共用 quick_research.research_factor（唯一真相）：每條用「經濟方向(pre-registered)」測，
輸出 OOS cv_sharpe / DSR / PBO / plateau / robust / 反向紅旗 排行榜，並做 universe 級
多重比較誠實判讀（13 條裡有幾條真撐得住 vs 純靠運氣）。

跑: uv run --with "numpy>=2" --with pandas --with pyyaml python scripts/universe_sweep.py
"""
import sys, os, json
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data import available  # noqa: E402
from core.backtest import load_btc_price  # noqa: E402
from quick_research import research_factor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _is_robust(R) -> bool:
    cv = R["wf"].get("cv_sharpe") or 0
    dsr = (R["dsr"] or {}).get("dsr") or 0
    pbo = R["pbo"]
    plat = R["opt"].get("plateau_score") or 0
    return cv > 0.3 and (pbo is None or pbo < 0.5) and dsr > 0.9 and plat >= 0.4


def main():
    px = load_btc_price()  # 共用，省 13× 載入
    rows = []
    for stem in available():
        try:
            R = research_factor(stem, px=px, log_ledger=True)
        except Exception as e:  # noqa: BLE001
            rows.append({"factor": stem.replace("btc_", ""), "error": str(e)[:60]})
            continue
        rows.append({
            "factor": stem.replace("btc_", ""), "model": R["model"], "dir": R["direction"],
            "preregistered": R["long_when"] is not None,
            "cv_sharpe": R["wf"].get("cv_sharpe"), "dsr": (R["dsr"] or {}).get("dsr"),
            "pbo": R["pbo"], "plateau": R["opt"].get("plateau_score"),
            "robust": _is_robust(R), "contra_wins": R["contra_wins"],
            "contra_cv": R["contra"]["wf"].get("cv_sharpe"),
        })
    ok = [r for r in rows if "error" not in r]
    ok.sort(key=lambda r: (r["cv_sharpe"] is None, -(r["cv_sharpe"] or -99)))

    n = len(ok)
    robust_n = sum(1 for r in ok if r["robust"])
    redflag_n = sum(1 for r in ok if r["contra_wins"])
    prereg_n = sum(1 for r in ok if r["preregistered"])
    exp_false = round(n * 0.10, 1)  # DSR>0.9 門檻 → 每條約 10% 假陽性

    def f(x, w=6, p=2):
        return (" " * w if x is None else f"{x:+{w}.{p}f}")

    print("# Universe Sweep — 13 條鏈上 factor 的誠實預註冊掃描\n")
    print(f"{'factor':22s} {'model':16s} dir  cv_sharpe   DSR    PBO  plateau R  flag")
    print("-" * 78)
    for r in ok:
        preg = "·" if r["preregistered"] else " "
        print(f"{r['factor'][:22]:22s} {r['model']:16s} {preg}{r['dir']:>2}  {f(r['cv_sharpe'])}   "
              f"{str(r['dsr'] if r['dsr'] is not None else '—'):>5} "
              f"{str(r['pbo'] if r['pbo'] is not None else '—'):>4} "
              f"{f(r['plateau'], 5, 2)}  {'✓' if r['robust'] else ' '}  "
              f"{'⚠' if r['contra_wins'] else ''}")
    for r in rows:
        if "error" in r:
            print(f"{r['factor'][:22]:22s} ERROR: {r['error']}")
    print("（dir 前 · = 方向由 trading_signal 預註冊；無點 = 判讀不出、預設 +1）")

    print("\n## 誠實判讀")
    print(f"- {n} 條因子全部用經濟方向測；其中 {prereg_n} 條方向由 trading_signal 預註冊，"
          f"{n - prereg_n} 條判讀不出（預設 +1，僅供參考）。")
    print(f"- **robust（cv>0.3 且 DSR>0.9 且 PBO<0.5 且 plateau≥0.4）：{robust_n}/{n}**")
    print(f"- 反向紅旗（只有反方向賺、與敘事相反，疑過擬合/標反）：{redflag_n}/{n}")
    print(f"- 多重比較：{n} 條測試、DSR>0.9 門檻，純運氣預期假陽性 ≈ {exp_false} 條"
          f"（robust 還疊了 PBO/plateau，實際更嚴）。")
    verdict = ("與運氣預期同量級 → **不足以宣稱有真 edge**，需更多獨立資料/真 OOS。"
               if robust_n <= exp_false + 1 else
               "高於運氣預期 → 值得挑出來做更嚴格的獨立驗證（新資料/walk-forward 延長）。")
    print(f"  → robust={robust_n} vs 運氣≈{exp_false}：{verdict}")

    out = ROOT / "reports" / "universe_sweep.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated": dt.datetime.now().isoformat(timespec="seconds"),
                               "n": n, "robust_n": robust_n, "redflag_n": redflag_n,
                               "expected_false_positives": exp_false, "rows": ok},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
