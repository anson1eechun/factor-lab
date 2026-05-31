"""因子研究記憶模組（Paper #5：Agentic AI 啟發）

對應「記憶與策略更新」模組，記錄每一輪辯論的完整軌跡：
  - 誰提了什麼假說
  - 回測結果（IC/Sharpe）
  - Arbiter 裁決與理由
  - 防止重複探索無效方向

所有資料存於既有的 index.db，與 kb.py 共用連線。
"""

from __future__ import annotations
import sqlite3
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
INDEX_DB = Path(ROOT / "index.db")

# ── 擴充 Schema ──────────────────────────────────────────────────
MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS debate_rounds (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id    TEXT NOT NULL,        -- 辯論場次 ID
  round_num     INTEGER NOT NULL,    -- 該場次內的第幾輪
  agent_role    TEXT NOT NULL,        -- proposer/theorist/empiricist/arbiter
  factor_name   TEXT,                -- 因子名稱
  factor_formula TEXT,               -- 數學公式（如有）
  factor_category TEXT,              -- momentum/value/volatility/carry/...
  hypothesis    TEXT,                -- 完整假說文本
  ic_mean       REAL,               -- Rank-IC 均值
  ic_ir         REAL,               -- IC-IR
  sharpe        REAL,               -- 多空 Sharpe
  max_drawdown  REAL,               -- 最大回撤
  decision      TEXT,                -- validated/rejected/revise/deprecated
  decision_reason TEXT,             -- 決策理由
  created_at    TEXT
);

CREATE TABLE IF NOT EXISTS factor_registry (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  formula         TEXT,
  category        TEXT,
  status          TEXT DEFAULT 'pending',  -- active/deprecated/pending/retired
  first_proposed  TEXT,
  last_evaluated  TEXT,
  best_ic_mean    REAL,
  best_ic_ir      REAL,
  best_sharpe     REAL,
  total_rounds    INTEGER DEFAULT 0,
  note_path       TEXT,                     -- vault 筆記路徑
  fingerprint     TEXT UNIQUE,              -- name+formula 去重指紋
  created_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_debate_session ON debate_rounds(session_id, round_num);
CREATE INDEX IF NOT EXISTS idx_factor_status ON factor_registry(status);
CREATE INDEX IF NOT EXISTS idx_factor_category ON factor_registry(category);

CREATE TABLE IF NOT EXISTS paper_insights (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id        TEXT NOT NULL,
  paper_title     TEXT,
  insight_type    TEXT NOT NULL,        -- design_constraint / architecture_reference / research_direction
  insight         TEXT NOT NULL,        -- 繁體中文啟示全文
  created_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_insight_type ON paper_insights(insight_type);
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(INDEX_DB))
    conn.executescript(MEMORY_SCHEMA)
    return conn


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _factor_fingerprint(name: str, formula: str = "") -> str:
    """為因子生成去重指紋。"""
    raw = f"{name.strip().lower()}|{formula.strip()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ── 辯論回合記錄 ─────────────────────────────────────────────────

def log_round(
    *,
    session_id: str,
    round_num: int,
    agent_role: str,
    factor_name: Optional[str] = None,
    factor_formula: Optional[str] = None,
    factor_category: Optional[str] = None,
    hypothesis: Optional[str] = None,
    ic_mean: Optional[float] = None,
    ic_ir: Optional[float] = None,
    sharpe: Optional[float] = None,
    max_drawdown: Optional[float] = None,
    decision: Optional[str] = None,
    decision_reason: Optional[str] = None,
) -> int:
    """記錄一輪辯論（agent 的輸出）。回傳 row id。"""
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO debate_rounds
               (session_id, round_num, agent_role, factor_name, factor_formula,
                factor_category, hypothesis, ic_mean, ic_ir, sharpe, max_drawdown,
                decision, decision_reason, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, round_num, agent_role, factor_name, factor_formula,
             factor_category, hypothesis, ic_mean, ic_ir, sharpe, max_drawdown,
             decision, decision_reason, _now()),
        )
        return cur.lastrowid


# ── 因子註冊（反重複機制）────────────────────────────────────────

