#!/usr/bin/env python3
"""quick_research.py — Phase 3 一鍵研究入口（影片那個「5 分鐘出報告」體驗的本體）。

吃一個 factor → data_profile 選 signal model → grid_optimize(plateau) → rolling_walk_forward(OOS)
→ 出自包含 HTML 報告（equity / drawdown / 逐根 position / plateau heatmap / WF folds）。
複用 core.gate 的 Soul Questions 生 alpha-story scaffold（資料可導出的先填，判斷題標記待 agent 補）。

確定性 harness：stdout 印 JSON 摘要供 debate agent 解析；HTML 落 reports/。

跑：
  uv run --with "numpy>=2" --with pandas --with pyyaml python scripts/quick_research.py --factor coinbase_premium_gap
  選項：--direction 1|-1  --model sign_flow  --windows 10,20,30,40  --cost-bps 10  --lag 1
"""
from __future__ import annotations
import argparse, json, sys, os, html as _html, datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

from core.data import load, meta, available  # noqa: E402
from core.signal_models import data_profile, auto_signal  # noqa: E402
from core.backtest import load_btc_price, evaluate_strategy  # noqa: E402
from core.gate import SOUL_QS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DEFAULT_W = [10, 15, 20, 25, 30, 40, 50, 60]
SPIKE_K = [1.5, 2.0, 2.5, 3.0]
LEDGER = ROOT / "logs" / "search_ledger.jsonl"


def _ledger_tally(entry: dict) -> dict:
    """把本次搜尋追加到 search ledger，回傳累計統計（讓多重比較可見、防 cherry-pick）。"""
    LEDGER.parent.mkdir(exist_ok=True)
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), **entry}
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    runs = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]
    combos = {(r.get("factor"), r.get("direction")) for r in runs}
    return {"runs": len(runs), "distinct_factor_dir": len(combos),
            "total_param_trials": sum((r.get("n_combos") or 1) for r in runs)}


def _grid_for(model: str, windows: list[int]) -> dict:
    return {"w": windows, "k": SPIKE_K} if model == "breakout_spike" else {"w": windows}


MOMENTUM_FAMILY = {"sign_flow", "trend_drift", "percentile_rank", "breakout_spike"}
_BULL = ("bullish", "demand", "squeeze", "accumulat", "buy", "support", "看多", "買", "需求")
_BEAR = ("bearish", "dump", "sell", "distribut", "看空", "賣", "拋")  # 不含 "supply"：'removing supply' 反而看多


def infer_direction(trading_signal, model: str):
    """從 data_dictionary 的 trading_signal 推「經濟方向」(pre-registered)，不再盲目 +1。
    回 (direction, long_when, rationale)；判讀不出回 (None, None, reason)。
    long_when: factor 偏高時該做多('high')還是做空('low')。"""
    t = (trading_signal or "").lower()
    if not t:
        return None, None, "無 trading_signal，無法推方向（預設 +1，請人工核對）"

    def _cut(seg):  # 只看到下一句，避免吃進相反的 negative/low 子句
        cuts = [seg.find(x, 3) for x in (".", "；", "。", " negative", " low ")]
        cuts = [c for c in cuts if c > 0]
        return seg[:min(cuts)] if cuts else seg

    def _verdict(seg):  # 同句同時出現多空 → 視為模稜(None)，不硬猜
        b, r = any(w in seg for w in _BULL), any(w in seg for w in _BEAR)
        return "bull" if (b and not r) else ("bear" if (r and not b) else None)

    high_is = None  # factor 偏高時 → 'bull' / 'bear'
    for key in ("wide positive", "positive", "high spike", "high", "inflow", "rising", "上升", "流入", "偏高"):
        i = t.find(key)
        if i >= 0:
            high_is = _verdict(_cut(t[i:i + 70]))
            if high_is:
                break
    if high_is is None and "confirm" in t:  # 「Confirms bullish/bearish」是對前述高值觸發的方向判決
        high_is = "bull" if ("bull" in t and "bear" not in t) else ("bear" if "bear" in t else None)
    if high_is is None:  # 只描述「下降/流出側」→ 反推高值側
        for key in ("declining", "falling", "decreasing", "下降", "流出"):
            i = t.find(key)
            if i >= 0:
                v = _verdict(_cut(t[i:i + 70]))
                if v:
                    high_is = "bear" if v == "bull" else "bull"
                    break
    if high_is is None:
        return None, None, "trading_signal 判讀不出方向（模稜/sizing/reversal；預設 +1，請人工核對）"

    long_when = "high" if high_is == "bull" else "low"
    align = 1 if long_when == "high" else -1
    direction = align if model in MOMENTUM_FAMILY else -align
    rationale = (f"trading_signal：factor 偏高→{'看多' if high_is == 'bull' else '看空'}"
                 f"（long_when={long_when}）→ {model} 取 direction={direction}")
    return direction, long_when, rationale


