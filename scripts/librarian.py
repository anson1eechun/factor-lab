#!/usr/bin/env python3
"""librarian.py — 辯論歸檔(取代每輪手寫的 librarian_archive_*.py)。

輸入 empirical_runs/<SID>_archive.json(主代理寫,只放判斷性文字),數字一律讀 <SID>_results.json:
{
  "session": "SIM-2026-10-01-001", "title": "...", "factor": "FSIM_X", "category": "...",
  "verdict": "REJECT|REWORK|VALIDATE|CLOSE", "decision_reason": "...", "hypothesis": "...",
  "transcripts": [{"role": "proposer", "summary": "...", "model": "..."}, ...],
  "family_status": "家族/子線狀態一句話(可省)", "closures": ["do-not-revisit 條文", ...]
}
動作:備份 index.db → 重寫本 SID 的 debate_sessions/transcripts/rounds + factors 列 →
ledger 寫 status/closure 列 → 產生因子筆記(若不存在)→ 驗證控制台 KPI。

  python scripts/librarian.py empirical_runs/<SID>_archive.json [--dry-run]
"""
import sys, os, json, shutil, sqlite3, datetime, argparse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as L

ROOT = "/home/anson/factor-lab"
ER = ROOT + "/empirical_runs/"
DB = os.environ.get("FACTORLAB_DB", ROOT + "/index.db")
FOLDER = {"VALIDATE": "validated", "REWORK": "candidates", "REJECT": "deprecated", "CLOSE": "deprecated"}
STATUS = {"VALIDATE": "candidate", "REWORK": "candidate", "REJECT": "deprecated", "CLOSE": "deprecated"}
DECISION = {"VALIDATE": "validated", "REWORK": "revise", "REJECT": "rejected", "CLOSE": "rejected"}


def headline(res):
    m = (res.get("main") or res.get(next((k for k in res if k.startswith("portfolio_")), ""))
         or res.get("screen") or {})
    return {"ic": m.get("rank_ic"), "ic_ir": m.get("ic_ir"), "sharpe": m.get("sharpe"),
            "maxdd": m.get("max_drawdown")}


def note_md(a, res, summary_path):
    h = headline(res)
    f = lambda x: "—" if x is None else f"{x:.4g}"
    return f"""---
kind: 辯論模擬
session: {a['session']}
verdict: {a['verdict']}
signal_impl: {res.get('module_path', '')}
type: {a.get('type') or res.get('type', '')}
family: {a.get('family') or res.get('family', '')}
date: {a['session'][4:14]}
---

# {a['factor']}

> **裁決:{a['verdict']}**。詳見 [[{a['session']}_debate_report]]、套餐摘要 [[{os.path.basename(summary_path)[:-3]}]]。

## 假設
{a.get('hypothesis', '')}

## 主規格
IC {f(h['ic'])} · IC-IR {f(h['ic_ir'])} · 淨 Sharpe {f(h['sharpe'])} · MaxDD {f(h['maxdd'])}

## 裁決理由
{a['decision_reason']}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive"); ap.add_argument("--dry-run", action="store_true")
    o = ap.parse_args()
    a = json.load(open(o.archive))
    sid, v = a["session"], a["verdict"]
    if v not in FOLDER:
        raise SystemExit(f"verdict 必須是 {list(FOLDER)}")
    out_dir = os.environ.get("FACTORLAB_OUT", ER)
    res_p = next((p for p in (out_dir + f"{sid}_results.json", out_dir + f"{sid}_stage0.json")
                  if os.path.exists(p)), None)
    res = json.load(open(res_p)) if res_p else {}
    h = headline(res)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    note_rel = f"{FOLDER[v]}/{a['factor']}.md"
    plan = [f"index.db 備份 → {DB}.bak-{sid}",
            f"debate_sessions/transcripts({len(a.get('transcripts', []))})/rounds 重寫 {sid}",
            f"factors {a['factor']} status={STATUS[v]} note={note_rel}",
            f"ledger +{1 + len(a.get('closures', []))} 列(status/closure)",
            f"筆記 {note_rel}" + ("(已存在,不覆寫)" if os.path.exists(f"{ROOT}/{note_rel}") else "")]
    base = {"session": sid, **{k: a.get(k) or res.get(k) or d for k, d in
                               (("family", "unknown"), ("module", "n/a"), ("type", "n/a"), ("asset", "n/a"),
                                ("params", {}))}, "tf": a.get("tf", "1d")}
    rows = [{**base, "kind": "status", "factor": f"[通道狀態] {a['factor']}", "verdict": v,
             "note": (a.get("family_status") or a["decision_reason"])[:200]}]
    rows += [{**base, "kind": "closure", "factor": f"[do-not-revisit] {x[:120]}", "verdict": "CLOSE"}
             for x in a.get("closures", [])]
    L.validate(rows)
    if o.dry_run:
        print("\n".join(plan)); return

    shutil.copy(DB, f"{DB}.bak-{sid}")
    c = sqlite3.connect(DB)
    for t in ("debate_sessions", "debate_transcripts", "debate_rounds"):
        c.execute(f"DELETE FROM {t} WHERE session_id=?", (sid,))
    c.execute("INSERT INTO debate_sessions (session_id,title,num_factors_proposed,num_factors_validated,"
              "num_factors_deprecated,started_at,completed_at,notes) VALUES (?,?,?,?,?,?,?,?)",
              (sid, a["title"], 1, int(v == "VALIDATE"), int(STATUS[v] == "deprecated"),
               sid[4:14], now[:10], f"{v}。{a['decision_reason'][:200]}"))
    for i, t in enumerate(a.get("transcripts", []), 1):
        c.execute("INSERT INTO debate_transcripts (session_id,step_order,agent_role,factor_refs,input_context,"
                  "output_summary,model,created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (sid, i, t["role"], a["factor"], t.get("input", ""), t["summary"], t.get("model", ""), now))
    c.execute("INSERT INTO debate_rounds (session_id,round_num,agent_role,factor_name,factor_formula,factor_category,"
              "hypothesis,ic_mean,ic_ir,sharpe,max_drawdown,decision,decision_reason,created_at) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (sid, 1, "arbiter", a["factor"], a.get("formula", ""), a.get("category", ""), a.get("hypothesis", ""),
               h["ic"], h["ic_ir"], h["sharpe"], h["maxdd"], DECISION[v], a["decision_reason"], now))
    c.execute("DELETE FROM factors WHERE id=?", (a["factor"],))
    c.execute("INSERT INTO factors (id,name,category,status,version,note_path,created) VALUES (?,?,?,?,?,?,?)",
              (a["factor"], a["factor"], a.get("category", ""), STATUS[v], 1, note_rel, now[:10]))
    c.commit(); c.close()

    L.append(rows)

    path = f"{ROOT}/{note_rel}"
    if not os.path.exists(path):
        open(path, "w").write(note_md(a, res, ER + f"{sid}_summary.md"))

    try:
        k = json.load(urllib.request.urlopen("http://127.0.0.1:8900/api/state", timeout=5))["kpis"]
        print("控制台 KPI:", {x: k.get(x) for x in ("sessions", "factors", "deprecated", "candidates")})
    except Exception as e:
        print("控制台未驗證:", e)
    print("\n".join(plan))


if __name__ == "__main__":
    main()
