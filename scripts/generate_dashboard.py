#!/usr/bin/env python3
"""
Factor Lab — Control Panel (rebuild)
====================================
Single self-contained HTML cockpit generated from index.db. Everything shown is
REAL data pulled from the SQLite knowledge base — no fabricated agent metrics,
no fake logs, no dead nav links.

Sections:
  • KPI strip          — live counts from the DB
  • Charts (Plotly)    — factor status / category, literature sources, debate decisions
  • Factor table       — click any row to drill down: formula, hypothesis, metrics,
                         evidence rows, arbiter decision + reason, note path
  • Debate viewer      — expand each session to read the step-by-step transcript
                         and per-factor rulings
  • Insights           — paper_insights extracted from the literature

Usage:
  python3 scripts/generate_dashboard.py          # write dashboard.html
  python3 scripts/generate_dashboard.py --open   # also open in a browser
"""

import sqlite3
import json
import os
import sys
import webbrowser
from collections import Counter
from datetime import datetime

DB_PATH = "/home/anson/factor-lab/index.db"
OUTPUT_HTML = "/home/anson/factor-lab/dashboard.html"


# ── Data loading ─────────────────────────────────────────────────────
def _num(v):
    """Return a float or None (DB stores some metrics as text/None)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    factors = [dict(r) for r in conn.execute("SELECT * FROM factors")]
    registry = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM factor_registry")}
    rounds = [dict(r) for r in conn.execute("SELECT * FROM debate_rounds")]
    sessions = [dict(r) for r in conn.execute("SELECT * FROM debate_sessions ORDER BY session_id")]
    transcripts = [dict(r) for r in conn.execute(
        "SELECT * FROM debate_transcripts ORDER BY session_id, step_order")]
    evidence = [dict(r) for r in conn.execute("SELECT * FROM evidence")]
    insights = [dict(r) for r in conn.execute("SELECT * FROM paper_insights")]
    literature = [dict(r) for r in conn.execute("SELECT source, fetched_at FROM literature")]

    # Index helpers keyed by factor NAME (e.g. "F3_CCR") — the join key shared
    # by registry / debate_rounds / evidence (factors.id is just "F3").
    rounds_by_name = {}
    for r in rounds:
        rounds_by_name.setdefault(r["factor_name"], []).append(r)
    evidence_by_name = {}
    for e in evidence:
        evidence_by_name.setdefault(e["factor_id"], []).append(e)

    # Build the merged factor records used by the table + drilldown.
    merged = []
    for f in sorted(factors, key=lambda x: x["name"]):
        name = f["name"]
        reg = registry.get(name, {})
        frounds = rounds_by_name.get(name, [])
        latest = frounds[-1] if frounds else {}
        merged.append({
            "id": f["id"],
            "name": name,
            "category": f.get("category") or reg.get("category") or "—",
            "status": f.get("status") or reg.get("status") or "unknown",
            "formula": latest.get("factor_formula") or reg.get("formula") or "",
            "hypothesis": latest.get("hypothesis") or "",
            "ic_mean": _num(latest.get("ic_mean")) if latest else _num(reg.get("best_ic_mean")),
            "ic_ir": _num(latest.get("ic_ir")) if latest else _num(reg.get("best_ic_ir")),
            "sharpe": _num(latest.get("sharpe")) if latest else _num(reg.get("best_sharpe")),
            "max_drawdown": _num(latest.get("max_drawdown")),
            "decision": latest.get("decision") or "",
            "decision_reason": latest.get("decision_reason") or "",
            "total_rounds": reg.get("total_rounds") or 0,
            "note_path": reg.get("note_path") or f.get("note_path") or "",
            "session_id": latest.get("session_id") or "",
            "evidence": [
                {
                    "market": e.get("market"),
                    "rank_ic": _num(e.get("rank_ic")),
                    "ic_ir": _num(e.get("ic_ir")),
                    "ls_annual": _num(e.get("ls_annual")),
                    "computed_at": e.get("computed_at"),
                }
                for e in evidence_by_name.get(name, [])
            ],
        })

    # Attach transcript steps + rulings to each session.
    steps_by_session = {}
    for t in transcripts:
        steps_by_session.setdefault(t["session_id"], []).append({
            "step_order": t.get("step_order"),
            "agent_role": t.get("agent_role"),
            "duration_seconds": t.get("duration_seconds"),
            "model": t.get("model"),
            "output_summary": t.get("output_summary") or "",
        })
    sessions_out = []
    for s in sessions:
        sid = s["session_id"]
        sessions_out.append({
            "session_id": sid,
            "title": s.get("title") or sid,
            "notes": s.get("notes") or "",
            "started_at": s.get("started_at") or "",
            "completed_at": s.get("completed_at") or "",
            "num_proposed": s.get("num_factors_proposed") or 0,
            "num_validated": s.get("num_factors_validated") or 0,
            "num_deprecated": s.get("num_factors_deprecated") or 0,
            "steps": sorted(steps_by_session.get(sid, []), key=lambda x: (x["step_order"] or 0)),
            "rulings": [
                {
                    "factor_name": r.get("factor_name"),
                    "decision": r.get("decision") or "",
                    "decision_reason": r.get("decision_reason") or "",
                    "ic_mean": _num(r.get("ic_mean")),
                    "sharpe": _num(r.get("sharpe")),
                }
                for r in rounds if r.get("session_id") == sid
            ],
        })

    status_dist = Counter(m["status"] for m in merged)
    category_dist = Counter(m["category"] for m in merged)
    lit_by_source = Counter((l["source"] or "unknown") for l in literature)
    decision_dist = Counter(r["decision"] for r in rounds if r.get("decision"))

    conn.close()

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kpis": {
            "factors": len(merged),
            "candidates": status_dist.get("candidate", 0),
            "deprecated": status_dist.get("deprecated", 0),
            "sessions": len(sessions_out),
            "transcript_steps": len(transcripts),
            "papers": len(literature),
            "insights": len(insights),
            "evidence_rows": len(evidence),
        },
        "factors": merged,
        "sessions": sessions_out,
        "insights": insights,
        "charts": {
            "status_dist": dict(status_dist),
            "category_dist": dict(category_dist),
            "lit_by_source": dict(lit_by_source),
            "decision_dist": dict(decision_dist),
        },
    }


# ── HTML template (plain string; data injected via placeholder) ──────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Factor Lab — Control Panel</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {
  --bg-canvas:#0a0e14; --bg-surface:#11161e; --bg-hi:#161c25;
  --border:#1f2632; --border-2:#2a3340; --border-3:#3a4658;
  --text:#e6edf3; --text-2:#9aa6b7; --text-3:#5b6878;
  --green:#4cc38a; --amber:#f5a524; --red:#e5484d; --blue:#5eb1ff; --purple:#c084fc;
  --mono:'JetBrains Mono','Geist Mono','Courier New',monospace;
  --sans:'Inter','Geist',system-ui,sans-serif;
  --r:10px; --r-sm:6px;
}
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:var(--sans); font-size:13px; line-height:1.55;
  background:var(--bg-canvas); color:var(--text); padding-bottom:40px; }
a { color:var(--blue); text-decoration:none; }

.topbar { display:flex; align-items:center; justify-content:space-between;
  padding:14px 28px; background:var(--bg-surface); border-bottom:1px solid var(--border);
  position:sticky; top:0; z-index:50; }
.topbar__logo { font-size:16px; font-weight:700; letter-spacing:-.01em; }
.topbar__logo span { color:var(--green); }
.topbar__meta { font-size:11px; color:var(--text-3); font-family:var(--mono); }

.wrap { max-width:1280px; margin:0 auto; padding:24px 28px; }
.section-title { font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; color:var(--text-2); margin:28px 0 12px; }
.section-title:first-child { margin-top:0; }

/* KPI strip */
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; }
.kpi { background:var(--bg-surface); border:1px solid var(--border); border-radius:var(--r);
  padding:16px 18px; }
.kpi__val { font-family:var(--mono); font-size:26px; font-weight:700; line-height:1; }
.kpi__label { font-size:11px; color:var(--text-3); margin-top:6px; }
.kpi.green .kpi__val { color:var(--green); }
.kpi.amber .kpi__val { color:var(--amber); }

/* Charts */
.charts { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.card { background:var(--bg-surface); border:1px solid var(--border); border-radius:var(--r); }
.card__head { padding:12px 16px; border-bottom:1px solid var(--border);
  font-size:12px; font-weight:600; color:var(--text-2);
  text-transform:uppercase; letter-spacing:.05em; }
.card__body { padding:8px; }
.chart { width:100%; height:260px; }

/* Factor table */
table.factors { width:100%; border-collapse:collapse; }
.factors th { text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.05em;
  color:var(--text-3); padding:10px 14px; border-bottom:1px solid var(--border); font-weight:600; }
.factors td { padding:11px 14px; border-bottom:1px solid var(--border); font-size:12px;
  vertical-align:middle; }
.factor-row { cursor:pointer; transition:background .12s; }
.factor-row:hover { background:var(--bg-hi); }
.factor-row td:first-child { font-family:var(--mono); color:var(--text-2); }
.fname { font-weight:600; color:var(--text); }
.num { font-family:var(--mono); text-align:right; }
.num.pos { color:var(--green); } .num.neg { color:var(--red); } .num.na { color:var(--text-3); }
.badge { font-size:10px; padding:2px 9px; border-radius:9999px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; }
.badge.candidate { background:rgba(76,195,138,.14); color:var(--green); }
.badge.deprecated { background:rgba(229,72,77,.14); color:var(--red); }
.badge.unknown { background:var(--bg-hi); color:var(--text-3); }
.badge.REJECT { background:rgba(229,72,77,.14); color:var(--red); }
.badge.REWORK { background:rgba(245,165,36,.14); color:var(--amber); }
.badge.VALIDATE,.badge.VALIDATED { background:rgba(76,195,138,.14); color:var(--green); }
.chev { color:var(--text-3); font-size:10px; transition:transform .15s; display:inline-block; }
.factor-row.open .chev { transform:rotate(90deg); }

.detail-row td { background:#0c1118; padding:0; border-bottom:1px solid var(--border); }
.detail { padding:18px 20px; display:none; }
.detail.open { display:block; }
.detail__grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:14px;
  margin-bottom:14px; }
.field__label { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-3); }
.field__val { font-size:13px; margin-top:3px; }
.field__val.mono { font-family:var(--mono); font-size:12px; word-break:break-all; }
.reason { background:var(--bg-hi); border-left:3px solid var(--border-3); border-radius:0 var(--r-sm) var(--r-sm) 0;
  padding:10px 14px; font-size:12px; color:var(--text-2); margin-top:8px; }
.reason.REJECT { border-color:var(--red); }
.reason.REWORK { border-color:var(--amber); }
.ev-table { width:100%; border-collapse:collapse; margin-top:10px; font-size:11px; }
.ev-table th,.ev-table td { padding:6px 10px; text-align:left; border-bottom:1px solid var(--border); }
.ev-table th { color:var(--text-3); text-transform:uppercase; font-size:10px; }
.ev-table td { font-family:var(--mono); }

/* Debate viewer */
.debate { margin-bottom:12px; }
.debate__head { display:flex; align-items:center; gap:12px; padding:14px 18px; cursor:pointer; }
.debate__head:hover { background:var(--bg-hi); }
.debate__title { font-weight:600; flex:1; }
.debate__sid { font-family:var(--mono); font-size:10px; color:var(--text-3); }
.debate__counts { font-size:11px; color:var(--text-2); }
.debate__body { display:none; padding:0 18px 18px; }
.debate__body.open { display:block; }
.debate__notes { font-size:12px; color:var(--text-2); background:var(--bg-hi);
  border-radius:var(--r-sm); padding:10px 14px; margin:0 0 14px; }
.step { display:flex; gap:14px; padding:10px 0; border-bottom:1px solid var(--border); }
.step:last-child { border-bottom:none; }
.step__order { font-family:var(--mono); color:var(--text-3); flex-shrink:0; width:24px; }
.role { font-size:10px; padding:2px 9px; border-radius:9999px; font-weight:600; flex-shrink:0;
  height:fit-content; text-transform:uppercase; }
.role.proposer{background:rgba(94,177,255,.14);color:var(--blue);}
.role.builder{background:rgba(192,132,252,.14);color:var(--purple);}
.role.skeptic{background:rgba(245,165,36,.14);color:var(--amber);}
.role.empiricist{background:rgba(76,195,138,.14);color:var(--green);}
.role.arbiter{background:rgba(245,165,36,.18);color:var(--amber);}
.role.librarian{background:rgba(6,182,212,.14);color:#06b6d4;}
.step__main { flex:1; }
.step__summary { font-size:12px; color:var(--text); }
.step__meta { font-size:10px; color:var(--text-3); font-family:var(--mono); margin-top:3px; }
.rulings { margin-top:14px; }
.ruling { display:flex; align-items:center; gap:10px; padding:7px 0; font-size:12px;
  border-top:1px solid var(--border); }
.ruling__name { font-family:var(--mono); color:var(--text-2); width:160px; flex-shrink:0; }
.ruling__reason { color:var(--text-3); font-size:11px; flex:1; }

/* Insights */
.insight { padding:12px 16px; border-bottom:1px solid var(--border); }
.insight:last-child { border-bottom:none; }
.insight__type { font-size:10px; text-transform:uppercase; letter-spacing:.05em;
  color:var(--blue); font-weight:600; }
.insight__text { font-size:12px; color:var(--text-2); margin-top:4px; }

.foot { text-align:center; color:var(--text-3); font-size:11px; margin-top:32px; }
.empty { color:var(--text-3); font-size:12px; padding:20px; text-align:center; }

@media (max-width:840px){ .charts{grid-template-columns:1fr;} }
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar__logo">🧬 Factor Lab <span>Control Panel</span></div>
  <div class="topbar__meta" id="gen-meta"></div>
</div>

<div class="wrap">
  <div class="section-title">總覽</div>
  <div class="kpis" id="kpis"></div>

  <div class="section-title">圖表</div>
  <div class="charts">
    <div class="card"><div class="card__head">因子狀態</div><div class="card__body"><div id="chart-status" class="chart"></div></div></div>
    <div class="card"><div class="card__head">因子類別</div><div class="card__body"><div id="chart-category" class="chart"></div></div></div>
    <div class="card"><div class="card__head">文獻來源</div><div class="card__body"><div id="chart-lit" class="chart"></div></div></div>
    <div class="card"><div class="card__head">辯論裁決</div><div class="card__body"><div id="chart-decision" class="chart"></div></div></div>
  </div>

  <div class="section-title">因子表（點一列展開細節）</div>
  <div class="card">
    <table class="factors">
      <thead><tr>
        <th>ID</th><th>名稱</th><th>類別</th><th>狀態</th>
        <th style="text-align:right">IC</th><th style="text-align:right">IC-IR</th>
        <th style="text-align:right">Sharpe</th><th>裁決</th><th></th>
      </tr></thead>
      <tbody id="factor-tbody"></tbody>
    </table>
  </div>

  <div class="section-title">辯論記錄</div>
  <div class="card" id="debate-list"></div>

  <div class="section-title">論文洞見</div>
  <div class="card" id="insight-list"></div>

  <div class="foot" id="foot"></div>
</div>

<script>
const D = __DASHBOARD_DATA__;

const fmt = (v, d=3) => (v === null || v === undefined) ? null : Number(v).toFixed(d);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function numCell(v){
  if (v === null || v === undefined) return '<td class="num na">—</td>';
  const cls = v >= 0 ? 'pos' : 'neg';
  return `<td class="num ${cls}">${fmt(v)}</td>`;
}

// ── KPIs ──
const K = D.kpis;
const kpiDefs = [
  ['factors','因子總數',''], ['candidates','候選中','green'], ['deprecated','已棄置','amber'],
  ['sessions','辯論場次',''], ['papers','文獻','' ], ['insights','洞見',''],
  ['evidence_rows','實證紀錄',''], ['transcript_steps','辯論步驟',''],
];
document.getElementById('kpis').innerHTML = kpiDefs.map(([k,label,cls]) =>
  `<div class="kpi ${cls}"><div class="kpi__val">${K[k]}</div><div class="kpi__label">${label}</div></div>`
).join('');

// ── Charts ──
const PLOT_BG = 'rgba(0,0,0,0)';
const FONT = { color:'#9aa6b7', family:'Inter, sans-serif', size:11 };
const PALETTE = ['#5eb1ff','#c084fc','#4cc38a','#f5a524','#fb7185','#06b6d4'];
const baseLayout = (extra={}) => Object.assign({
  paper_bgcolor:PLOT_BG, plot_bgcolor:PLOT_BG, font:FONT,
  margin:{t:10,r:10,b:30,l:40}, showlegend:false,
}, extra);
const CFG = { displayModeBar:false, responsive:true };

function donut(id, obj, colorMap){
  const labels = Object.keys(obj), values = Object.values(obj);
  if (!labels.length){ document.getElementById(id).innerHTML = '<div class="empty">無資料</div>'; return; }
  const colors = labels.map((l,i)=> (colorMap && colorMap[l]) || PALETTE[i%PALETTE.length]);
  Plotly.newPlot(id, [{ type:'pie', hole:.55, labels, values,
    marker:{colors}, textinfo:'label+value', textfont:{color:'#e6edf3',size:11},
    hoverinfo:'label+value+percent' }],
    baseLayout({margin:{t:10,r:10,b:10,l:10}, showlegend:false}), CFG);
}
function bar(id, obj, color){
  const labels = Object.keys(obj), values = Object.values(obj);
  if (!labels.length){ document.getElementById(id).innerHTML = '<div class="empty">無資料</div>'; return; }
  Plotly.newPlot(id, [{ type:'bar', x:values, y:labels, orientation:'h',
    marker:{color: color || '#5eb1ff'}, text:values, textposition:'auto',
    textfont:{color:'#0a0e14'} }],
    baseLayout({margin:{t:10,r:20,b:30,l:120},
      xaxis:{gridcolor:'#1f2632',zeroline:false}, yaxis:{automargin:true}}), CFG);
}

donut('chart-status', D.charts.status_dist, {candidate:'#4cc38a', deprecated:'#e5484d', unknown:'#5b6878'});
bar('chart-category', D.charts.category_dist, '#c084fc');
donut('chart-lit', D.charts.lit_by_source);
bar('chart-decision', D.charts.decision_dist, '#f5a524');

// ── Factor table ──
const tbody = document.getElementById('factor-tbody');
tbody.innerHTML = D.factors.map((f, i) => {
  const dec = f.decision ? `<span class="badge ${f.decision}">${f.decision}</span>` : '<span class="num na">—</span>';
  return `
  <tr class="factor-row" data-idx="${i}">
    <td>${esc(f.id)}</td>
    <td class="fname">${esc(f.name)}</td>
    <td>${esc(f.category)}</td>
    <td><span class="badge ${f.status}">${esc(f.status)}</span></td>
    ${numCell(f.ic_mean)}${numCell(f.ic_ir)}${numCell(f.sharpe)}
    <td>${dec}</td>
    <td><span class="chev">▶</span></td>
  </tr>
  <tr class="detail-row"><td colspan="9"><div class="detail" id="detail-${i}"></div></td></tr>`;
}).join('');

function renderDetail(f){
  const evRows = f.evidence.length ? `
    <table class="ev-table"><thead><tr><th>市場</th><th>Rank IC</th><th>IC-IR</th><th>LS年化</th><th>計算於</th></tr></thead>
    <tbody>${f.evidence.map(e=>`<tr>
      <td>${esc(e.market)}</td><td>${fmt(e.rank_ic) ?? '—'}</td><td>${fmt(e.ic_ir) ?? '—'}</td>
      <td>${fmt(e.ls_annual) ?? '—'}</td><td>${esc((e.computed_at||'').slice(0,10))}</td></tr>`).join('')}
    </tbody></table>` : '<div class="empty">尚無 evidence 紀錄</div>';
  const reason = f.decision_reason
    ? `<div class="field__label" style="margin-top:14px">裁決理由</div>
       <div class="reason ${f.decision}">${esc(f.decision_reason)}</div>` : '';
  return `
    <div class="detail__grid">
      <div><div class="field__label">假設</div><div class="field__val">${esc(f.hypothesis) || '—'}</div></div>
      <div><div class="field__label">最大回撤</div><div class="field__val mono">${fmt(f.max_drawdown) ?? '—'}</div></div>
      <div><div class="field__label">辯論回合</div><div class="field__val mono">${f.total_rounds}</div></div>
      <div><div class="field__label">來源場次</div><div class="field__val mono">${esc(f.session_id) || '—'}</div></div>
    </div>
    <div class="field__label">公式</div>
    <div class="field__val mono">${esc(f.formula) || '—'}</div>
    ${reason}
    <div class="field__label" style="margin-top:14px">實證 (evidence)</div>
    ${evRows}
    <div class="field__label" style="margin-top:14px">筆記路徑</div>
    <div class="field__val mono">${esc(f.note_path) || '—'}</div>`;
}

tbody.querySelectorAll('.factor-row').forEach(row => {
  row.addEventListener('click', () => {
    const i = +row.dataset.idx;
    const det = document.getElementById('detail-'+i);
    const isOpen = det.classList.contains('open');
    if (!isOpen && !det.dataset.loaded){ det.innerHTML = renderDetail(D.factors[i]); det.dataset.loaded='1'; }
    det.classList.toggle('open'); row.classList.toggle('open');
  });
});

// ── Debate viewer ──
document.getElementById('debate-list').innerHTML = D.sessions.map((s, i) => `
  <div class="debate">
    <div class="debate__head" data-idx="${i}">
      <span class="chev">▶</span>
      <span class="debate__title">${esc(s.title)}</span>
      <span class="debate__counts">提案 ${s.num_proposed} · 通過 ${s.num_validated} · 棄置 ${s.num_deprecated}</span>
      <span class="debate__sid">${esc(s.session_id)}</span>
    </div>
    <div class="debate__body" id="debate-body-${i}"></div>
  </div>`).join('') || '<div class="empty">無辯論記錄</div>';

function renderDebate(s){
  const notes = s.notes ? `<div class="debate__notes">📋 ${esc(s.notes)}</div>` : '';
  const steps = s.steps.length ? s.steps.map(st => `
    <div class="step">
      <span class="step__order">${st.step_order ?? '·'}</span>
      <span class="role ${esc(st.agent_role)}">${esc(st.agent_role)}</span>
      <div class="step__main">
        <div class="step__summary">${esc(st.output_summary)}</div>
        <div class="step__meta">${esc(st.model) || 'model n/a'} · ${st.duration_seconds ?? '?'}s</div>
      </div>
    </div>`).join('') : '<div class="empty">無 transcript 步驟</div>';
  const rulings = s.rulings.length ? `
    <div class="rulings"><div class="field__label">逐因子裁決</div>
    ${s.rulings.map(r=>`<div class="ruling">
      <span class="ruling__name">${esc(r.factor_name)}</span>
      <span class="badge ${r.decision}">${esc(r.decision)}</span>
      <span class="ruling__reason">${esc(r.decision_reason)}</span>
    </div>`).join('')}</div>` : '';
  return notes + steps + rulings;
}

document.querySelectorAll('.debate__head').forEach(head => {
  head.addEventListener('click', () => {
    const i = +head.dataset.idx;
    const body = document.getElementById('debate-body-'+i);
    if (!body.dataset.loaded){ body.innerHTML = renderDebate(D.sessions[i]); body.dataset.loaded='1'; }
    body.classList.toggle('open'); head.querySelector('.chev').classList.toggle('open');
    head.querySelector('.chev').style.transform = body.classList.contains('open') ? 'rotate(90deg)' : '';
  });
});

// ── Insights ──
document.getElementById('insight-list').innerHTML = D.insights.length ? D.insights.map(x => `
  <div class="insight">
    <div class="insight__type">${esc(x.insight_type)}${x.paper_title ? ' · '+esc(x.paper_title) : ''}</div>
    <div class="insight__text">${esc(x.insight)}</div>
  </div>`).join('') : '<div class="empty">無洞見記錄</div>';

// ── Meta ──
document.getElementById('gen-meta').textContent = '產生於 ' + D.generated_at + ' · 資料來源 index.db';
document.getElementById('foot').textContent =
  `Factor Lab Control Panel · 全部數據取自 index.db · ${D.generated_at}`;
</script>
</body>
</html>
"""


def main():
    print("🔍 載入 index.db ...")
    data = load_data()
    k = data["kpis"]
    print(f"   ✓ {k['factors']} 因子 · {k['sessions']} 辯論 · {k['papers']} 文獻 · {k['evidence_rows']} evidence")

    html = HTML_TEMPLATE.replace(
        "__DASHBOARD_DATA__", json.dumps(data, ensure_ascii=False, default=str))
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   ✓ 已寫入 {OUTPUT_HTML} ({os.path.getsize(OUTPUT_HTML)/1024:.1f} KB)")

    if "--open" in sys.argv:
        webbrowser.open(f"file://{OUTPUT_HTML}")
        print("   ✓ 已開啟瀏覽器")
    else:
        print(f"   → 用瀏覽器開啟：file://{OUTPUT_HTML}")


if __name__ == "__main__":
    main()