def _soul_story(factor, stem, m, prof, direction, model, wf, single, date_range) -> dict:
    """Soul Questions scaffold：資料可導出的據實填，判斷題留給 Proposer/Helen。"""
    desc, sig = (m.get("description") or "").strip(), (m.get("trading_signal") or "").strip()
    return {
        SOUL_QS[0]: desc or "（待 Proposer 補：為何此 alpha 現在存在）",
        SOUL_QS[1]: "（待 Proposer/Helen 補：擁擠化 / 機制失效 / 資料延遲改變）",
        SOUL_QS[2]: sig or "（待 Proposer 補：對手方是誰、其行為）",
        SOUL_QS[3]: f"{m.get('name') or factor}｜model={model}, direction={direction}（{prof.get('reason','')}）",
        SOUL_QS[4]: f"data/onchain/{stem}.json｜{m.get('granularity')}, "
                    f"{date_range[0]}~{date_range[1]}, n={prof.get('n')}",
        SOUL_QS[5]: f"OOS cv_sharpe={wf.get('cv_sharpe')} vs in-sample net_sharpe={single.get('net_sharpe')}"
                    f"；正向折 {wf.get('positive_folds')}/{wf.get('n_folds')}",
    }


# ── 自包含 HTML 報告 ────────────────────────────────────────────────
CSS = """
body{background:#0a0e14;color:#e6edf3;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:14px;margin:22px 0 8px;color:#7d8590;border-bottom:1px solid #21262d;padding-bottom:4px}
.meta{color:#7d8590;font-size:13px;margin-bottom:8px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:4px 0} td,th{border:1px solid #21262d;padding:6px 8px;text-align:left;vertical-align:top}
th{color:#7d8590;font-weight:600}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}
.card{background:#11161e;border:1px solid #21262d;border-radius:8px;padding:10px 14px;min-width:110px}
.card .k{color:#7d8590;font-size:12px} .card .v{font-size:19px;font-weight:600;margin-top:2px}
.pos{color:#3fb950} .neg{color:#f85149}
.plot{background:#11161e;border:1px solid #21262d;border-radius:8px;margin:8px 0;padding:4px}
.badge{display:inline-block;padding:2px 9px;border-radius:10px;font-size:12px;font-weight:600}
.badge.ok{background:#13361f;color:#3fb950} .badge.no{background:#3d1418;color:#f85149}
"""


def _card(k, v, sign=None):
    cls = "" if sign is None else (" pos" if sign >= 0 else " neg")
    return f'<div class="card"><div class="k">{_html.escape(k)}</div><div class="v{cls}">{v}</div></div>'


def _lay(title, h=260, **kw):
    lay = {"title": {"text": title, "font": {"size": 13, "color": "#e6edf3"}},
           "paper_bgcolor": "#0a0e14", "plot_bgcolor": "#11161e", "font": {"color": "#e6edf3", "size": 11},
           "margin": {"l": 50, "r": 16, "t": 34, "b": 40}, "height": h, "showlegend": False}
    lay.update(kw)
    return lay


