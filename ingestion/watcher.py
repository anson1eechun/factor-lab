"""採集追蹤者 (Watcher) — P6 入口。

依 sources.yaml 輪詢 arXiv / RSS / X，偵測新內容，去重後抓全文摘要，
寫成符合 vault 慣例的 markdown 並更新 MOC。

純標準庫（urllib + xml.etree）：arXiv 與 RSS 都不需第三方套件即可跑。
X 區需環境變數 X_BEARER_TOKEN，否則略過。

用法：
    python -m ingestion.watcher            # 跑全部來源
    python -m ingestion.watcher --dry-run  # 只列出新項目，不寫入
"""
from __future__ import annotations
import os, sys, html, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import kb  # noqa: E402

SOURCES = yaml.safe_load((kb.ROOT / "sources.yaml").read_text(encoding="utf-8"))
UA = {"User-Agent": "factor-lab/0.1 (research; contact via local)"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _text(el, default=""):
    return (el.text or default).strip() if el is not None else default


# ---------- arXiv（Atom）----------
def poll_arxiv(cfg) -> list[dict]:
    base = "http://export.arxiv.org/api/query?"
    q = cfg["query"]
    if cfg.get("keywords"):
        kw = " OR ".join(f'all:"{k}"' for k in cfg["keywords"])
        q = f"({q}) AND ({kw})"
    params = urllib.parse.urlencode(
        {"search_query": q, "start": 0, "max_results": cfg.get("max_results", 20),
         "sortBy": "submittedDate", "sortOrder": "descending"}
    )
    root = ET.fromstring(_get(base + params))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for e in root.findall("a:entry", ns):
        url = _text(e.find("a:id", ns))
        items.append({
            "url": url, "title": _text(e.find("a:title", ns)).replace("\n", " "),
            "author": ", ".join(_text(a.find("a:name", ns))
                                 for a in e.findall("a:author", ns))[:120],
            "source": "arXiv", "date": _text(e.find("a:published", ns))[:10],
            "summary": _text(e.find("a:summary", ns)).replace("\n", " "),
            "archive_as": cfg.get("archive_as", "paper"),
        })
    return items


# ---------- RSS / Atom ----------
def poll_rss(cfg) -> list[dict]:
    root = ET.fromstring(_get(cfg["feed"]))
    items = []
    # RSS 2.0
    for it in root.iter("item"):
        link = _text(it.find("link"))
        items.append({
            "url": link, "title": _text(it.find("title")),
            "author": cfg.get("author", cfg["name"]), "source": cfg["name"],
            "date": _text(it.find("pubDate"))[:16],
            "summary": html.unescape(_text(it.find("description")))[:800],
            "archive_as": cfg.get("archive_as", "author"),
        })
    return items


# ---------- 主流程 ----------
def collect() -> list[dict]:
    found = []
    for c in SOURCES.get("arxiv", []):
        try: found += poll_arxiv(c)
        except Exception as e: print(f"[arxiv] 失敗: {e}")
    for c in SOURCES.get("rss", []):
        try: found += poll_rss(c)
        except Exception as e: print(f"[rss:{c.get('name')}] 失敗: {e}")
    for c in SOURCES.get("x", []):
        if c.get("enabled") and not os.getenv("X_BEARER_TOKEN"):
            print(f"[x:{c['handle']}] 略過：未設 X_BEARER_TOKEN")
    # 去重
    return [i for i in found if i["url"] and not kb.seen(i["url"])]


def run(dry_run=False):
    new = collect()
    print(f"偵測到 {len(new)} 筆新內容。")
    if dry_run:
        for i in new:
            print(f"  - [{i['source']}] {i['title'][:70]}  {i['url']}")
        return

    moc_entries, sources_seen = [], set()
    for i in new:
        # 精讀(Extractor) 由 LLM agent 做；此處先存原文摘要作為 body 佔位。
        body = ("> ⏳ 待精讀者(Extractor agent)填入：因子/假設/公式/報告績效/啟示\n\n"
                f"**原文摘要**\n\n{i['summary']}")
        path = kb.write_note(
            archive_as=i["archive_as"], title=i["title"], author=i["author"],
            source=i["source"], url=i["url"], date=i["date"][:10] or "0000-00-00",
            body=body, tags=[i["source"].lower().replace(" ", "_"), "待精讀"],
        )
        kb.record_literature(url=i["url"], source=i["source"], author=i["author"],
                             title=i["title"], archive_as=i["archive_as"], note_path=path)
        moc_entries.append((path, i["title"][:60]))
        sources_seen.add(f"{i['source']} — {i['url'].split('/')[2] if '//' in i['url'] else i['url']}")
        print(f"  ✓ 歸檔 {path.relative_to(kb.VAULT)}")

    if moc_entries:
        kb.update_moc(moc_entries, sources=sorted(sources_seen))
        print(f"已更新 MOC，新增 {len(moc_entries)} 筆。")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
