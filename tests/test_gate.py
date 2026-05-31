"""core/gate.py 機器檢查單元測試。

涵蓋 Gate 0（Soul Question 字數/題數/dedup）與 Gate 2/3 回測門檻。
門檻一律從 config.yaml（CONFIG）取得，避免在測試中寫死數字而再次造成漂移。
"""
from __future__ import annotations
import pytest

from core.kb import CONFIG
from core.gate import gate0_machine, gate_backtest, parse_soul_answers

_G = CONFIG["cetus"]["gates"]
MIN_CHARS = _G["gate0"]["soul_min_chars"]
MIN_SCORE = _G["gate0"]["soul_min_score"]

LONG = "結" * (MIN_CHARS + 10)      # 通過字數門檻
SHORT = "短" * (MIN_CHARS - 5)      # 未達字數門檻（仍 > 0）

SOUL_TITLES = [
    "為什麼這個 alpha 現在會存在", "什麼會殺死它", "對手方是誰",
    "一句話描述", "資料來源", "Alpha 衰減速度",
]


def make_md(answers: list[str]) -> str:
    """組出含六個 Soul Question 標題的 alpha-idea markdown。"""
    parts = ["# Alpha Idea: test\n"]
    for i, (t, a) in enumerate(zip(SOUL_TITLES, answers), 1):
        parts.append(f"\n## Q{i} {t}\n{a}\n")
    return "".join(parts)


# ---------- parse_soul_answers ----------

def test_parse_extracts_six_answers():
    md = make_md([f"答案{i}" for i in range(6)])
    answers = parse_soul_answers(md)
    assert len(answers) == 6
    assert answers[0].startswith("答案0")
    assert answers[5].startswith("答案5")


# ---------- Gate 0 ----------

def test_gate0_all_long_and_clear_passes():
    res = gate0_machine(make_md([LONG] * 6), dedup_status="clear")
    assert res["pass_machine"] is True
    assert res["soul_score"] == 6
    assert res["issues"] == []


def test_gate0_passes_at_exactly_min_score():
    """剛好 MIN_SCORE 題達標即通過（其餘題短）。"""
    answers = [LONG] * MIN_SCORE + [SHORT] * (6 - MIN_SCORE)
    res = gate0_machine(make_md(answers), dedup_status="clear")
    assert res["soul_score"] == MIN_SCORE
    assert res["pass_machine"] is True


def test_gate0_fails_below_min_score():
    answers = [LONG] * (MIN_SCORE - 1) + [SHORT] * (6 - MIN_SCORE + 1)
    res = gate0_machine(make_md(answers), dedup_status="clear")
    assert res["soul_score"] == MIN_SCORE - 1
    assert res["pass_machine"] is False
    assert any("不足" in i for i in res["issues"])


def test_gate0_duplicate_blocks_even_if_all_long():
    """dedup=duplicate 即使六題全達標也不得通過。"""
    res = gate0_machine(make_md([LONG] * 6), dedup_status="duplicate")
    assert res["pass_machine"] is False
    assert any("duplicate" in i for i in res["issues"])


def test_gate0_strips_template_placeholders():
    """純模板提示文字 [ ... ] 去除後視為空答案，不計分。"""
    placeholder = "[" + "在此填寫" * 20 + "]"   # 去括號後為空
    res = gate0_machine(make_md([placeholder] * 6), dedup_status="clear")
    assert res["soul_score"] == 0
    assert res["pass_machine"] is False


# ---------- Gate 2 / 3 回測門檻 ----------

def _passing_metrics(stage: str) -> dict:
    """從 config 邊界值組出剛好通過的 metrics（門檻為含等號比較）。"""
    if stage == "stage_2":
        c = _G["gate2"]
        return {"sharpe": c["mini_sharpe_min"], "pbo": c["pbo_max"],
                "trade_count": c["trade_count_min"], "max_dd": c["max_dd_max"]}
    c = _G["gate3"]
    return {"sharpe": c["sharpe_min"], "oos_sharpe": c["oos_sharpe_min"],
            "pbo": c["pbo_max"], "wf_decay": c["wf_decay_min"],
            "trade_count": c["trade_count_min"]}


@pytest.mark.parametrize("stage", ["stage_2", "stage_3"])
def test_backtest_passes_at_boundary(stage):
    res = gate_backtest(_passing_metrics(stage), stage)
    assert res["pass_machine"] is True, res["issues"]
    assert all(res["checks"].values())
    assert res["issues"] == []


@pytest.mark.parametrize("stage", ["stage_2", "stage_3"])
def test_backtest_fails_on_low_sharpe(stage):
    m = _passing_metrics(stage)
    m["sharpe"] -= 0.5
    res = gate_backtest(m, stage)
    assert res["pass_machine"] is False
    assert res["checks"]["mini_sharpe" if stage == "stage_2" else "sharpe"] is False


@pytest.mark.parametrize("stage", ["stage_2", "stage_3"])
def test_backtest_fails_on_high_pbo(stage):
    m = _passing_metrics(stage)
    m["pbo"] += 0.5
    res = gate_backtest(m, stage)
    assert res["pass_machine"] is False
    assert res["checks"]["pbo"] is False


def test_backtest_missing_metrics_use_failing_defaults():
    """metrics 缺鍵時應以保守預設值（不通過），不得拋例外。"""
    res = gate_backtest({}, "stage_3")
    assert res["pass_machine"] is False


def test_gate3_checks_oos_and_wf_decay_unlike_gate2():
    """Gate 3 多了 oos_sharpe / wf_decay 檢查項，Gate 2 沒有。"""
    g3 = gate_backtest(_passing_metrics("stage_3"), "stage_3")["checks"]
    g2 = gate_backtest(_passing_metrics("stage_2"), "stage_2")["checks"]
    assert "oos_sharpe" in g3 and "wf_decay" in g3
    assert "oos_sharpe" not in g2 and "wf_decay" not in g2