def register_factor(
    *,
    name: str,
    formula: str = "",
    category: str = "",
    status: str = "pending",
    note_path: str = "",
) -> bool:
    """將因子註冊到 registry。已存在則更新時間戳。回傳 False 表示重複。"""
    fp = _factor_fingerprint(name, formula)
    with _db() as conn:
        existing = conn.execute(
            "SELECT id, status, total_rounds FROM factor_registry WHERE fingerprint=?",
            (fp,),
        ).fetchone()
        if existing:
            # 因子已存在 → 更新 last_evaluated
            conn.execute(
                "UPDATE factor_registry SET last_evaluated=?, total_rounds=total_rounds+1 WHERE id=?",
                (_now(), existing[0]),
            )
            return False  # 表示重複
        # 新因子
        conn.execute(
            """INSERT INTO factor_registry
               (name, formula, category, status, first_proposed, last_evaluated,
                note_path, fingerprint, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, formula, category, status, _now(), _now(),
             note_path, fp, _now()),
        )
        return True


def update_factor_evidence(
    *,
    name: str,
    formula: str = "",
    ic_mean: Optional[float] = None,
    ic_ir: Optional[float] = None,
    sharpe: Optional[float] = None,
    status: Optional[str] = None,
):
    """更新因子的最佳績效數據。只更新到更好的值。"""
    fp = _factor_fingerprint(name, formula)
    with _db() as conn:
        existing = conn.execute(
            "SELECT best_ic_mean, best_ic_ir, best_sharpe FROM factor_registry WHERE fingerprint=?",
            (fp,),
        ).fetchone()
        if not existing:
            register_factor(name=name, formula=formula)
            existing = (None, None, None)

        best_ic_mean = max(
            existing[0] if existing[0] is not None else float("-inf"),
            ic_mean if ic_mean is not None else float("-inf"),
        )
        best_ic_ir = max(
            existing[1] if existing[1] is not None else float("-inf"),
            ic_ir if ic_ir is not None else float("-inf"),
        )
        best_sharpe = max(
            existing[2] if existing[2] is not None else float("-inf"),
            sharpe if sharpe is not None else float("-inf"),
        )

        updates = ["last_evaluated=?"]
        params: list = [_now()]
        if ic_mean is not None:
            updates.append("best_ic_mean=?")
            params.append(best_ic_mean)
        if ic_ir is not None:
            updates.append("best_ic_ir=?")
            params.append(best_ic_ir)
        if sharpe is not None:
            updates.append("best_sharpe=?")
            params.append(best_sharpe)
        if status is not None:
            updates.append("status=?")
            params.append(status)

        params.append(fp)
        conn.execute(
            f"UPDATE factor_registry SET {', '.join(updates)} WHERE fingerprint=?",
            params,
        )


# ── 查詢介面（給 LLM Agent 用）───────────────────────────────────

def get_active_factors(category: Optional[str] = None) -> list[dict]:
    """回傳所有 active 因子（避免重複提案）。"""
    with _db() as conn:
        if category:
            rows = conn.execute(
                """SELECT name, category, best_sharpe, best_ic_ir, status, note_path
                   FROM factor_registry WHERE status='active' AND category=?
                   ORDER BY best_sharpe DESC""",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT name, category, best_sharpe, best_ic_ir, status, note_path
                   FROM factor_registry WHERE status='active'
                   ORDER BY best_sharpe DESC""",
            ).fetchall()

    return [
        {
            "name": r[0], "category": r[1], "sharpe": r[2],
            "ic_ir": r[3], "status": r[4], "note_path": r[5],
        }
        for r in rows
    ]


def get_deprecated_factors() -> list[dict]:
    """回傳已被淘汰的因子（避免重複犯錯）。"""
    with _db() as conn:
        rows = conn.execute(
            """SELECT factor_name, factor_category, decision_reason
               FROM debate_rounds
               WHERE decision IN ('rejected', 'deprecated')
                 AND factor_name IS NOT NULL
               ORDER BY created_at DESC""",
        ).fetchall()

    return [{"name": r[0], "category": r[1], "reason": r[2] or ""} for r in rows]


