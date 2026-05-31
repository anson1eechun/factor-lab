#!/usr/bin/env python3
"""Hermes control helper for Factor-Lab.

This script does not call an LLM. It exposes deterministic checks and prompt
generation so Hermes can drive the multi-agent workflow consistently from CLI,
chat, gateway, or cron.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment issue
    raise SystemExit("Missing dependency: pyyaml. Run `pip install -r requirements.txt`.") from exc


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
SOURCES_PATH = ROOT / "sources.yaml"
# Canonical source of truth lives in the repo and is version-controlled.
CANONICAL_SKILLS_ROOT = ROOT / "hermes" / "skills"
CANONICAL_SKILL = CANONICAL_SKILLS_ROOT / "factor-lab" / "SKILL.md"
# Runtime mirror Hermes loads from (kept in sync by scripts/install_hermes_skills.py).
INSTALLED_SKILLS_ROOT = Path.home() / ".hermes" / "skills"
HERMES_SKILL = INSTALLED_SKILLS_ROOT / "factor-lab" / "SKILL.md"

PENDING_MARKERS = ("待精讀", "待精讀者(Extractor agent)", "status: 待精讀")
LEAD_MARKER = "## 待提案因子線索"


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def load_sources() -> dict[str, Any]:
    if not SOURCES_PATH.exists():
        return {}
    return yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or {}


def vault_root(cfg: dict[str, Any]) -> Path:
    return Path(cfg["kb"]["vault_root"])


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def iter_markdown(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def pending_notes(vault: Path) -> list[Path]:
    out: list[Path] = []
    for path in iter_markdown(vault) or []:
        text = read_text(path)
        if any(marker in text for marker in PENDING_MARKERS):
            out.append(path)
    return out


def lead_notes(vault: Path) -> list[Path]:
    return [path for path in (iter_markdown(vault) or []) if LEAD_MARKER in read_text(path)]


def candidate_notes(cfg: dict[str, Any]) -> list[Path]:
    vault = vault_root(cfg)
    paths = [
        ROOT / "candidates",
        vault / cfg["kb"]["paths"]["factor"] / "candidates",
        vault / cfg["cetus"]["pipeline_paths"]["alpha_idea"],
    ]
    notes: list[Path] = []
    for directory in paths:
        if directory.exists():
            notes.extend(sorted(directory.glob("*.md")))
    return notes


ROLE_SKILLS = [
    "extractor",
    "archivist",
    "proposer",
    "builder",
    "skeptic",
    "empiricist",
    "arbiter",
    "librarian",
]
# Pipeline A/B roles plus Cetus Stage 0 gate roles (conor/daemon/helen).
AGENT_FILES = ROLE_SKILLS + ["conor", "daemon", "helen"]


def required_files() -> dict[str, Path]:
    files = {
        "config": CONFIG_PATH,
        "project_rules": ROOT / "CLAUDE.md",
        "watcher": ROOT / "ingestion" / "watcher.py",
        "debate_flow": ROOT / "scripts" / "debate_flow.py",
        "cetus": ROOT / "cetus.py",
        "canonical_skill": CANONICAL_SKILL,
    }
    for name in AGENT_FILES:
        files[f"agent_{name}"] = ROOT / ".claude" / "agents" / f"{name}.md"
    # Canonical (repo) role skills are the source of truth checked here.
    for name in ROLE_SKILLS:
        files[f"skill_factor_lab_{name}"] = (
            CANONICAL_SKILLS_ROOT / f"factor-lab-{name}" / "SKILL.md"
        )
    return files


def installed_mirror_status() -> dict[str, bool]:
    """Whether the runtime mirror under ~/.hermes/skills is present.

    Not a hard failure — `scripts/install_hermes_skills.py` syncs it.
    """
    names = ["factor-lab"] + [f"factor-lab-{r}" for r in ROLE_SKILLS]
    return {
        name: (INSTALLED_SKILLS_ROOT / name / "SKILL.md").exists() for name in names
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config()
    sources = load_sources()
    vault = vault_root(cfg)
    files = required_files()
    missing = {name: str(path) for name, path in files.items() if not path.exists()}
    pending = pending_notes(vault)
    leads = lead_notes(vault)
    candidates = candidate_notes(cfg)
    mirror = installed_mirror_status()
    mirror_missing = sorted(name for name, ok in mirror.items() if not ok)

    report = {
        "ok": not missing and vault.exists(),
        "root": str(ROOT),
        "vault": str(vault),
        "index_db": cfg["kb"].get("index_db"),
        "canonical_skills": str(CANONICAL_SKILLS_ROOT),
        "installed_skills": str(INSTALLED_SKILLS_ROOT),
        "installed_mirror_ok": not mirror_missing,
        "installed_mirror_missing": mirror_missing,
        "missing": missing,
        "counts": {
            "pending_notes": len(pending),
            "lead_notes": len(leads),
            "candidate_notes": len(candidates),
            "sources_arxiv": len(sources.get("arxiv", [])),
            "sources_rss": len(sources.get("rss", [])),
            "sources_threads": len(sources.get("threads", [])),
        },
        "env": {
            "x_bearer_token": bool(os.getenv("X_BEARER_TOKEN")),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if mirror_missing:
        print(
            "提示：執行 `python3 scripts/install_hermes_skills.py` 同步 skills 到 ~/.hermes。",
            file=sys.stderr,
        )
    return 0 if report["ok"] else 1


def cmd_pending(args: argparse.Namespace) -> int:
    cfg = load_config()
    vault = vault_root(cfg)
    notes = pending_notes(vault)
    limit = args.limit if args.limit and args.limit > 0 else len(notes)
    payload = {
        "count": len(notes),
        "shown": min(limit, len(notes)),
        "notes": [rel(path, vault) for path in notes[:limit]],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def prompt_header() -> str:
    return (
        "你正在使用 Hermes Agent 驅動 Factor-Lab。\n"
        "工作目錄固定為 `/home/anson/factor-lab`。\n"
        "先讀 `CLAUDE.md` 與 `/home/anson/.hermes/skills/factor-lab/SKILL.md`，"
        "角色 delegate 優先載入 `factor-lab-<role>` skill，再照 `.claude/agents/*.md` 分工。\n"
    )


def ingest_prompt(limit: int | None) -> str:
    limit_line = f"本輪最多處理 {limit} 篇待精讀筆記。\n" if limit else "本輪處理合理數量的待精讀筆記，避免一次改太多。\n"
    return (
        prompt_header()
        + "\n任務：跑一輪文獻採集與知識庫整理。\n"
        + limit_line
        + "\n步驟：\n"
        + "1. 執行 `python3 scripts/hermes_factor_lab.py doctor`。\n"
        + "2. 執行 `python3 -m ingestion.watcher`，若網路或來源失敗要清楚回報。\n"
        + "3. 執行 `python3 scripts/hermes_factor_lab.py pending --limit 20` 找待精讀筆記。\n"
        + "4. 對每篇選定筆記分別用 `factor-lab-extractor` 角色精讀，再用 `factor-lab-archivist` 角色歸檔；每個 delegate 只擁有自己的筆記檔。\n"
        + "5. 產出摘要：新增文獻、可信度、可行動啟示、`## 待提案因子線索`、跳過原因。\n"
    )


def research_prompt() -> str:
    return (
        prompt_header()
        + "\n任務：跑一輪因子研究辯論。\n"
        + "\n步驟：\n"
        + "1. 先清理舊狀態：`rm -f candidates/F*.md core/signals/F*.py`，再 `python3 scripts/debate_flow.py reset`。\n"
        + "   接著 `python3 scripts/debate_flow.py prepare` 與 `python3 scripts/debate_flow.py offer`。\n"
        + "   ⚠️ 已知陷阱：`offer` 回傳的 candidate/signal 陣列為空，主 agent 每步 delegate 前需手動掃描路徑並用 `set candidate_files`/`set signal_files` 傳入。詳見 hermes/skills/factor-lab/references/orchestration-runbook.md。\n"
        + "2. `factor-lab-proposer` 先讀既有因子與 `## 待提案因子線索`，提出 1-3 個候選。\n"
        + "3. `factor-lab-builder` 為候選寫 `core/signals/F<id>_<name>.py`，做 smoke test，更新候選筆記。\n"
        + "4. `factor-lab-skeptic` 與 `factor-lab-empiricist` 在 builder 後並行：前者寫五維質疑，後者跑 Rank-IC/IC-IR/分組/穩健性。\n"
        + "5. 主 agent 擔任 Arbiter，依 config 門檻與證據裁決 validated/revise/deprecated。\n"
        + "6. `factor-lab-librarian` 只在裁決後歸檔、建 wikilink、更新 index.db 與 MOC。\n"
        + "7. 回報每個因子的假設、實作檔、主要質疑、實證數字、裁決與最終路徑。\n"
    )


def new_idea_prompt(idea: str) -> str:
    return (
        prompt_header()
        + "\n任務：把下面 alpha idea 走完 Cetus Stage 0 / Gate 0。\n"
        + f"\nIdea: {idea}\n"
        + "\n步驟：\n"
        + "1. 執行 `python3 cetus.py new \"<idea>\"` 建 alpha-idea 筆記。\n"
        + "2. 從輸出取得 slug，執行 `python3 cetus.py gate0 <slug>`。\n"
        + "3. 用 daemon/helen/conor 角色完成 dedup、Soul Questions 語意判斷、pass/rework/graveyard 彙報。\n"
        + "4. 回報 alpha note 路徑、soul_score、裁決與理由。\n"
    )


def cmd_prompt(args: argparse.Namespace) -> int:
    if args.workflow == "ingest":
        print(ingest_prompt(args.limit))
    elif args.workflow == "research":
        print(research_prompt())
    elif args.workflow == "new-idea":
        if not args.idea:
            raise SystemExit("prompt new-idea requires --idea")
        print(new_idea_prompt(args.idea))
    else:  # pragma: no cover - argparse prevents this
        raise SystemExit(f"Unknown workflow: {args.workflow}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes helper for Factor-Lab workflows")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check paths, skill install, source counts, and pending workload")
    doctor.set_defaults(func=cmd_doctor)

    pending = sub.add_parser("pending", help="List Obsidian notes still marked 待精讀")
    pending.add_argument("--limit", type=int, default=20)
    pending.set_defaults(func=cmd_pending)

    prompt = sub.add_parser("prompt", help="Print a Hermes prompt for a workflow")
    prompt.add_argument("workflow", choices=["ingest", "research", "new-idea"])
    prompt.add_argument("--limit", type=int, default=None, help="Maximum pending notes for ingest prompt")
    prompt.add_argument("--idea", default="", help="Idea text for new-idea prompt")
    prompt.set_defaults(func=cmd_prompt)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
