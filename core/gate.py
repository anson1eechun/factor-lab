"""Gate 的可機器檢查部分（Helen 的助手）。

Helen agent 做語意判斷（Q1 是否結構性、Q3 對手方是否具名…）；本模組做
**確定性**檢查（題數、字數、dedup 狀態、回測數字門檻），讓 Helen 的裁決有客觀骨幹。
"""
from __future__ import annotations
import re
from .kb import CONFIG

_G = CONFIG["cetus"]["gates"]

SOUL_QS = [
    "為什麼這個 alpha 現在會存在",
    "什麼會殺死它",
    "對手方是誰",
    "一句話描述",
    "資料來源",
    "Alpha 衰減速度",
]


def parse_soul_answers(md: str) -> list[str]:
    """從 alpha-idea markdown 抽出六個 Soul Question 的答案（依 ## Qn 標題切）。"""
    blocks = re.split(r"\n#{2,3}\s*Q[1-6]\b[^\n]*\n", md)
    # blocks[0] 是 Q1 之前的內容；其餘對應 Q1..Q6
    return [b.strip() for b in blocks[1:7]]


def gate0_machine(md: str, dedup_status: str) -> dict:
    """Gate 0 確定性檢查。回傳 {pass_machine, soul_score, issues}。"""
    cfg = _G["gate0"]
    answers = parse_soul_answers(md)
    issues, score = [], 0
    for i in range(6):
        ans = answers[i] if i < len(answers) else ""
        # 去掉模板提示文字 [ ... ]
        ans_clean = re.sub(r"\[[^\]]*\]", "", ans).strip()
        if len(ans_clean) >= cfg["soul_min_chars"]:
            score += 1
        else:
            issues.append(f"Q{i+1} 答案不足 {cfg['soul_min_chars']} 字")
    if dedup_status == "duplicate":
        issues.append("dedup=duplicate：與既有/已死策略高度重複")
    if not re.search(r"signal\s*=", md) and "Factor Formula" in md:
        pass  # 寬鬆：formula 由 builder 後續補
    passed = (score >= cfg["soul_min_score"] and dedup_status != "duplicate")
    return {"pass_machine": passed, "soul_score": score, "issues": issues}


def gate_backtest(metrics: dict, stage: str) -> dict:
    """Stage 2 / 3 的回測數字門檻檢查。metrics 鍵見 03-PIPELINE。"""
    cfg = _G["gate2"] if stage == "stage_2" else _G["gate3"]
    checks, issues = {}, []

    def need(key, val, op, thr, label):
        ok = (val >= thr) if op == ">=" else (val <= thr)
        checks[label] = ok
        if not ok:
            issues.append(f"{label}: {val} 未達 {op}{thr}")

    if stage == "stage_2":
        need("sharpe", metrics.get("sharpe", 0), ">=", cfg["mini_sharpe_min"], "mini_sharpe")
        need("pbo", metrics.get("pbo", 1), "<=", cfg["pbo_max"], "pbo")
        need("trades", metrics.get("trade_count", 0), ">=", cfg["trade_count_min"], "trades")
        need("dd", metrics.get("max_dd", 1), "<=", cfg["max_dd_max"], "max_dd")
    else:
        need("sharpe", metrics.get("sharpe", 0), ">=", cfg["sharpe_min"], "sharpe")
        need("oos", metrics.get("oos_sharpe", 0), ">=", cfg["oos_sharpe_min"], "oos_sharpe")
        need("pbo", metrics.get("pbo", 1), "<=", cfg["pbo_max"], "pbo")
        need("wf", metrics.get("wf_decay", 0), ">=", cfg["wf_decay_min"], "wf_decay")
        need("trades", metrics.get("trade_count", 0), ">=", cfg["trade_count_min"], "trades")
    return {"pass_machine": all(checks.values()), "checks": checks, "issues": issues}
