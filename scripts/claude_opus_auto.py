#!/usr/bin/env python3
"""
Claude Code Opus 4.8 MAX 自動化任務執行器
在 7:20 AM session reset 後自動操控 Claude Code TUI

執行流程:
1. Launch Claude Code with Opus MAX + bypass permissions
2. 處理 TUI 對話框（theme/trust/permissions）
3. 分階段發送任務
4. 監控輸出，等 ❯ prompt 再發下一階段
"""

import os
import sys
import pty
import time
import select
import subprocess
import signal
from datetime import datetime

# === 配置 ===
HOME = "/home/anson"
WORKDIR = "/home/anson"
LOG_FILE = "/home/anson/factor-lab/logs/claude_opus_max_auto.log"
MAX_WAIT_THINKING = 900  # 15 分鐘 thinking timeout

# Claude Code 命令
CLAUDE_CMD = "claude --model opus --effort max --dangerously-skip-permissions"

# 階段任務
PHASES = [
    {
        "name": "Phase 1: 修復標籤系統 + 缺口重分析",
        "prompt": """
先處理方法論問題，然後重新分析。步驟：

1. 掃描 /home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文/ 下所有 .md 檔案
2. 讀取每篇 YAML frontmatter 中的 tags 欄位
3. 建立標準化標籤對照表，將中英混雜的標籤統一（例如 "機器學習"→"ML/DL", "回測"→"Backtesting"）
4. 為缺少主題標籤的論文（如只標 arxiv/待精讀）補上合理的標籤
5. 用更新後的標籤重新統計各主題覆蓋率
6. 找出真正的知識缺口（差距最大的 5 個主題）
7. 將修復後的標籤分析報告寫入 /home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文/gap_analysis_v2.md

重要：實際修改檔案的 YAML frontmatter tags 欄位（用 Edit 工具），不要只寫在報告裡。"""
    },
    {
        "name": "Phase 2: 搜尋並下載論文",
        "prompt": """
現在根據 Phase 1 找出的 5 大缺口主題，搜尋並下載論文。

為每個缺口主題：
1. 到 arXiv API (https://export.arxiv.org/api/query?search_query=...) 搜尋 2024-2026 論文
2. 篩選出最相關的 2-3 篇
3. 下載 PDF 到 /home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文/<topic>_papers/<arxiv_id>.pdf
4. 如果缺口主題尚無子目錄，建立之

搜尋關鍵詞由你自己根據主題特徵設計。目標下載 10-15 篇。"""
    },
    {
        "name": "Phase 3: 分析並歸檔論文",
        "prompt": """
現在分析 Phase 2 下載的所有論文 PDF。

對每篇論文：
1. 讀取 PDF 全文
2. 提取：核心問題、方法論、關鍵發現、與量化交易的關聯
3. 建立 Obsidian 格式筆記，包含：
   - YAML frontmatter (title, date, author, source, tags)
   - 摘要
   - 核心問題
   - 方法論
   - 關鍵發現
   - 與量化交易關聯
   - 個人筆記
4. 存到 /home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文/<arxiv_id>_<short_title>.md

檔案命名格式：YYYY-MM-DD_<arxiv_id>_<簡短英文標題>.md"""
    },
    {
        "name": "Phase 4: 系統審計 + 自由探索",
        "prompt": """
現在發揮你的創造力，深入審視整個因子研究系統。

1. 讀取 /home/anson/factor-lab/ 下的核心程式碼（重點看 orchestrate.py, core/ 目錄, data/ 目錄）
2. 分析以下面向：
   - 辯論管線完整性（提案→質疑→建構→實證→裁決）
   - 資料品質控管（CCXT/Binance 資料流）
   - 回測方法論（PBO、過擬合防護）
   - 效能瓶頸
   - 缺失的關鍵組件
3. 自由發揮：你發現任何重要的問題或改進機會，請深入探討
4. 與我（Hermes Agent）對話討論你的發現 — 用自然語言
5. 最後生成完整的系統審計報告到：
   /home/anson/factor-lab/docs/system_audit_report.md

內容包括：
- 架構評估
- 漏洞清單（附嚴重性評級）
- 改進建議（附優先級）
- 未來路線圖建議
- 你發現的任何其他重要事項"""
    }
]


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def wait_for_pattern(fd, patterns, timeout=MAX_WAIT_THINKING, check_interval=2):
    """
    Monitor PTY output for patterns. Returns matched pattern name or None on timeout.
    patterns: dict of {name: bytes_pattern}
    """
    output = b""
    deadline = time.time() + timeout
    last_log_time = 0

    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], check_interval)
        if r:
            try:
                data = os.read(fd, 4096)
                if not data:
                    log("PTY closed (EOF)")
                    return "__EOF__"
                output += data
                # Log non-spinner output to file
                if time.time() - last_log_time > 10:
                    clean = data.replace(b"\r", b"\n").decode("utf-8", errors="replace")
                    # Filter out pure spinner lines
                    meaningful = [l for l in clean.split("\n") if l.strip() and not all(c in "✻✶✢·●*✽ " for c in l.strip())]
                    if meaningful:
                        log(f"Output: {meaningful[-3:]}")
                    last_log_time = time.time()
            except OSError:
                pass

        # Check for patterns
        for name, pattern in patterns.items():
            if pattern in output:
                log(f"Detected pattern: {name}")
                return name

    log(f"Timeout waiting for patterns: {list(patterns.keys())}")
    return None