def get_recent_decisions(limit: int = 10) -> list[dict]:
    """最近 N 個裁決（給下次辯論的上下文）。"""
    with _db() as conn:
        rows = conn.execute(
            """SELECT factor_name, factor_category, decision, decision_reason,
                      ic_mean, ic_ir, sharpe, created_at
               FROM debate_rounds
               WHERE decision IS NOT NULL
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    return [
        {
            "factor": r[0], "category": r[1], "decision": r[2],
            "reason": r[3], "ic_mean": r[4], "ic_ir": r[5],
            "sharpe": r[6], "when": r[7],
        }
        for r in rows
    ]


def get_session_history(session_id: str) -> list[dict]:
    """回傳某場辯論的完整軌跡。"""
    with _db() as conn:
        rows = conn.execute(
            """SELECT round_num, agent_role, factor_name, hypothesis,
                      ic_mean, ic_ir, sharpe, decision, decision_reason, created_at
               FROM debate_rounds
               WHERE session_id=?
               ORDER BY round_num, id""",
            (session_id,),
        ).fetchall()

    return [
        {
            "round": r[0], "agent": r[1], "factor": r[2], "hypothesis": r[3],
            "ic_mean": r[4], "ic_ir": r[5], "sharpe": r[6],
            "decision": r[7], "reason": r[8], "when": r[9],
        }
        for r in rows
    ]


# ── 上下文生成（給 LLM prompt 用）────────────────────────────────

def generate_context_prompt() -> str:
    """為新一輪辯論生成記憶上下文，供 LLM agent 注入系統提示。"""
    active = get_active_factors()
    deprecated = get_deprecated_factors()
    recent = get_recent_decisions(limit=5)

    lines = ["## 因子研究記憶（factor-lab memory）\n"]

    if active:
        lines.append("### 已驗證的有效因子（避免重複提案）")
        for f in active:
            lines.append(
                f"- **{f['name']}** [{f['category']}]: "
                f"Sharpe={f['sharpe']}, IC-IR={f['ic_ir']}"
            )

    if deprecated:
        lines.append("\n### 已淘汰因子（避免重複犯錯）")
        seen = set()
        for f in deprecated:
            if f['name'] not in seen:
                seen.add(f['name'])
                lines.append(f"- **{f['name']}** [{f['category']}]: {f['reason'][:120]}")

    if recent:
        lines.append("\n### 最近裁決")
        for d in recent:
            lines.append(
                f"- [{d['when']}] {d['factor']}: **{d['decision']}** "
                f"(IC={d['ic_mean']}, SR={d['sharpe']}) — {d['reason'][:100]}"
            )

    lines.append("\n### 約束")
    lines.append("- 新因子必須與上述 effective factors 低相關")
    lines.append("- 已淘汰的因子方向不可重新提案（除非有本質不同的實現方式）")
    lines.append("- 優先探索尚未覆蓋的因子類別")

    constraints = get_design_constraints()
    if constraints:
        lines.append("\n### 論文驅動的設計約束")
        for c in constraints:
            lines.append(f"- [{c['source']}] {c['constraint']}")

    return "\n".join(lines)


def factor_fingerprint_exists(name: str, formula: str = "") -> bool:
    """檢查因子是否已存在於 registry。"""
    fp = _factor_fingerprint(name, formula)
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM factor_registry WHERE fingerprint=?", (fp,)
        ).fetchone()
    return row is not None


# ── 論文啟示記錄（為辯論提供設計約束）─────────────────────────

def record_paper_insight(
    *,
    paper_id: str,
    paper_title: str = "",
    insight_type: str,
    insight: str,
) -> int:
    """記錄從論文中提煉的設計約束/架構參考/研究方向。回傳 row id。"""
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO paper_insights (paper_id, paper_title, insight_type, insight, created_at)
               VALUES (?,?,?,?,?)""",
            (paper_id, paper_title, insight_type, insight, _now()),
        )
        return cur.lastrowid


def get_design_constraints() -> list[dict]:
    """回傳所有 design_constraint 類型的論文啟示（供辯論 prompt 注入）。"""
    with _db() as conn:
        rows = conn.execute(
            """SELECT paper_id, paper_title, insight, created_at
               FROM paper_insights
               WHERE insight_type='design_constraint'
               ORDER BY created_at DESC""",
        ).fetchall()
    return [{"source": r[0], "title": r[1] or "", "constraint": r[2], "when": r[3]} for r in rows]


def get_research_directions() -> list[dict]:
    """回傳所有 research_direction 類型的論文啟示。"""
    with _db() as conn:
        rows = conn.execute(
            """SELECT paper_id, paper_title, insight, created_at
               FROM paper_insights
               WHERE insight_type='research_direction'
               ORDER BY created_at DESC""",
        ).fetchall()
    return [{"source": r[0], "title": r[1] or "", "direction": r[2], "when": r[3]} for r in rows]
