"""core.kb_graph — Phase 4：把 index.db + graveyard 變成 typed 知識圖譜（node/edge）。

純標準庫（sqlite3/json/re/pathlib），base python3 與 Balaena :8900 控制台都能 import。
全部用 index.db / graveyard 的真實資料，不杜撰節點（守 no-fake-data 紀律）。

node 類型（顏色對齊影片語意）：
  factor（alpha-research，依裁決上色：綠=validated/琥珀=rework/紅=reject·graveyard/藍=candidate）
  concept（青，論文可行動 insight） · paper（藍，文獻） · category/literature（hub） · root
"""
from __future__ import annotations
import sqlite3
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "index.db"
GRAVEYARD = ROOT / "graveyard"

_C = {
    "validated": "#4cc38a", "rework": "#f5a524", "reject": "#e5484d", "graveyard": "#8b1a1a",
    "candidate": "#5eb1ff", "concept": "#33c0d6", "paper": "#5eb1ff",
    "category": "#7d8590", "lit": "#c084fc", "root": "#e6edf3",
}
_PRI = {"VALIDATED": 3, "REWORK": 2, "DECAYED": 1, "REJECT": 0}
_ACTIONABLE = ("factor_insight", "design_constraint", "research_direction")


def _verdict_color(decision: str | None, status: str | None) -> str:
    d = (decision or "").upper()
    if status == "graveyard":
        return _C["graveyard"]
    if d == "VALIDATED" or status == "active":
        return _C["validated"]
    if d == "REWORK":
        return _C["rework"]
    if d in ("REJECT", "DECAYED") or status == "deprecated":
        return _C["reject"]
    return _C["candidate"]


def build_graph(db_path=None, graveyard_dir=None) -> dict:
    """從 index.db + graveyard 建 typed 圖。回傳 {nodes, edges, stats}。"""
    conn = sqlite3.connect(str(db_path or DB))
    conn.row_factory = sqlite3.Row
    gy = Path(graveyard_dir or GRAVEYARD)
    gy_names = {p.stem for p in gy.glob("*.md")} if gy.exists() else set()

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(nid, **kw):
        nodes[nid] = {"id": nid, **kw}

    def ensure_cat(c):
        nid = f"cat:{c}"
        if nid not in nodes:
            add(nid, label=c, group="category", color=_C["category"], shape="hexagon", value=18)
            edges.append({"from": "root", "to": nid})
        return nid

    add("root", label="factor-lab KB", group="root", color=_C["root"], shape="star", value=30)

    # ── factor 節點（依裁決聚合 debate_rounds + factor_registry + graveyard）──
    fac: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT factor_name,factor_category,decision,decision_reason,sharpe,ic_mean "
        "FROM debate_rounds WHERE factor_name IS NOT NULL AND factor_name!=''"
    ):
        f = fac.setdefault(r["factor_name"], {"cat": None, "dec": None, "reason": "", "sharpe": None, "ic": None})
        if r["factor_category"]:
            f["cat"] = r["factor_category"]
        if _PRI.get((r["decision"] or "").upper(), -1) >= _PRI.get((f["dec"] or "").upper(), -1) and r["decision"]:
            f["dec"], f["reason"] = r["decision"], (r["decision_reason"] or f["reason"])
        if r["sharpe"] is not None:
            f["sharpe"] = r["sharpe"]
        if r["ic_mean"] is not None:
            f["ic"] = r["ic_mean"]
    reg = {r["name"]: r for r in conn.execute("SELECT name,category,status,best_sharpe FROM factor_registry")}

    for name, f in fac.items():
        rrow = reg.get(name)
        status = "graveyard" if name in gy_names else (rrow["status"] if rrow is not None else None)
        cat = f["cat"] or (rrow["category"] if rrow is not None else None) or "uncategorized"
        tip = f"{name}｜{cat}｜裁決={f['dec'] or status or '?'}"
        if f["sharpe"] is not None:
            tip += f"｜Sharpe={round(f['sharpe'], 2)}"
        if f["reason"]:
            tip += f"｜{f['reason'][:90]}"
        add(f"f:{name}", label=name, group="factor", color=_verdict_color(f["dec"], status),
            title=tip, shape="dot", value=12)
        edges.append({"from": ensure_cat(cat), "to": f"f:{name}"})

    for name, rrow in reg.items():
        if name in fac:
            continue
        cat = rrow["category"] or "uncategorized"
        status = "graveyard" if name in gy_names else rrow["status"]
        add(f"f:{name}", label=name, group="factor", color=_verdict_color(None, status),
            title=f"{name}｜{cat}｜status={status}", shape="dot", value=12)
        edges.append({"from": ensure_cat(cat), "to": f"f:{name}"})

    for gname in sorted(gy_names):
        if f"f:{gname}" not in nodes:
            add(f"f:{gname}", label=gname, group="factor", color=_C["graveyard"],
                title=f"{gname}｜graveyard（無 DB 紀錄）", shape="dot", value=12)
            edges.append({"from": ensure_cat("graveyard"), "to": f"f:{gname}"})

    # ── 文獻 → 可行動 insight（concept）──
    add("lit", label="literature", group="lit", color=_C["lit"], shape="hexagon", value=20)
    edges.append({"from": "root", "to": "lit"})
    seen_paper = set()
    for r in conn.execute(
        "SELECT id,paper_id,paper_title,insight_type,insight FROM paper_insights "
        f"WHERE insight_type IN ({','.join('?' * len(_ACTIONABLE))})", _ACTIONABLE
    ):
        pid = r["paper_id"] or "unknown"
        if pid not in seen_paper:
            seen_paper.add(pid)
            add(f"p:{pid}", label=(r["paper_title"] or pid)[:26], group="paper", color=_C["paper"],
                title=f"{pid}｜{r['paper_title'] or ''}", shape="square", value=10)
            edges.append({"from": "lit", "to": f"p:{pid}"})
        add(f"i:{r['id']}", label=r["insight_type"], group="concept", color=_C["concept"],
            title=(r["insight"] or "")[:140], shape="triangle", value=7)
        edges.append({"from": f"p:{pid}", "to": f"i:{r['id']}"})

    conn.close()
    by = Counter(n["group"] for n in nodes.values())
    return {"nodes": list(nodes.values()), "edges": edges,
            "stats": {"nodes": len(nodes), "edges": len(edges), "by_type": dict(by)}}