def render_html(*, factor, stem, m, prof, model, direction, args, opt, single, wf, story,
                dsr, pbo, ledger, contra, rationale, contra_wins) -> str:
    net = single["net_returns"]
    dates = [d.strftime("%Y-%m-%d") for d in net.index]
    eqv = (1.0 + net).cumprod()
    ddv = eqv / eqv.cummax() - 1.0
    posv = single["position"].reindex(net.index).fillna(0.0)
    GR, RD, AX = "#3fb950", "#f85149", {"gridcolor": "#21262d", "zerolinecolor": "#30363d"}

    figs = []  # (div_id, data, layout)
    figs.append(("equity",
                 [{"type": "scatter", "mode": "lines", "x": dates, "y": eqv.round(4).tolist(),
                   "line": {"color": GR}}],
                 _lay("權益曲線（淨值，扣成本）", yaxis={"type": "log", **AX}, xaxis=AX)))
    figs.append(("dd",
                 [{"type": "scatter", "mode": "lines", "x": dates, "y": ddv.round(4).tolist(),
                   "fill": "tozeroy", "line": {"color": RD}}],
                 _lay("回撤", h=200, yaxis={"tickformat": ".0%", **AX}, xaxis=AX)))
    figs.append(("position",
                 [{"type": "scatter", "mode": "lines", "x": dates, "y": posv.round(3).tolist(),
                   "line": {"shape": "hv", "color": "#58a6ff"}}],
                 _lay("逐根部位 position（+1 多 / -1 空 / 0 空手）— 不黑箱", h=200,
                      yaxis={"range": [-1.1, 1.1], **AX}, xaxis=AX)))
    if "heatmap" in opt:
        hm = opt["heatmap"]
        figs.append(("plateau",
                     [{"type": "heatmap", "z": hm["z"], "x": hm["x"], "y": hm["y"],
                       "colorscale": "RdYlGn", "zmid": 0, "colorbar": {"title": "Sharpe"}}],
                     _lay(f"plateau heatmap（{hm['x_name']}×{hm['y_name']}，綠=高 Sharpe）",
                          xaxis={"title": hm["x_name"], **AX}, yaxis={"title": hm["y_name"], **AX})))
    else:
        rs = [r for r in opt["results"] if r["score"] == r["score"]]
        rs.sort(key=lambda r: r["params"]["w"])
        xs = [r["params"]["w"] for r in rs]
        ys = [round(r["score"], 3) for r in rs]
        figs.append(("plateau",
                     [{"type": "bar", "x": xs, "y": ys,
                       "marker": {"color": [GR if v > 0 else RD for v in ys]}}],
                     _lay("plateau（各 window 的 net Sharpe；整片綠=穩健非運氣）",
                          xaxis={"title": "window w", **AX}, yaxis={"title": "net Sharpe", **AX})))
    if wf.get("folds"):
        fx = [f["test"] for f in wf["folds"]]
        fy = [f["oos_sharpe"] for f in wf["folds"]]
        figs.append(("folds",
                     [{"type": "bar", "x": fx, "y": fy,
                       "marker": {"color": [GR if v > 0 else RD for v in fy]}}],
                     _lay("rolling walk-forward 各折 OOS Sharpe", xaxis=AX, yaxis=AX)))

    # cards
    o, s, w = opt, single, wf
    cv = w.get("cv_sharpe")
    dsr_v = (dsr or {}).get("dsr")
    cards = "".join([
        _card("OOS cv_sharpe ★", cv, (cv or 0)),
        _card("DSR（試 N 次後可信）", dsr_v if dsr_v is not None else "—", (dsr_v or 0) - 0.9),
        _card("PBO（過擬合率）", pbo if pbo is not None else "—", (0.5 - pbo) if pbo is not None else None),
        _card("正向折 OOS", f'{w.get("positive_folds")}/{w.get("n_folds")}'),
        _card("in-sample SR ⚠樂觀", s["net_sharpe"], s["net_sharpe"]),
        _card("plateau", o["plateau_score"], o["plateau_score"]),
        _card("OOS MDD", f'{(w.get("oos_max_drawdown") or 0)*100:.1f}%', w.get("oos_max_drawdown", 0)),
    ])
    is_robust = ((cv or 0) > 0.3 and (pbo is None or pbo < 0.5)
                 and (dsr_v or 0) > 0.9 and o["plateau_score"] >= 0.4)
    robust = ('<span class="badge ok">ROBUST（OOS+PBO+DSR 通過）</span>' if is_robust
              else '<span class="badge no">FRAGILE / 可能過擬合</span>')
    honesty = (f'⚠ honesty：in-sample SR 是 {o.get("n_combos")} 組參數挑最佳（偏樂觀）；DSR 已對此 N 校正。'
               f'本機累計 quick_research {ledger.get("runs")} 次、{ledger.get("distinct_factor_dir")} 個 '
               f'factor×direction、總 {ledger.get("total_param_trials")} 組參數試驗 — 最佳結果請按此比較次數打折看。'
               f'OOS cv_sharpe 才是誠實數字。')
    cw = contra["wf"]
    cdsr, cpbo = (contra["dsr"] or {}).get("dsr"), contra["pbo"]
    dirflag = ('<span class="badge no">⚠ 只有反方向賺錢——與敘事相反，疑過擬合 / metadata 標反</span>'
               if contra_wins else '')
    dir_rows = (
        '<tr><th>方向</th><th>direction</th><th>OOS cv_sharpe</th><th>DSR</th><th>PBO</th></tr>'
        f'<tr><td>採用（pre-registered）</td><td>{direction}</td><td>{wf.get("cv_sharpe")}</td>'
        f'<td>{(dsr or {}).get("dsr")}</td><td>{pbo}</td></tr>'
        f'<tr><td>反向（sanity check）</td><td>{-direction}</td><td>{cw.get("cv_sharpe")}</td>'
        f'<td>{cdsr}</td><td>{cpbo}</td></tr>')

    soul_rows = "".join(
        f"<tr><th>{_html.escape(q)}</th><td>{_html.escape(str(a))}</td></tr>" for q, a in story.items())
    fold_rows = "".join(
        f'<tr><td>{f["test"]}</td><td>{f["best_params"]}</td>'
        f'<td class="{"pos" if f["oos_sharpe"]>0 else "neg"}">{f["oos_sharpe"]}</td>'
        f'<td>{f["oos_return"]*100:.1f}%</td></tr>' for f in w.get("folds", []))

    scripts = "".join(
        f'Plotly.newPlot("{i}",{json.dumps(d, ensure_ascii=False)},'
        f'{json.dumps(l, ensure_ascii=False)},{{responsive:true,displayModeBar:false}});'
        for i, d, l in figs)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>quick_research · {_html.escape(factor)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><style>{CSS}</style></head><body>
<h1>quick_research · {_html.escape(m.get('name') or factor)} {robust}</h1>
<div class="meta">asset=BTC · model={model} · direction={direction} · best={o['best_params']} ·
cost={args.cost_bps}bps · lag={args.lag} · 產生於 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="cards">{cards}</div>
<div class="meta">{honesty}</div>
<h2>方向推斷 {dirflag}</h2><div class="meta">{_html.escape(rationale)}</div><table>{dir_rows}</table>
<h2>Alpha Story（Soul Questions scaffold）</h2><table>{soul_rows}</table>
<h2>績效（in-sample 最佳參數，扣成本）</h2>
<div id="equity" class="plot"></div><div id="dd" class="plot"></div><div id="position" class="plot"></div>
<h2>穩健性</h2><div id="plateau" class="plot"></div><div id="folds" class="plot"></div>
<h2>Walk-forward 折次（OOS，每折重選參）</h2>
<table><tr><th>test 窗</th><th>best params</th><th>OOS Sharpe</th><th>OOS 報酬</th></tr>{fold_rows}</table>
<script>{scripts}</script></body></html>"""


RENDER_KEYS = ("factor", "stem", "m", "prof", "model", "direction", "opt", "single", "wf",
               "story", "dsr", "pbo", "ledger", "contra", "rationale", "contra_wins")


def research_factor(factor, *, direction="auto", model=None, windows=None, cost_bps=10.0,
                    lag=1, train_days=365, test_days=120, px=None, description=None,
                    log_ledger=True) -> dict:
    """單一 factor 的完整研究 pipeline（quick_research 與 universe_sweep 共用＝唯一真相）。
    load → 自動選模 → 從 trading_signal 推方向(pre-registered) → 採用/反向各跑 grid+WF →
    DSR/PBO → ledger。FileNotFoundError 由 load 拋出。"""
    s = load(factor)
    stem = s.name
    m = meta(factor)
    if description:
        m = {**m, "description": description}
    prof = data_profile(s)
    mdl = model or prof["recommended_model"]
    windows = windows or DEFAULT_W
    if px is None:
        px = load_btc_price()
    grid = _grid_for(mdl, windows)

    def _run(d):
        mp = lambda **p: auto_signal(s, direction=d, model=mdl, **p)  # noqa: E731
        return {"direction": d, **evaluate_strategy(mp, grid, px, cost_bps=cost_bps, lag=lag,
                                                     train_days=train_days, test_days=test_days)}

    inferred, long_when, rationale = infer_direction(m.get("trading_signal"), mdl)
    if str(direction) in ("1", "-1"):
        primary_dir, rationale = int(direction), f"使用者指定 direction={direction}"
    elif inferred is not None:
        primary_dir = inferred
    else:
        primary_dir = 1  # rationale 已說明判讀不出
    primary, contra = _run(primary_dir), _run(-primary_dir)
    cvp = primary["wf"].get("cv_sharpe") or 0
    cvc = contra["wf"].get("cv_sharpe") or 0
    contra_wins = (cvc - cvp) > 0.3 and cvp < 0.3
    ledger = (_ledger_tally({"factor": factor, "model": mdl, "direction": primary_dir,
                             "n_combos": (primary["opt"].get("n_combos") or 0) * 2,
                             "best_score": primary["opt"].get("best_score"),
                             "cv_sharpe": cvp, "dsr": primary["dsr"].get("dsr"), "pbo": primary["pbo"]})
              if log_ledger else {"runs": None, "distinct_factor_dir": None, "total_param_trials": None})
    date_range = (s.index.min().date().isoformat(), s.index.max().date().isoformat())
    story = _soul_story(factor, stem, m, prof, primary_dir, mdl, primary["wf"], primary["single"], date_range)
    return {"factor": factor, "stem": stem, "m": m, "prof": prof, "model": mdl, "direction": primary_dir,
            "opt": primary["opt"], "best": primary["best"], "single": primary["single"], "wf": primary["wf"],
            "dsr": primary["dsr"], "pbo": primary["pbo"], "contra": contra, "rationale": rationale,
            "contra_wins": contra_wins, "story": story, "ledger": ledger, "date_range": date_range,
            "long_when": long_when, "cvp": cvp, "cvc": cvc}


def _summary(R: dict) -> dict:
    return {
        "factor": R["factor"], "file": R["stem"], "asset": "BTC", "model": R["model"], "direction": R["direction"],
        "profile": {k: R["prof"].get(k) for k in ("tags", "recommended_model", "reason", "skew", "excess_kurtosis")},
        "single_pass_optimized": {k: R["single"][k] for k in
                                  ("net_sharpe", "ann_return", "max_drawdown", "t_stat", "turnover_per_day", "exposure")},
        "optimize": {k: R["opt"][k] for k in ("best_params", "best_score", "plateau_score", "positive_frac", "robust", "n_combos")},
        "walk_forward": {k: R["wf"].get(k) for k in
                         ("cv_sharpe", "positive_folds", "n_folds", "positive_fold_frac", "oos_max_drawdown", "oos_total_return")},
        "deflated_sharpe": R["dsr"], "pbo": R["pbo"], "search_ledger": R["ledger"],
        "direction_inference": {"used": R["direction"], "rationale": R["rationale"], "contra_wins": R["contra_wins"],
                                "contra_cv_sharpe": R["contra"]["wf"].get("cv_sharpe"),
                                "contra_dsr": (R["contra"]["dsr"] or {}).get("dsr")},
        "alpha_story": R["story"],
    }


def main():
    ap = argparse.ArgumentParser(description="Phase 3 一鍵因子研究")
    ap.add_argument("--factor", required=True, help="鏈上序列名（容錯 btc_ 前綴）")
    ap.add_argument("--direction", default="auto", help="1 / -1 / auto（從 trading_signal 推，預設）")
    ap.add_argument("--model", default=None, help="覆寫 auto 選模")
    ap.add_argument("--description", default=None)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--lag", type=int, default=1)
    ap.add_argument("--windows", default=None, help='逗號分隔，如 "10,20,30,40"')
    ap.add_argument("--train-days", type=int, default=365)
    ap.add_argument("--test-days", type=int, default=120)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        R = research_factor(args.factor, direction=args.direction, model=args.model,
                            windows=([int(x) for x in args.windows.split(",")] if args.windows else None),
                            cost_bps=args.cost_bps, lag=args.lag, train_days=args.train_days,
                            test_days=args.test_days, description=args.description)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e), "available": available()}, ensure_ascii=False))
        sys.exit(1)

    REPORTS.mkdir(exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else REPORTS / f"quick_{R['stem']}_{ts}.html"
    out.write_text(render_html(args=args, **{k: R[k] for k in RENDER_KEYS}), encoding="utf-8")
    print(json.dumps({**_summary(R), "report_html": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
