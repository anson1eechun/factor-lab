"""Threads 爬取器 — 從 embedded JSON 提取貼文（不需登入）。

Threads 將貼文資料藏在 <script type="application/json" data-sjs> 裡，
透過 Scrapling 渲染頁面後，從 JSON blob 中提取 thread_items。

用法：
    python -m ingestion.threads_poller          # 跑 sources.yaml 中所有 threads 來源
    python -m ingestion.threads_poller --test   # 測試模式：只印出，不歸檔
"""
from __future__ import annotations
import json, re, os, sys
from pathlib import Path
from datetime import datetime

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import kb  # noqa: E402

SOURCES = yaml.safe_load((kb.ROOT / "sources.yaml").read_text(encoding="utf-8"))


def _extract_thread_items(html: str) -> list[dict]:
    """從頁面 HTML 中找出所有 thread_items。"""
    pattern = re.compile(
        r'<script[^>]*type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>',
        re.DOTALL,
    )
    all_posts = []
    for m in pattern.finditer(html):
        raw = m.group(1).strip()
        if '"thread_items"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # 遞迴搜尋 thread_items
        items = _nested_lookup("thread_items", data)
        for group in items:
            if not isinstance(group, list):
                continue
            for t in group:
                if isinstance(t, dict) and "post" in t:
                    all_posts.append(t["post"])
    return all_posts


def _nested_lookup(key: str, obj):
    """簡易 nested lookup，避免依賴第三方套件。"""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                results.append(v)
            results.extend(_nested_lookup(key, v))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_nested_lookup(key, item))
    return results


def _parse_post(post: dict) -> dict | None:
    """將 post dict 轉為 watcher 統一格式。"""
    try:
        caption = post.get("caption", {})
        text = caption.get("text", "") if isinstance(caption, dict) else str(caption or "")
        if not text.strip():
            return None

        user = post.get("user", {}) if isinstance(post.get("user"), dict) else {}
        username = user.get("username", "")
        pk = post.get("pk", "")
        code = post.get("code", "")
        taken_at = post.get("taken_at", 0)

        # 轉換 timestamp → date
        if taken_at:
            dt = datetime.fromtimestamp(taken_at)
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = "0000-00-00"

        url = f"https://www.threads.com/@{username}/post/{code}" if username and code else ""

        # 摘要：取前 200 字
        summary = text[:200].replace("\n", " ")

        return {
            "url": url,
            "title": text[:80].replace("\n", " "),
            "author": f"@{username}",
            "source": f"Threads (@{username})",
            "date": date_str,
            "summary": summary,
            "archive_as": "author",
            "full_text": text,
            "pk": pk,
        }
    except Exception:
        return None


def poll_threads(cfg: dict) -> list[dict]:
    """爬取單一 Threads 作者的最新貼文。"""
    from scrapling.fetchers import DynamicFetcher

    handle = cfg["handle"].lstrip("@")
    url = f"https://www.threads.com/@{handle}"

    try:
        page = DynamicFetcher.fetch(
            url,
            real_chrome=True,
            headless=True,
            network_idle=True,
            timeout=60000,
        )
        if page.status != 200:
            print(f"[threads:@{handle}] HTTP {page.status}")
            return []
    except Exception as e:
        print(f"[threads:@{handle}] 載入失敗: {e}")
        return []

    posts = _extract_thread_items(page.html_content)
    max_posts = cfg.get("max_posts", 10)
    results = []

    for post in posts[:max_posts]:
        parsed = _parse_post(post)
        if parsed:
            results.append(parsed)

    print(f"[threads:@{handle}] 找到 {len(results)} 篇貼文（共 {len(posts)} raw posts）")
    return results


def collect() -> list[dict]:
    """收集所有 threads 來源的新貼文。"""
    found = []
    for c in SOURCES.get("threads", []):
        try:
            found += poll_threads(c)
        except Exception as e:
            print(f"[threads:{c.get('handle')}] 失敗: {e}")
    # 去重：以 pk 為準
    seen_pks = set()
    unique = []
    for item in found:
        pk = item.get("pk", "")
        if pk and pk not in seen_pks and item["url"] and not kb.seen(item["url"]):
            seen_pks.add(pk)
            unique.append(item)
    return unique


def run(dry_run=False):
    new = collect()
    print(f"偵測到 {len(new)} 篇新貼文。")
    if dry_run:
        for i in new:
            print(f"  - [{i['source']}] {i['title'][:60]}  {i['url']}")
        return

    moc_entries, sources_seen = [], set()
    for i in new:
        body = (
            f"> ⏳ 待精讀者(Extractor agent)填入：因子/假設/公式/報告績效/啟示\n\n"
            f"**原文摘要**\n\n{i['full_text']}"
        )
        path = kb.write_note(
            archive_as=i["archive_as"],
            title=i["title"],
            author=i["author"],
            source=i["source"],
            url=i["url"],
            date=i["date"],
            body=body,
            tags=[i["source"].lower().replace(" ", "_").replace("(", "").replace(")", ""), "待精讀"],
        )
        kb.record_literature(
            url=i["url"], source=i["source"], author=i["author"],
            title=i["title"], archive_as=i["archive_as"], note_path=path,
        )
        moc_entries.append((path, i["title"][:60]))
        sources_seen.add(f"{i['source']} — threads.com")
        print(f"  ✓ 歸檔 {path.relative_to(kb.VAULT)}")

    if moc_entries:
        kb.update_moc(moc_entries, sources=sorted(sources_seen))
        print(f"已更新 MOC，新增 {len(moc_entries)} 筆。")


if __name__ == "__main__":
    run(dry_run="--test" in sys.argv or "--dry-run" in sys.argv)