def run_claude_session():
    """Main automation loop"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    log("=" * 60)
    log("Starting Claude Code Opus 4.8 MAX automation")
    log(f"Time: {datetime.now()}")
    log(f"PID: {os.getpid()}")
    log("=" * 60)

    # Prepare environment
    env = os.environ.copy()
    env["HOME"] = HOME
    env["PATH"] = f"{HOME}/.local/bin:{HOME}/.nvm/versions/node/v22.14.0/bin:{env.get('PATH', '/usr/bin')}"

    # Launch Claude Code in PTY
    log("Launching Claude Code...")
    pid, fd = pty.fork()
    
    if pid == 0:
        # Child process
        os.chdir(WORKDIR)
        os.execvpe("claude", ["claude", "--model", "opus", "--effort", "max", 
                               "--dangerously-skip-permissions"], env)
        sys.exit(1)

    # Parent process - control the TUI
    log(f"Claude Code PID: {pid}")

    try:
        # Step 1: Handle startup dialogs (theme + trust + permissions)
        log("Waiting for startup dialogs...")
        
        # Wait for initial render (theme screen or direct to prompt)
        startup = wait_for_pattern(fd, {
            "theme_dialog": b"Select theme",
            "prompt_ready": b"\xe2\x9d\xaf",  # ❯ UTF-8
            "login_dialog": b"Select login method",
            "rate_limit": b"rate-limit"
        }, timeout=30)

        if startup == "rate_limit":
            log("Rate limited! Session not reset yet. Exiting.")
            os.kill(pid, signal.SIGTERM)
            return

        if startup == "login_dialog":
            log("Login dialog detected - need browser auth. Aborting.")
            os.kill(pid, signal.SIGTERM)
            return

        if startup == "theme_dialog":
            log("Theme dialog - pressing Enter (accept default)")
            os.write(fd, b"\r")
            time.sleep(2)

            # Now handle trust dialog if it appears
            trust = wait_for_pattern(fd, {
                "trust_dialog": b"I trust this folder",
                "bypass_dialog": b"bypass permissions",
                "prompt_ready": b"\xe2\x9d\xaf",
            }, timeout=15)

            if trust == "trust_dialog":
                log("Trust dialog - pressing Enter")
                os.write(fd, b"\r")
                time.sleep(1)

                # Now permissions bypass
                bypass = wait_for_pattern(fd, {
                    "bypass_dialog": b"bypass permissions",
                    "prompt_ready": b"\xe2\x9d\xaf",
                }, timeout=10)

                if bypass == "bypass_dialog":
                    log("Permissions bypass dialog - pressing Down then Enter")
                    os.write(fd, b"\x1b[B")  # Down arrow
                    time.sleep(0.3)
                    os.write(fd, b"\r")
                    time.sleep(1)

            elif trust == "bypass_dialog":
                log("Permissions bypass dialog - pressing Down then Enter")
                os.write(fd, b"\x1b[B")
                time.sleep(0.3)
                os.write(fd, b"\r")
                time.sleep(1)

        elif startup == "bypass_dialog":
            log("Permissions bypass dialog - pressing Down then Enter")
            os.write(fd, b"\x1b[B")
            time.sleep(0.3)
            os.write(fd, b"\r")
            time.sleep(1)

        # Step 2: Execute phases
        for i, phase in enumerate(PHASES):
            log(f"\n{'='*40}")
            log(f"Starting {phase['name']}")
            log(f"{'='*40}")

            # Send the prompt
            log("Sending prompt...")
            prompt = phase["prompt"].strip()
            os.write(fd, prompt.encode("utf-8"))
            os.write(fd, b"\r")
            
            # Wait for completion (❯ prompt reappears)
            log(f"Waiting for completion (max {MAX_WAIT_THINKING}s)...")
            result = wait_for_pattern(fd, {
                "prompt_ready": b"\xe2\x9d\xaf",
                "rate_limit": b"rate-limit",
            }, timeout=MAX_WAIT_THINKING)

            if result == "rate_limit":
                log("Rate limit hit mid-session!")
                break

            if result != "prompt_ready":
                log(f"WARNING: Did not detect prompt ready for {phase['name']}. Continuing anyway.")

            log(f"Completed {phase['name']}")
            
            # Brief pause between phases
            time.sleep(3)

    except Exception as e:
        log(f"Error: {e}")
        import traceback
        log(traceback.format_exc())

    finally:
        # Clean shutdown
        log("Shutting down Claude Code...")
        os.write(fd, b"/exit\r")
        time.sleep(3)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        os.close(fd)
        
        # Wait for child
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass

    log("=" * 60)
    log("Claude Code automation session complete")
    log("=" * 60)


if __name__ == "__main__":
    run_claude_session()
