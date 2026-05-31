"""core/stages.py 階段狀態機單元測試。

涵蓋系統把關核心：合法/非法轉換、rework 限額、審計記錄與歷史查詢。
SQLite 透過 monkeypatch 導向 tmp 檔，與正式 index.db 完全隔離。
"""
from __future__ import annotations
import pytest

import core.kb as kb
import core.stages as stages
from core.stages import transition, history, rework_used, TransitionError


@pytest.fixture(autouse=True)
def tmp_index_db(tmp_path, monkeypatch):
    """每個測試用獨立的臨時 SQLite，互不污染。"""
    monkeypatch.setattr(kb, "INDEX_DB", tmp_path / "test_index.db")
    yield


# ---------- 合法轉換 ----------

def test_full_happy_path_stage0_to_stage3():
    """stage_0 → 1 → 2 → 3 全程合法，且每步寫入審計記錄。"""
    chain = [("stage_0", "stage_1"), ("stage_1", "stage_2"), ("stage_2", "stage_3")]
    for frm, to in chain:
        transition("foo", frm, to, by_agent="arbiter", reason=f"{frm}->{to}")
    h = history("foo")
    assert [(r["from"], r["to"]) for r in h] == chain
    assert all(r["by"] == "arbiter" for r in h)


def test_any_stage_can_go_to_graveyard():
    for frm in ("stage_0", "stage_1", "stage_2", "stage_3"):
        transition(f"g_{frm}", frm, "graveyard", by_agent="arbiter", reason="killed")
    # 每個 slug 各一筆記錄
    for frm in ("stage_0", "stage_1", "stage_2", "stage_3"):
        assert history(f"g_{frm}")[-1]["to"] == "graveyard"


# ---------- 非法轉換 ----------

def test_skip_stage_is_rejected():
    """不可跳級：stage_0 → stage_2 應丟 TransitionError。"""
    with pytest.raises(TransitionError, match="非法轉換"):
        transition("skip", "stage_0", "stage_2", by_agent="arbiter", reason="cheat")


def test_graveyard_is_terminal():
    """墳場是終態，不可復活。"""
    with pytest.raises(TransitionError):
        transition("dead", "graveyard", "stage_0", by_agent="arbiter", reason="revive")


def test_illegal_transition_writes_no_record():
    """非法轉換不得留下審計痕跡。"""
    with pytest.raises(TransitionError):
        transition("noop", "stage_0", "stage_3", by_agent="arbiter", reason="x")
    assert history("noop") == []


# ---------- rework 限額 ----------

def test_rework_allowed_once_then_blocked():
    """rework 限一次：第一次成功，第二次強制擋下。"""
    transition("rw", "stage_2", "rework", by_agent="skeptic", reason="第一次退回")
    assert rework_used("rw") == 1
    with pytest.raises(TransitionError, match="rework 額度"):
        transition("rw", "stage_2", "rework", by_agent="skeptic", reason="第二次退回")
    # 被擋下後計數不應再增加
    assert rework_used("rw") == 1


def test_rework_limit_is_configurable():
    """rework_limit=2 時，第二次仍可、第三次才擋。"""
    for i in range(2):
        transition("rw2", "stage_2", "rework", by_agent="skeptic",
                   reason=f"退回{i}", rework_limit=2)
    assert rework_used("rw2") == 2
    with pytest.raises(TransitionError):
        transition("rw2", "stage_2", "rework", by_agent="skeptic",
                   reason="第三次", rework_limit=2)


def test_rework_count_is_per_slug():
    """rework 計數各 slug 獨立，不互相影響。"""
    transition("a", "stage_1", "rework", by_agent="skeptic", reason="a")
    assert rework_used("a") == 1
    assert rework_used("b") == 0


# ---------- 審計記錄完整性 ----------

def test_history_is_time_ordered_and_records_reason():
    transition("h", "stage_0", "stage_1", by_agent="proposer", reason="r1")
    transition("h", "stage_1", "rework", by_agent="skeptic", reason="r2")
    h = history("h")
    assert [r["reason"] for r in h] == ["r1", "r2"]
    assert [r["at"] for r in h] == sorted(r["at"] for r in h)


def test_unknown_slug_has_empty_history():
    assert history("never_seen") == []
    assert rework_used("never_seen") == 0
