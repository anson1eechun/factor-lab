#!/usr/bin/env python3
"""
Factor-Lab Phase 2 辯論流程協調器

由主 agent (Hermes) 調用，逐步推進辯論流程。每一步產生結構化輸出，
主 agent 根據輸出決定是否繼續、修正、或呼叫 delegate_task 執行。

用法：
  python3 scripts/debate_flow.py prepare    # 準備辯論上下文
  python3 scripts/debate_flow.py status     # 查看當前進度
  python3 scripts/debate_flow.py reset      # 重置狀態
"""

from __future__ import annotations
import sys
import json
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = Path("/home/anson/Documents/Obsidian Vault/量化交易")
STATEFILE = ROOT / ".debate_state.json"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def cmd_prepare():
    """準備辯論上下文：已驗證因子、已淘汰因子、論文洞見、待提案線索。"""
    sys.path.insert(0, str(ROOT))
    from core.memory import generate_context_prompt, get_design_constraints, get_research_directions
    
    context = generate_context_prompt()
    
    # 掃描待提案線索
    paper_dir = VAULT / "06-书籍论文"
    leads = []
    if paper_dir.exists():
        for fpath in sorted(paper_dir.glob("*.md")):
            content = fpath.read_text()
            if "待提案因子線索" in content:
                leads.append(str(fpath.relative_to(VAULT)))
            elif "待提案" in content and "因子" in content:
                leads.append(str(fpath.relative_to(VAULT)))
    
    # 檢查 candidates/
    cand_dir = ROOT / "candidates"
    candidates = list(cand_dir.glob("*.md")) if cand_dir.exists() else []
    
    state = {
        "phase": "prepare",
        "timestamp": _now(),
        "context_prompt": context,
        "leads_count": len(leads),
        "leads": leads,
        "existing_candidates": len(candidates),
        "candidate_files": [str(c.relative_to(ROOT)) for c in candidates],
        "next_step": "proposer" if not candidates else "builder",
    }
    
    STATEFILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_status():
    """查看當前辯論流程狀態。"""
    if not STATEFILE.exists():
        print(json.dumps({"error": "No debate state. Run 'prepare' first."}))
        return
    
    state = json.loads(STATEFILE.read_text())
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_reset():
    """重置辯論狀態（清除 statefile）。"""
    if STATEFILE.exists():
        STATEFILE.unlink()
    print(json.dumps({"status": "reset", "message": "Debate state cleared."}))


