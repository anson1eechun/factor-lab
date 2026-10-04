#!/usr/bin/env python3
"""
Glassnode Visual Pipeline: 下載文章圖表 → Gemini 視覺分析 → 歸檔至 Obsidian vault。

用法:
    python3 -m ingestion.glassnode_visual                    # 處理全部待精讀文章
    python3 -m ingestion.glassnode_visual --dry-run          # 預覽不寫入
    python3 -m ingestion.glassnode_visual --limit 1          # 只處理最新 1 篇
"""

import os
import re
import sys
import json
import time
import shutil
import hashlib
import argparse
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

# === 常數 ===
VAULT_ROOT = Path("/home/anson/Documents/Obsidian Vault/量化交易")
GLASSNODE_DIR = VAULT_ROOT / "09-作者专题" / "Glassnode"
GEMINI_TMP = Path("/home/anson/.gemini/tmp/factor-lab")
GEMINI_HOME = "/home/anson"
GEMINI_MODEL = "gemini-2.5-pro"
# 排除的非圖表圖片（logo、頭像、縮圖等）
EXCLUDE_PATTERNS = [
    r"/size/w\d+",           # Ghost 縮圖
    r"500px-square",         # logo
    r"ChatGPT-Image",        # AI 產生圖
    r"Group-\d+",            # UI 元件
    r"favicon",
    r"\.svg$",               # SVG icons
]


def log(msg: str):
    print(f"  {msg}", flush=True)


