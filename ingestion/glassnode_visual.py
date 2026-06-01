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
    """從文章 HTML 提取所有圖表 URL 和 figcaption。"""
    log(f"Fetching HTML: {article_url}")
    req = urllib.request.Request(
        article_url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/147.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    charts = []
    # 匹配 <figure> 內的 img + figcaption
    # 策略：先找所有 figure，再在裡面找 img
    figure_pattern = re.compile(
        r'<figure[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>.*?<figcaption[^>]*>(.*?)</figcaption>.*?</figure>',
        re.DOTALL | re.IGNORECASE
    )
    for match in figure_pattern.finditer(html):
        src = match.group(1)
        caption = match.group(2).strip()
        # 清理 HTML entities
        caption = re.sub(r'<[^>]+>', '', caption)
        if is_chart_image(src):
            charts.append({"url": src, "caption": caption})

    # 也找不在 figure 內的大圖 (cover image 等)
    img_pattern = re.compile(r'<img[^>]+src="([^"]+)"[^>]*>', re.IGNORECASE)
    for match in img_pattern.finditer(html):
        src = match.group(1)
        if is_chart_image(src) and not any(c["url"] == src for c in charts):
            charts.append({"url": src, "caption": ""})

    # 去重
    seen = set()
    unique = []
    for c in charts:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)
    log(f"Found {len(unique)} chart images")
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


def gemini_analyze(image_path: Path, caption: str) -> str:
    """使用 Gemini CLI 分析圖表。

策略：
- 圖片 < 60KB: 直接 base64 data URI 嵌入 prompt（最可靠）
- 圖片 >= 60KB: 寫入 Gemini workspace 並用 Markdown 引用
"""
    import base64

    with open(image_path, "rb") as f:
        img_data = f.read()

    ext = image_path.suffix.lower()
    mime = "image/png" if ext in (".png", "") else (
        "image/webp" if ext == ".webp" else "image/jpeg"
    )

    # 若圖片不大，直接用 base64 data URI（避免 "Argument list too long"）
    if len(img_data) < 60_000:
        b64 = base64.b64encode(img_data).decode()
        data_uri = f"data:{mime};base64,{b64}"

        prompt = f"""[用繁體中文回答，不要用英文]

分析這張 Glassnode 圖表：

![]({data_uri})

圖表說明: {caption}

請簡潔分析：
1. 圖表標題/指標名稱
2. 關鍵趨勢和轉折點
3. 重要價位（如有）
4. 對比特幣/加密貨幣市場的意義

每點用 1-2 句話，總長不超過 10 行。"""

        return _run_gemini(prompt)

    # 大圖片：寫入 workspace，用 Markdown 引用
    GEMINI_TMP.mkdir(parents=True, exist_ok=True)
    gemini_path = GEMINI_TMP / image_path.name
    shutil.copy2(image_path, gemini_path)
    # 強制刷入磁碟
    try:
        fd = os.open(str(gemini_path), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except Exception:
        pass

    prompt = f"""[用繁體中文回答，不要用英文]

分析這張 Glassnode 圖表：

![chart]({gemini_path})

圖表說明: {caption}

請簡潔分析：
1. 圖表標題/指標名稱
2. 關鍵趨勢和轉折點
3. 重要價位（如有）
4. 對比特幣/加密貨幣市場的意義

每點用 1-2 句話，總長不超過 10 行。"""

    try:
        return _run_gemini(prompt)
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

    # 4. Gemini 分析每個圖表
    analyses = []
    for img in downloaded:
        log(f"  Gemini analyzing chart {img['index']}...")
        if not dry_run:
            analysis = gemini_analyze(img["path"], img["caption"])
            analyses.append({
                **img,
                "analysis": analysis,
            })
            log(f"  ✓ {analysis[:60]}...")

    # 5. 更新 .md 檔案
    # 新增「圖表分析」區段
    chart_section = "\n\n## 📊 圖表與分析\n\n"
    for item in analyses:
        chart_section += f"### 圖表 {item['index']}"
        if item["caption"]:
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
        "> ✅ 已由 Gemini Vision 分析圖表內容",
    )
    new_content = update_frontmatter(new_content, fm)
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
                    analysis = gemini_analyze(dest, c["caption"])
                    print(f"  Analysis: {analysis}")
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
