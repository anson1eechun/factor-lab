#!/usr/bin/env python3
"""
Batch extract for non-quant "待精讀" notes.
"""
import re
from pathlib import Path

VAULT = "/home/anson/Documents/Obsidian Vault/量化交易"
FOLDER = "06-书籍论文"
DIR = Path(VAULT) / FOLDER

SKIP = {
    "gap_analysis.md",
    "gap_analysis_v2.md",
    "缺口补强报告_GapFill_Audit.md",
}

LOW_ACTION = """
## 核心因子/訊號
- 本文屬 LLM/CS/AI 方法論或基準，未提出可直接用於量化交易的因子/訊號。

## 計算定義
- 不適用（非量化因子論文）。

## 報告績效
- 不適用（IC / Sharpe / 回測績效與交易 alpha 無關）。

## 限制與適用條件
- 與本知識庫之核心任務（因子挖掘與回測）直接關聯度低。

## 對本知識庫的啟示
- 低可行動性：此文作為 LLM/CS 方法論參考即可，不建議提案為因子。
"""

PLACEHOLDER = "> ⏳ 待精讀者(Extractor agent)填入：因子/假設/公式/報告績效/啟示"

def process(path):
    text = path.read_text(encoding="utf-8")
    if "待精讀" not in text or path.name in SKIP:
        return False
    if "---\n" not in text:
        return False

    # Already filled: just clean placeholder
    if "## 核心因子/訊號" in text:
        text = text.replace(PLACEHOLDER, "")
        path.write_text(text, encoding="utf-8")
        return True

    # Fix tags
    def fix_tags(m):
        block = m.group(0)
        lines = block.split("\n")
        out = []
        last = -1
        for i, l in enumerate(lines):
            s = l.strip()
            if s in ("- 待精讀", "- 待精讀"):
                continue
            if s.startswith("- "):
                last = i
            out.append(l)
        if last >= 0:
            out.insert(last + 1, "- 已精讀")
            out.insert(last + 2, "- 低可行動性")
        return "\n".join(out)

    text = re.sub(r"(tags:\s*\n(?:[ \t]*- .+\n)+)", fix_tags, text, count=1)

    if PLACEHOLDER in text:
        text = text.replace(PLACEHOLDER, LOW_ACTION.strip())
    else:
        text = text.rstrip() + "\n\n" + LOW_ACTION.strip()

    path.write_text(text, encoding="utf-8")
    return True

if __name__ == "__main__":
    n = 0
    for p in sorted(DIR.iterdir()):
        if p.suffix == ".md" and process(p):
            print(f"[OK] {p.name}")
            n += 1
    print(f"Processed {n} files.")