def extract_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter，回傳 dict。"""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    current_key = None
    current_list = None
    for line in m.group(1).split("\n"):
        if line.startswith("  - "):
            if current_list is not None:
                current_list.append(line.strip("  - "))
            continue
        kv = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if kv:
            if current_list is not None and current_key:
                fm[current_key] = current_list
            current_key = kv.group(1)
            val = kv.group(2).strip().strip('"').strip("'")
            if val:
                fm[current_key] = val
                current_list = None
            else:
                current_list = []
                fm[current_key] = current_list
        else:
            current_list = None
    if current_list is not None and current_key:
        fm[current_key] = current_list
    return fm


def update_frontmatter(text: str, fm: dict) -> str:
    """將修改後的 frontmatter 寫回 markdown。"""
    m = re.match(r"^(---\s*\n)(.*?)(\n---)", text, re.DOTALL)
    if not m:
        return text

    lines = ["---"]
    for key, val in fm.items():
        if isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {val}")
    new_fm = "\n".join(lines) + "\n---"
    return re.sub(r"^---\s*\n.*?\n---", new_fm, text, count=1, flags=re.DOTALL)


def is_chart_image(url: str) -> bool:
    """過濾：只保留實際圖表，排除 logo、縮圖、UI 元件。"""
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, url):
            return False
    # 必須是圖片
    if not re.search(r"\.(png|webp|jpg|jpeg)(\?|$)", url, re.IGNORECASE):
        return False
    return True


def fetch_chart_urls(article_url: str) -> list[dict]:
    """從 Glassnode 文章提取圖表 URL 和前置段落文字（用於識別指標）。

    策略：Glassnode 文章在每個 <figure> 前的 <p> 或標題中明確描述圖表內容
    （如 "The below figure presents Total Market Cap: Raw aggregate..."）。
    提取這段文字可讓 Gemini 精確知道圖表是什麼指標。

    Returns: list of dicts with keys: url, caption, context
      - url: 圖片 URL
      - caption: figcaption 文字（通常是 "View Live Metric"，無用）
      - context: 圖表前最近一個 <p> 或 heading 的文字內容（最有用的資訊）
    """
    log(f"Fetching HTML: {article_url}")
    req = urllib.request.Request(
        article_url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/147.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # 拆成 tokens：標籤和純文字
    tokens = list(re.finditer(r'<(/?)(\w+)([^>]*)>|([^<]+)', html, re.DOTALL))
    
    # 先找所有 figure 位置及其內部 img src
    figures = []  # (html_start, img_src, caption)
    depth = 0
    in_figure = False
    figure_start = 0
    in_figcaption = False
    figcaption_text = ""
    
    for tok in tokens:
        raw = tok.group(0)
        if raw.startswith('<'):
            tag = tok.group(2).lower() if tok.group(2) else ""
            is_close = tok.group(1) == '/'
            attrs = tok.group(3) or ""
            
            if tag == 'figure' and not is_close:
                in_figure = True
                figure_start = tok.start()
            elif tag == 'figure' and is_close:
                in_figure = False
                in_figcaption = False
            elif in_figure and tag == 'img':
                src_m = re.search(r'src="([^"]+)"', attrs)
                if src_m and is_chart_image(src_m.group(1)):
                    figures.append((figure_start, src_m.group(1), figcaption_text.strip()))
            elif in_figure and tag in ('h1','h2','h3','h4','h5','h6','p','div','li'):
                # 跳過 figcaption 內的標籤
                pass
            elif tag == 'figcaption' and not is_close:
                in_figcaption = True
                figcaption_text = ""
            elif tag == 'figcaption' and is_close:
                in_figcaption = False
        elif in_figcaption:
            figcaption_text += raw
    
    # 清理 figcaption
    for i in range(len(figures)):
        figures[i] = (figures[i][0], figures[i][1], re.sub(r'<[^>]+>', '', figures[i][2]).strip())

    # 找每個 figure 前最近的 <p> 或 heading 文字
    # 搜集所有 p 和 heading 的位置和文字
    context_elements = []  # [(start_pos, text)]
    current_start = 0
    current_text = ""
    in_target = False
    in_tag = False
    
    for tok in tokens:
        raw = tok.group(0)
        if raw.startswith('<'):
            tag = tok.group(2).lower() if tok.group(2) else ""
            is_close = tok.group(1) == '/'
            
            if tag in ('p','h1','h2','h3','h4') and not is_close:
                # save previous
                if current_text.strip():
                    context_elements.append((current_start, current_text.strip()))
                current_start = tok.start()
                current_text = ""
                in_target = True
            elif tag in ('p','h1','h2','h3','h4') and is_close:
                if current_text.strip():
                    context_elements.append((current_start, current_text.strip()))
                in_target = False
                current_text = ""
            elif in_target:
                pass  # nested tag inside p/heading
        elif in_target:
            current_text += raw

    # 為每個 chart figure 找最近的前置 context
    result = []
    for fig_start, src, caption in figures:
        context = ""
        for pos, text in reversed(context_elements):
            if pos < fig_start:
                context = text
                break
        result.append({"url": src, "caption": caption, "context": context})

    # 去重
    seen = set()
    unique = []
    for c in result:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)
    log(f"Found {len(unique)} chart images")
    for i, c in enumerate(unique):
        log(f"  [{i+1}] {c['context'][:80]}...")
    return unique


def download_image(url: str, dest: Path) -> bool:
    """下載圖片到指定路徑。"""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as e:
        log(f"Download failed: {e}")
        return False


def chart_name_from_context(context: str) -> str:
    """從 HTML 原文 context 提取圖表名稱。"""
    if not context:
        return ""
    ctx = context.lower()
    if "total market cap index" in ctx:
        return "Total Market Cap Index (縮放指數, base 100)"
    elif "total market cap" in ctx:
        return "Total Market Cap: Raw Aggregate (原始聚合, USD)"
    elif "median sopr" in ctx and "index" in ctx:
        return "Median SOPR Index (縮放指數)"
    elif "median sopr" in ctx:
        return "Median SOPR: Raw Aggregate (原始中位數)"
    elif "open interest index" in ctx:
        return "Total Open Interest Index (縮放指數)"
    elif "open interest" in ctx:
        return "Total Open Interest: Raw Aggregate (原始聚合, USD)"
    elif "methodolog" in ctx or "basket selection" in ctx or ("four metrics" in ctx and "rebalancing" in ctx):
        return "方法論/框架說明圖"
    elif "endpoint" in ctx or "api" in ctx or ("raw and index" in ctx):
        return "API 端點架構圖"
    return ""


def gemini_analyze(image_path: Path, caption: str, article_title: str = "", chart_name: str = "", chart_context: str = "") -> str:
    """使用 Gemini CLI 分析圖表。

    策略：
    - 圖片 < 60KB: 直接 base64 data URI 嵌入 prompt（最可靠）
    - 圖片 >= 60KB: 寫入 Gemini workspace 並用 Markdown 引用

    chart_name: 已從 HTML 原文辨識的圖表名稱（如 "Total Market Cap: Raw Aggregate"）
        傳入後直接使用，不重新解析。若為空則嘗試從 chart_context 提取。
    article_title: 文章標題
    chart_context: 文章原文中對此圖表的描述（HTML <p> 標籤文字）
        輔助 Gemini 理解圖表脈絡，非用來辨識圖表名稱。
    """
    import base64

    with open(image_path, "rb") as f:
        img_data = f.read()

    ext = image_path.suffix.lower()
    mime = "image/png" if ext in (".png", "") else (
        "image/webp" if ext == ".webp" else "image/jpeg"
    )

    # 若未傳入 chart_name，從 chart_context 提取（向後相容）
    if not chart_name and chart_context:
        chart_name = chart_name_from_context(chart_context)

    # 建構上下文提示
    context_parts = []
    if article_title:
        context_parts.append(f"文章: {article_title}")
    if chart_name:
        context_parts.append(f"圖表: {chart_name}")
    if chart_context and chart_context != chart_name:
        # 只有當 chart_context 不同於 chart_name 時才附加原文（避免重複）
        ctx_short = chart_context[:300] + ("..." if len(chart_context) > 300 else "")
        context_parts.append(f"原文說明: {ctx_short}")
    context_str = "\n".join(context_parts) if context_parts else ""

    _build_prompt = lambda img_ref: f"""用繁體中文回答，不要用英文。

