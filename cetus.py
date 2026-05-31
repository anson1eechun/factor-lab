"""Cetus MVP 薄 CLI — 把確定性操作封裝給 agent 與人類共用。

LLM 的語意判斷由 Conor/Daemon/Helen agent 做；本 CLI 只做：建 idea 檔、跑 dedup、
跑 Gate 0 機器檢查、埋進 graveyard、看某個 slug 的階段歷史。

用法：
    python cetus.py new   "<title>" --target ETH-PERP --timeframe 1h
    python cetus.py dedup "<hypothesis 一段文字>"
    python cetus.py gate0 <slug>
    python cetus.py bury  <slug> --cause gate_0_reject --by helen
    python cetus.py log   <slug>
"""
from __future__ import annotations
import argparse, datetime as dt, re, sys
from pathlib import Path

from core.kb import CONFIG, VAULT, _slug
from core import dedup, gate, stages

CET = CONFIG["cetus"]
ROOT = Path(__file__).resolve().parent
TPL = (ROOT / "templates" / "alpha-idea.md").read_text(encoding="utf-8")


def _dir(key: str) -> Path:
    d = VAULT / CET["pipeline_paths"][key]
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_new(a):
    today = dt.date.today().isoformat()
    slug = f"{today}-{_slug(a.title).replace(' ', '-')}"
    dd = dedup.check(a.title)
    refs = "\n".join(f"- [[{r['slug']}]] (cos={r['cosine']}, {r['kind']}) — 為何不一樣：[待答]"
                     for r in dd["references"]) or "- (none)"
    md = TPL.format(slug=slug, title=a.title, author="daemon",
                    created=dt.datetime.now().isoformat(timespec="seconds"),
                    direction=a.direction, target=a.target, timeframe=a.timeframe,
                    dedup_status=dd["status"], graveyard_refs=refs)
    path = _dir("alpha_idea") / f"{slug}.md"
    path.write_text(md, encoding="utf-8")
    print(f"✓ 建立 {path.relative_to(VAULT)}")
    print(f"  dedup: {dd['status']} → {dd['recommendation']}")
    for r in dd["references"]:
        print(f"    ~ {r['slug']} (cos={r['cosine']})")


def cmd_dedup(a):
    r = dedup.check(a.text)
    print(f"status={r['status']}  recommendation={r['recommendation']}")
    for x in r["references"]:
        print(f"  {x['cosine']:.3f}  [{x['kind']}] {x['slug']}")


def _find(slug: str) -> Path | None:
    for key in ("alpha_idea", "research"):
        p = _dir(key) / f"{slug}.md"
        if p.exists():
            return p
    return None


def cmd_gate0(a):
    p = _find(a.slug)
    if not p:
        sys.exit(f"找不到 {a.slug}")
    md = p.read_text(encoding="utf-8")
    m = re.search(r"dedup_status:\s*(\w+)", md)
    res = gate.gate0_machine(md, m.group(1) if m else "clear")
    print(f"soul_score={res['soul_score']}/6  機器檢查={'PASS' if res['pass_machine'] else 'FAIL'}")
    for i in res["issues"]:
        print(f"  ✗ {i}")
    print("（語意判斷 Q1 結構性 / Q3 對手方具名 由 Helen agent 接手）")


def cmd_bury(a):
    p = _find(a.slug)
    frm = "stage_0"
    if p:
        m = re.search(r"stage:\s*(\w+)", p.read_text(encoding="utf-8"))
        frm = m.group(1) if m else "stage_0"
    stages.transition(a.slug, frm, "graveyard", by_agent=a.by, reason=a.cause,
                      rework_limit=CET["rework_limit"])
    g = _dir("graveyard") / f"{a.slug}.md"
    body = (f"---\nslug: {a.slug}\noriginal_stage: {frm}\n"
            f"buried_at: {dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"cause_of_death: {a.cause}\nkilled_by: {a.by}\n---\n\n"
            f"# Why It Died\n[由 Helen 補 ≥200 字 reasoning]\n\n"
            f"# What's Reusable\n[由 Jimmy 整理可重用 factor / lesson]\n")
    if p:
        body += f"\n# Original\n\n{p.read_text(encoding='utf-8')}\n"
        p.unlink()
    g.write_text(body, encoding="utf-8")
    print(f"⚰ 已埋葬 {a.slug} ({frm} → graveyard, cause={a.cause})")


def cmd_log(a):
    for h in stages.history(a.slug):
        print(f"  {h['at']}  {h['from']} → {h['to']}  by {h['by']}  ({h['reason']})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("title")
    n.add_argument("--target", default="BTC-PERP"); n.add_argument("--timeframe", default="1h")
    n.add_argument("--direction", default="long-short"); n.set_defaults(f=cmd_new)
    d = sub.add_parser("dedup"); d.add_argument("text"); d.set_defaults(f=cmd_dedup)
    g = sub.add_parser("gate0"); g.add_argument("slug"); g.set_defaults(f=cmd_gate0)
    b = sub.add_parser("bury"); b.add_argument("slug")
    b.add_argument("--cause", default="gate_0_reject"); b.add_argument("--by", default="helen")
    b.set_defaults(f=cmd_bury)
    l = sub.add_parser("log"); l.add_argument("slug"); l.set_defaults(f=cmd_log)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