_CSS = """html,body{margin:0;background:#0a0e14;color:#e6edf3;font-family:Inter,system-ui,sans-serif}
#bar{position:fixed;top:0;left:0;right:0;height:40px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
 padding:0 14px;background:#11161e;border-bottom:1px solid #1f2632;font-size:13px;z-index:5}
#net{position:absolute;top:40px;left:0;right:0;bottom:0}
.lg{display:inline-flex;align-items:center;gap:5px;color:#9aa6b7;font-size:12px}
.lg i{width:10px;height:10px;border-radius:2px;display:inline-block}"""


def render_html(graph: dict, title: str = "factor-lab 知識圖譜") -> str:
    """自包含 HTML（vis-network CDN），force-directed、typed 上色、節點 hover 顯示裁決/教訓。"""
    data = json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, ensure_ascii=False)
    st = graph["stats"]
    legend = [("validated", _C["validated"]), ("rework", _C["rework"]),
              ("reject/graveyard", _C["reject"]), ("candidate", _C["candidate"]),
              ("concept", _C["concept"]), ("paper", _C["paper"]), ("category", _C["category"])]
    leg = "".join(f'<span class="lg"><i style="background:{c}"></i>{n}</span>' for n, c in legend)
    by = json.dumps(st["by_type"], ensure_ascii=False)
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>{title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>{_CSS}</style></head><body>
<div id="bar"><b>{title}</b><span class="lg">nodes {st['nodes']} · edges {st['edges']} · {by}</span>{leg}</div>
<div id="net"></div>
<script>
const d={data};
const network=new vis.Network(document.getElementById('net'),
 {{nodes:new vis.DataSet(d.nodes),edges:new vis.DataSet(d.edges)}},
 {{nodes:{{font:{{color:'#e6edf3',size:12}},borderWidth:0,scaling:{{min:6,max:30}}}},
   edges:{{color:{{color:'#2a3340',highlight:'#5eb1ff'}},smooth:false,width:0.6}},
   physics:{{barnesHut:{{gravitationalConstant:-9000,springLength:130,centralGravity:0.25}},
            stabilization:{{iterations:220}}}},
   interaction:{{hover:true,tooltipDelay:120}}}});
</script></body></html>"""
