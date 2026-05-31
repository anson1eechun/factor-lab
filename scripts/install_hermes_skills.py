#!/usr/bin/env python3
"""Sync the canonical Factor-Lab Hermes skills into the runtime locations.

Single source of truth: `factor-lab/hermes/skills/` (version-controlled).
Mount points (symlinked back to the repo):

- `~/.hermes/skills/`                              — global, loads without a profile
- `~/.hermes/profiles/deepseek/skills/research/`  — deepseek profile

Re-running is idempotent. With symlinks (default) edits to the repo are reflected
immediately; `--copy` writes real copies instead (for machines where the repo path
differs). `--check` reports drift without changing anything.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "hermes" / "skills"
TARGETS = [
    Path.home() / ".hermes" / "skills",
    Path.home() / ".hermes" / "profiles" / "deepseek" / "skills" / "research",
]
# Removed when reconciling: orchestrator was folded into the entry skill.
STALE = ["factor-lab-orchestrator"]


def canonical_dirs() -> list[Path]:
    return sorted(p for p in CANONICAL.glob("factor-lab*") if p.is_dir())


def sync_target(target: Path, copy: bool) -> list[str]:
    actions: list[str] = []
    target.mkdir(parents=True, exist_ok=True)

    for name in STALE:
        dest = target / name
        if dest.is_symlink() or dest.exists():
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            else:
                dest.unlink()
            actions.append(f"removed stale {dest}")

    for src in canonical_dirs():
        dest = target / src.name
        if dest.is_symlink() or dest.exists():
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if copy:
            shutil.copytree(src, dest)
            actions.append(f"copied {dest}")
        else:
            dest.symlink_to(src, target_is_directory=True)
            actions.append(f"linked {dest} -> {src}")
    return actions


def check_target(target: Path) -> list[str]:
    problems: list[str] = []
    for name in STALE:
        if (target / name).exists():
            problems.append(f"stale present: {target / name}")
    for src in canonical_dirs():
        dest = target / src.name
        if not dest.exists():
            problems.append(f"missing: {dest}")
        elif dest.is_symlink() and dest.resolve() != src.resolve():
            problems.append(f"wrong link: {dest} -> {dest.resolve()}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install/sync Factor-Lab Hermes skills")
    parser.add_argument("--copy", action="store_true", help="Copy instead of symlink")
    parser.add_argument("--check", action="store_true", help="Report drift, change nothing")
    args = parser.parse_args(argv)

    if not CANONICAL.exists():
        raise SystemExit(f"Canonical skills dir missing: {CANONICAL}")

    if args.check:
        ok = True
        for target in TARGETS:
            problems = check_target(target)
            if problems:
                ok = False
                print(f"[drift] {target}")
                for p in problems:
                    print(f"  - {p}")
            else:
                print(f"[ok] {target}")
        return 0 if ok else 1

    for target in TARGETS:
        print(f"# {target}")
        for action in sync_target(target, copy=args.copy):
            print(f"  {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
