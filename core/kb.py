"""知識庫存取層。

權威儲存是 Obsidian Vault 內的 Markdown 筆記；本模組維護一個 SQLite 索引
(index.db) 做去重與 IC 歷史快取，並提供把筆記寫進 vault、更新 MOC 的工具。
全部使用標準庫，無第三方相依。
"""
from __future__ import annotations
import os, re, sqlite3, hashlib, datetime as dt
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

VAULT = Path(CONFIG["kb"]["vault_root"])
INDEX_DB = Path(CONFIG["kb"]["index_db"])


# ---------- SQLite 索引 ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS literature (
  lit_id      TEXT PRIMARY KEY,      -- 內容指紋 (sha1 of url)
  source      TEXT, author TEXT, title TEXT, url TEXT,
  archive_as  TEXT, note_path TEXT,
  fetched_at  TEXT
);
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY, platform TEXT, ref TEXT,
  priority TEXT, last_polled TEXT
);
CREATE TABLE IF NOT EXISTS factors (
  id TEXT PRIMARY KEY, name TEXT, category TEXT,
  status TEXT, version INTEGER, note_path TEXT, created TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  factor_id TEXT, market TEXT, rank_ic REAL, ic_ir REAL,
  ls_annual REAL, computed_at TEXT
);
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(INDEX_DB)
    conn.executescript(SCHEMA)
    return conn


def fingerprint(url: str) -> str:
    return hashlib.sha1(url.strip().encode()).hexdigest()


def seen(url: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM literature WHERE lit_id=?", (fingerprint(url),)
        ).fetchone()
    return row is not None


def record_literature(*, url, source, author, title, archive_as, note_path):
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO literature VALUES (?,?,?,?,?,?,?,?)",
            (fingerprint(url), source, author, title, url, archive_as,
             str(note_path), dt.datetime.now().isoformat(timespec="seconds")),
        )


# ---------- 寫入 vault ----------
def _slug(text: str, maxlen: int = 60) -> str:
    text = re.sub(r"[\\/:*?\"<>|#^\[\]]", "", text).strip()
    return text[:maxlen].rstrip()


def note_dir(archive_as: str, author: str | None) -> Path:
    sub = CONFIG["kb"]["paths"][archive_as]
    d = VAULT / sub
    if archive_as == "author" and author:
        d = d / _slug(author)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_note(*, archive_as, title, author, source, url, date, body, tags) -> Path:
    """把一篇文獻/因子寫成符合 vault 慣例的 markdown，回傳路徑。"""
    d = note_dir(archive_as, author)
    fname = f"{date}_{_slug(title)}.md"
    path = d / fname
    fm = {
        "date": date, "author": author, "source": source,
        "url": url, "type": "量化交易文章" if archive_as != "factor" else "因子",
        "tags": tags,
    }
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    content = (
        f"---\n{front}\n---\n\n"
        f"# {title}\n\n"
        f"> 來源：{source} | {date}\n"
        f"> 原文連結：{url}\n\n---\n\n"
        f"{body}\n\n---\n\n"
        f"*本筆記由 factor-lab 自動採集歸檔。*\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


# ---------- 更新 MOC ----------
def _rel(path: Path) -> str:
    """vault 內相對路徑（去副檔名），給 wikilink 用。"""
    return str(path.relative_to(VAULT)).removesuffix(".md")


def update_moc(new_entries: list[tuple[Path, str]], sources: list[str] | None = None):
    """new_entries: [(note_path, 一句話摘要)]; sources: 來源行文字。"""
    moc = VAULT / CONFIG["kb"]["moc_file"]
    text = moc.read_text(encoding="utf-8")
    today = dt.date.today().isoformat()

    if new_entries:
        lines = "\n".join(
            f"- {today} | [[{_rel(p)}|{p.stem.split('_',1)[-1]}]] — {summ}"
            for p, summ in new_entries
        )
        text = _inject(text, "NEW_ENTRIES", lines, prepend=True)
    if sources:
        lines = "\n".join(f"- {s}" for s in sources)
        text = _inject(text, "SOURCES", lines, prepend=False, dedup=True)

    text = re.sub(r"(最後更新：`)[^`]*(`)", rf"\g<1>{today}\g<2>", text)
    moc.write_text(text, encoding="utf-8")


def _inject(text, marker, new_lines, *, prepend, dedup=False):
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    pat = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.S)
    m = pat.search(text)
    if not m:
        return text
    existing = m.group(1).strip("\n")
    block = (new_lines + "\n" + existing) if prepend else (existing + "\n" + new_lines)
    if dedup:
        seen_l, out = set(), []
        for ln in block.splitlines():
            if ln and ln not in seen_l:
                seen_l.add(ln); out.append(ln)
        block = "\n".join(out)
    return text[: m.start()] + f"{start}\n{block}\n{end}" + text[m.end():]
