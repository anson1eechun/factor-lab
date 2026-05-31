"""輕量 dedup（MVP，無 embedding / pgvector）。

Cetus 正式版用 pgvector 做 hypothesis embedding 餘弦相似度；MVP 先用
詞袋餘弦（中英混合，bi-gram + 詞）比對新 idea 與 graveyard / active 提案，
門檻沿用 config 的 duplicate_cosine / similar_cosine。日後可無痛換成真 embedding。
"""
from __future__ import annotations
import re, math
from collections import Counter
from pathlib import Path
from .kb import CONFIG, VAULT

_CET = CONFIG["cetus"]


def _tokens(text: str) -> Counter:
    text = text.lower()
    words = re.findall(r"[a-z0-9]+", text)              # 英數詞
    cjk = re.findall(r"[一-鿿]", text)          # 中文字
    bigrams = ["".join(p) for p in zip(cjk, cjk[1:])]   # 中文 bi-gram
    return Counter(words + bigrams)


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    num = sum(a[t] * b[t] for t in common)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


def _corpus(rel_dir: str) -> list[tuple[str, str]]:
    """回傳該 vault 子資料夾下 [(slug, 全文)]。"""
    d = VAULT / rel_dir
    out = []
    if d.exists():
        for p in d.rglob("*.md"):
            out.append((p.stem, p.read_text(encoding="utf-8")))
    return out


def check(hypothesis: str) -> dict:
    """回傳 {status: clear|similar|duplicate, references, recommendation}。"""
    q = _tokens(hypothesis)
    dup_th = _CET["dedup"]["duplicate_cosine"]
    sim_th = _CET["dedup"]["similar_cosine"]

    pool = []
    for kind, rel in (("graveyard", _CET["pipeline_paths"]["graveyard"]),
                      ("alpha_idea", _CET["pipeline_paths"]["alpha_idea"]),
                      ("research", _CET["pipeline_paths"]["research"])):
        for slug, text in _corpus(rel):
            pool.append((kind, slug, _cosine(q, _tokens(text))))

    pool.sort(key=lambda x: x[2], reverse=True)
    refs = [{"kind": k, "slug": s, "cosine": round(c, 3)}
            for k, s, c in pool if c >= sim_th][:10]

    if not refs:
        return {"status": "clear", "references": [], "recommendation": "proceed"}
    if any(r["cosine"] >= dup_th for r in refs):
        return {"status": "duplicate", "references": refs,
                "recommendation": "reject_or_iterate"}
    return {"status": "similar", "references": refs,
            "recommendation": "proceed_with_differentiation"}