{context_str}

這張圖表的名稱和指標已由文章原文確認，請直接分析其視覺內容：

{img_ref}

重要: 圖表名稱已在上方標示。你必須直接使用該名稱，不要將其辨識為 MVRV/Mayer Multiple/SOPR/Realized Price 等其他指標。

請簡潔分析：
1. 關鍵趨勢和轉折點（指出時間段）
2. 重要價位或數值（如有）
3. 對加密貨幣市場的意義

每點 1-2 句話，總長不超過 10 行。"""

    # 若圖片不大，直接用 base64 data URI
    if len(img_data) < 60_000:
        b64 = base64.b64encode(img_data).decode()
        data_uri = f"data:{mime};base64,{b64}"
        return _run_gemini(_build_prompt(f"![]({data_uri})"))

    # 大圖片：寫入 workspace，用 Markdown 引用
    GEMINI_TMP.mkdir(parents=True, exist_ok=True)
    gemini_path = GEMINI_TMP / image_path.name
    shutil.copy2(image_path, gemini_path)
    try:
        fd = os.open(str(gemini_path), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except Exception:
        pass

    try:
        return _run_gemini(_build_prompt(f"![chart]({gemini_path})"))
    finally:
        try:
            gemini_path.unlink(missing_ok=True)
        except Exception:
            pass


def _run_gemini(prompt: str) -> str:
    """執行 Gemini CLI，回傳乾淨輸出。"""
    cmd = [
        "gemini",
        "-p", prompt,
        "-m", GEMINI_MODEL,
        "--yolo",
    ]

    env = os.environ.copy()
    env["HOME"] = GEMINI_HOME

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        output = result.stdout.strip()
        # 過濾掉 Gemini CLI 的噪音輸出
        lines = []
        skip_prefixes = [
            "Ripgrep is not available",
            "Error executing tool",
            "I am sorry",
        ]
        for line in output.split("\n"):
            if any(line.startswith(p) for p in skip_prefixes):
                continue
            lines.append(line)
        return "\n".join(lines).strip()
    except subprocess.TimeoutExpired:
        return "⚠️ Gemini 分析逾時"
    except Exception as e:
        return f"⚠️ Gemini 分析錯誤: {e}"


def process_note(note_path: Path, dry_run: bool = False, force: bool = False) -> bool:
    """處理一篇 Glassnode 筆記：下載圖表 → 分析 → 更新。"""
    note_name = note_path.stem
    log(f"\n{'='*60}")
    log(f"Processing: {note_name}")

    with open(note_path, "r") as f:
        content = f.read()

    fm = extract_frontmatter(content)
    article_url = fm.get("url", "")
    if not article_url:
        log("No URL in frontmatter, skipping")
        return False

    # 檢查是否已處理過（--force 可跳過）
    if not force and "已精讀" in fm.get("tags", []):
        log("Already processed (已精讀), skipping")
        return False

    # 提取文章標題（從 h1 heading 或檔名）
    body_text = re.sub(r'^---.*?---', '', content, flags=re.DOTALL).strip()
    title_match = re.search(r'^#\s+(.+)', body_text, re.MULTILINE)
    article_title = title_match.group(1).strip() if title_match else note_name.replace('_', ' ')

    # 1. 提取圖表 URL
    charts = fetch_chart_urls(article_url)
    if not charts:
        log("No charts found, skipping")
        return False

    # 2. 建立 assets 目錄
    safe_name = re.sub(r'[^\w\-]', '_', note_name)[:60]
    assets_dir = GLASSNODE_DIR / "assets" / safe_name
    assets_dir_rel = f"assets/{safe_name}"

    # 3. 下載圖表
    downloaded = []
    for i, chart in enumerate(charts):
        ext = "png" if ".png" in chart["url"].lower() else "webp"
        fname = f"chart_{i+1:02d}.{ext}"
        dest = assets_dir / fname
        rel_path = f"{assets_dir_rel}/{fname}"

        log(f"[{i+1}/{len(charts)}] {chart.get('caption','')[:40]}...")
        if not dry_run:
            if download_image(chart["url"], dest):
                downloaded.append({
                    "path": dest,
                    "rel_path": rel_path,
                    "caption": chart.get("caption", ""),
                    "index": i + 1,
                })

    if not downloaded:
        log("No images downloaded")
        return False

    # 4. Gemini 視覺分析 —— 強制注入圖表名稱，不讓模型自己猜
    #    從 HTML 前置段落提取圖表名稱（chart_name_from_context），
    #    然後在 Gemini prompt 中明確宣告「這張圖是 X」，杜絕 MVRV 偏見
    analyses = []
    for img in downloaded:
        idx = img["index"] - 1  # 0-based into charts list
        chart_ctx = charts[idx].get("context", "") if idx < len(charts) else ""
        chart_name = chart_name_from_context(chart_ctx)
        
        if dry_run:
            analysis = f"[DRY RUN] {chart_name or 'Unknown'}"
        else:
            if chart_name:
                # 文章原文已清楚標示圖表名稱 → 傳給 Gemini，讓它分析視覺內容
                log(f"    Gemini analyzing chart {img['index']} ({chart_name})...")
                analysis = gemini_analyze(
                    img["path"],
                    img.get("caption", ""),
                    article_title=article_title,
                    chart_name=chart_name,     # 已辨識的圖表名稱
                    chart_context=chart_ctx,    # 原始 HTML 段落（輔助脈絡）
                )
            else:
                # 無法從 HTML 辨識圖表名稱 → 用 article_title 給 Gemini 最少脈絡
                log(f"    Gemini analyzing chart {img['index']} (no context)...")
                analysis = gemini_analyze(
                    img["path"],
                    img.get("caption", ""),
                    article_title=article_title,
                    chart_context=chart_ctx,
                )
            if not analysis or analysis.startswith("⚠️"):
                # Gemini 失敗 → fallback 回 HTML 段落的純文字說明
                log(f"    Gemini failed, using HTML context fallback")
                analysis = f"**{chart_name or '圖表'}**\n\n{chart_ctx}" if chart_name else chart_ctx
        
        analyses.append({
            **img,
            "analysis": analysis,
            "chart_name": chart_name,
        })
        log(f"  ✓ {chart_name or 'Unknown'}")

    # 5. 更新 .md 檔案
    # 更新圖表分析區段
    chart_section = "\n\n## 📊 圖表與分析\n\n"
    for item in analyses:
        name = item.get("chart_name", "")
        if name:
            chart_section += f"### 圖表 {item['index']}：{name}\n\n"
        else:
            chart_section += f"### 圖表 {item['index']}"
            if item["caption"] and item["caption"] != "View Live Metric":
                chart_section += f"：{item['caption']}"
            chart_section += "\n\n"
        chart_section += f"![[{item['rel_path']}]]\n\n"
        chart_section += f"> {item['analysis']}\n\n"

    # 更新 frontmatter tags
    old_tags = fm.get("tags", [])
    if isinstance(old_tags, list):
        new_tags = ["已精讀" if t == "待精讀" else t for t in old_tags]
        if "已精讀" not in new_tags:
            new_tags.append("已精讀")
        fm["tags"] = new_tags

    # 組合
    # 替換「待精讀者」佔位符
    new_content = content
    new_content = new_content.replace(
        "> ⏳ 待精讀者(Extractor agent)填入：因子/假設/公式/報告績效/啟示",
        "> ✅ 已使用文章原文辨識圖表名稱，交由 Gemini 視覺分析圖表內容",
    )
    new_content = update_frontmatter(new_content, fm)
    # 移除既有的圖表與分析區段（避免 --force 重複跑追加到舊內容）
    new_content = re.sub(r'\n## 📊 圖表與分析\n.*', '', new_content, flags=re.DOTALL)
    new_content += chart_section

    if not dry_run:
        with open(note_path, "w") as f:
            f.write(new_content)
        log(f"✓ Updated note: {note_path}")

    log(f"✓ Done: {len(downloaded)} charts, {len(analyses)} analyses")
    return True


def find_notes() -> list[Path]:
    """掃描 vault 中所有 Glassnode 筆記。"""
    if not GLASSNODE_DIR.exists():
        return []
    notes = sorted(GLASSNODE_DIR.glob("*.md"))
    return [n for n in notes if n.name != "Glassnode.md"]


def main():
    parser = argparse.ArgumentParser(description="Glassnode Visual Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="預覽模式，不下載不寫入")
    parser.add_argument("--limit", type=int, default=0, help="只處理前 N 篇（0=全部）")
    parser.add_argument("--force", action="store_true", help="強制重新處理已精讀的")
    parser.add_argument("--url", type=str, help="手動指定單一文章 URL 測試")
    args = parser.parse_args()

    # 確保 Gemini tmp 目錄存在
    GEMINI_TMP.mkdir(parents=True, exist_ok=True)

    if args.url:
        # 手動測試模式
        charts = fetch_chart_urls(args.url)
        print(f"\nFound {len(charts)} charts:")
        for i, c in enumerate(charts):
            print(f"  [{i+1}] {c['caption'][:60]} -> {c['url'][:80]}...")

        if not args.dry_run and charts:
            safe_name = re.sub(r'[^\w\-]', '_', args.url.split("/")[-1][:60])
            assets_dir = GLASSNODE_DIR / "assets" / safe_name
            for i, c in enumerate(charts):
                ext = "png" if ".png" in c["url"].lower() else "webp"
                dest = assets_dir / f"chart_{i+1:02d}.{ext}"
                if download_image(c["url"], dest):
                    print(f"  ✓ Downloaded: {dest}")
                    chart_ctx = c.get("context", "")
                    chart_name = chart_name_from_context(chart_ctx)
                    print(f"  Name: {chart_name or 'Unknown'}")
                    if chart_ctx:
                        print(f"  Context: {chart_ctx[:200]}...")
        return

    # 掃描全部筆記
    notes = find_notes()
    log(f"Found {len(notes)} Glassnode notes in vault")

    if args.limit > 0:
        notes = notes[: args.limit]

    processed = 0
    for note_path in notes:
        try:
            if process_note(note_path, dry_run=args.dry_run, force=args.force):
                processed += 1
        except Exception as e:
            log(f"✗ Error: {e}")
            continue

    log(f"\n{'='*60}")
    log(f"Summary: {processed}/{len(notes)} notes processed")


if __name__ == "__main__":
    main()