def cmd_offer():
    """給主 agent 的結構化指令：下一步應該做什麼。"""
    if not STATEFILE.exists():
        print(json.dumps({
            "step": "prepare",
            "instruction": "Run: python3 scripts/debate_flow.py prepare",
            "reason": "No debate state exists yet. Need to prepare context first."
        }, ensure_ascii=False, indent=2))
        return
    
    state = json.loads(STATEFILE.read_text())
    phase = state.get("phase", "prepare")
    next_step = state.get("next_step", "unknown")
    
    # 為每個步驟產生 delegate_task 指令模板
    instructions = {
        "proposer": {
            "step": "proposer",
            "action": "delegate_task",
            "skill": "factor-lab-proposer",
            "goal": "基於既有因子庫，從論文洞見與待提案線索中提出 1~3 個新因子候選",
            "context_template": f"以下為當前因子研究記憶。請提出 1~3 個新的因子候選。\n\n{state.get('context_prompt', '')}\n\n待提案線索來源：\n" + "\n".join(f"- {l}" for l in state.get('leads', [])),
            "toolsets": ["terminal", "file"],
            "expected_output": "proposer 輸出含候選因子路徑 (candidates/F<id>_<name>.md) 與核心假設",
        },
        "builder": {
            "step": "builder",
            "action": "delegate_task",
            "skill": "factor-lab-builder",
            "goal": "將 proposer 提出的候選因子轉換為精確可計算的 Python 函數",
            "context_template": f"候選因子路徑：{state.get('candidate_files', [])}\n\n請為每個候選因子：\n1. 閱讀候選筆記\n2. 撰寫 core/signals/F<id>_<name>.py\n3. 執行 smoke test\n4. 更新候選筆記的計算規格",
            "toolsets": ["terminal", "file"],
            "expected_output": "builder 輸出：每個因子的實作路徑 + smoke test 結果",
        },
        "skeptic": {
            "step": "skeptic",
            "action": "delegate_task",
            "skill": "factor-lab-skeptic",
            "goal": "對 builder 實作的因子進行五維批判（資料探勘/經濟直覺/前視偏誤/重複造輪子/成本流動性）",
            "context_template": f"候選因子檔案：{state.get('candidate_files', [])}\n實作信號檔案：{state.get('signal_files', [])}\n\n請對每個因子執行五維批判，並將質疑寫入候選筆記。",
            "toolsets": ["terminal", "file"],
            "expected_output": "skeptic 輸出：每個因子的逐條質疑（寫入候選筆記 ## 質疑 段落）",
        },
        "empiricist": {
            "step": "empiricist",
            "action": "delegate_task",
            "skill": "factor-lab-empiricist",
            "goal": "用歷史行情量化因子預測力：Rank-IC、IC-IR、分組回報",
            "context_template": f"候選因子檔案：{state.get('candidate_files', [])}\n實作信號檔案：{state.get('signal_files', [])}\n\n請對每個因子執行完整實證，計算 Rank-IC / IC-IR / 分組回報，寫入候選筆記 ## 實證 段落。",
            "toolsets": ["terminal", "file"],
            "expected_output": "empiricist 輸出：每個因子的完整實證數據",
        },
        "arbiter": {
            "step": "arbiter",
            "action": "main_agent",
            "instruction": "主 agent (你) 需擔任 Arbiter 角色，綜合 skeptic 質疑 + empiricist 數據，下裁決：validated / revise / deprecated",
            "context_template": f"候選因子檔案：{state.get('candidate_files', [])}\n\n請閱讀每篇候選筆記的 ## 質疑 和 ## 實證 段落，做出裁決。",
        },
        "librarian": {
            "step": "librarian",
            "action": "delegate_task",
            "skill": "factor-lab-librarian",
            "goal": "將裁決結果歸位到 vault、去重、註冊、建連結",
            "context_template": f"裁決結果待處理。請根據每個候選筆記中的 ## 裁決 段落，執行歸位/去重/註冊操作。\n\n裁決的因子：{state.get('candidate_files', [])}",
            "toolsets": ["terminal", "file"],
            "expected_output": "librarian 輸出：每個因子的歸位結果 + registry 更新",
        },
    }
    
    step_info = instructions.get(next_step, {"error": f"Unknown next step: {next_step}"})
    print(json.dumps(step_info, ensure_ascii=False, indent=2))


def cmd_done(step: str):
    """標記某步驟完成，更新 state 到下一步。"""
    if not STATEFILE.exists():
        print(json.dumps({"error": "No debate state. Run 'prepare' first."}))
        return
    
    state = json.loads(STATEFILE.read_text())
    
    flow = ["proposer", "builder", "skeptic", "empiricist", "arbiter", "librarian"]
    
    if step not in flow:
        print(json.dumps({"error": f"Unknown step: {step}. Flow: {flow}"}))
        return
    
    try:
        idx = flow.index(step)
        next_step = flow[idx + 1] if idx + 1 < len(flow) else "complete"
    except ValueError:
        next_step = "unknown"
    
    state["phase"] = step
    state["next_step"] = next_step
    state["timestamp"] = _now()
    
    STATEFILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(json.dumps({"step_completed": step, "next_step": next_step}, ensure_ascii=False, indent=2))


def cmd_set(key: str, value: str):
    """手動設定 state 欄位。（例如記錄 candidate_files）"""
    if not STATEFILE.exists():
        print(json.dumps({"error": "No debate state. Run 'prepare' first."}))
        return
    
    state = json.loads(STATEFILE.read_text())
    try:
        state[key] = json.loads(value)
    except json.JSONDecodeError:
        state[key] = value
    
    STATEFILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(json.dumps({"set": key, "value": state[key]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: debate_flow.py <prepare|status|reset|offer|done <step>|set <key> <value>>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "prepare":
        cmd_prepare()
    elif command == "status":
        cmd_status()
    elif command == "reset":
        cmd_reset()
    elif command == "offer":
        cmd_offer()
    elif command == "done":
        if len(sys.argv) < 3:
            print("Usage: debate_flow.py done <step>")
            sys.exit(1)
        cmd_done(sys.argv[2])
    elif command == "set":
        if len(sys.argv) < 4:
            print("Usage: debate_flow.py set <key> <json_value>")
            sys.exit(1)
        cmd_set(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
