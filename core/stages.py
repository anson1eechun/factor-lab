"""Cetus 階段狀態機（MVP，檔案式）。

每個 strategy 的生命週期是嚴格 state machine：不能跳級、不能繞 Gate、rework 限一次。
狀態存在 alpha-idea / strategy 筆記的 frontmatter (`stage` 欄)，轉換寫入 index.db 的
`transitions` 表做審計。MVP 只實作到 Stage 3（不含 paper trade）。
"""
from __future__ import annotations
from enum import Enum
import datetime as dt
from .kb import db


class Stage(str, Enum):
    STAGE_0 = "stage_0"      # Alpha Idea
    STAGE_1 = "stage_1"      # Research
    STAGE_2 = "stage_2"      # Factor Dev
    STAGE_3 = "stage_3"      # Full Backtest
    STAGE_4A = "stage_4a"    # Paper Trade（MVP 後）
    STAGE_4B = "stage_4b"    # Small Capital（MVP 後）
    STAGE_5 = "stage_5"      # Live（MVP 後）
    GRAVEYARD = "graveyard"  # 終態
    REWORK = "rework"        # 被退回，限一次


VALID_TRANSITIONS: dict[str, set[str]] = {
    "stage_0": {"stage_1", "rework", "graveyard"},
    "stage_1": {"stage_2", "rework", "graveyard"},
    "stage_2": {"stage_3", "rework", "graveyard"},
    "stage_3": {"stage_4a", "rework", "graveyard"},
    "stage_4a": {"stage_4b", "rework", "graveyard"},
    "stage_4b": {"stage_5", "graveyard"},
    "stage_5": {"graveyard"},
    "rework": {"stage_0", "stage_1", "stage_2", "stage_3", "stage_4a", "graveyard"},
    "graveyard": set(),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transitions (
  slug TEXT, from_stage TEXT, to_stage TEXT,
  by_agent TEXT, reason TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS rework_count (slug TEXT PRIMARY KEY, n INTEGER);
"""


class TransitionError(Exception):
    pass


def _ensure():
    with db() as c:
        c.executescript(_SCHEMA)


def rework_used(slug: str) -> int:
    _ensure()
    with db() as c:
        r = c.execute("SELECT n FROM rework_count WHERE slug=?", (slug,)).fetchone()
    return r[0] if r else 0


def transition(slug: str, frm: str, to: str, *, by_agent: str, reason: str,
               rework_limit: int = 1) -> None:
    """驗證並記錄一次階段轉換。違法轉換或超過 rework 上限會丟 TransitionError。"""
    _ensure()
    if to not in VALID_TRANSITIONS.get(frm, set()):
        raise TransitionError(f"非法轉換 {frm} → {to}")
    if to == "rework":
        used = rework_used(slug)
        if used >= rework_limit:
            raise TransitionError(
                f"{slug} 已用完 rework 額度({rework_limit})，只能 graveyard")
    with db() as c:
        c.execute("INSERT INTO transitions VALUES (?,?,?,?,?,?)",
                  (slug, frm, to, by_agent, reason,
                   dt.datetime.now().isoformat(timespec="seconds")))
        if to == "rework":
            c.execute("INSERT INTO rework_count(slug,n) VALUES(?,1) "
                      "ON CONFLICT(slug) DO UPDATE SET n=n+1", (slug,))


def history(slug: str) -> list[dict]:
    _ensure()
    with db() as c:
        rows = c.execute(
            "SELECT from_stage,to_stage,by_agent,reason,at FROM transitions "
            "WHERE slug=? ORDER BY at", (slug,)).fetchall()
    keys = ("from", "to", "by", "reason", "at")
    return [dict(zip(keys, r)) for r in rows]
