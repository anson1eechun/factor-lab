"""core.data — 統一鏈上資料載入層（Phase 0 地基）。

權威資料：`data/onchain/*.json`，每檔 = 內嵌 metadata + `data: [{timestamp(ms), value, last_modified}]`
（來源 ErcinDedeoglu，CC BY 4.0；日線、約 3.5 年）。本層取代各 signal 內各自 `_load()` 的重複樣板。

canonical signal 契約見 `docs/SIGNAL_CONTRACT.md`：
    signal/strategy() -> pandas.Series(position, date-indexed, ∈[-1,1])
    harness（scripts/onchain_eval.py）對齊 BTC 價、lag≥1（鏈上有回報延遲，無前視）、扣成本。

設計：只有 `load()` 需要 pandas（延後匯入）；`available()/meta()/profile_basic()/data_dictionary()`
純標準庫，base python3 即可跑（factor-lab 重活一律 `uv run --with pandas ...`）。
"""
from __future__ import annotations
import json, functools, datetime as _dt
import statistics as _st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONCHAIN = ROOT / "data" / "onchain"

_META_KEYS = ("name", "description", "category", "data_type", "granularity",
              "trading_signal", "first_data_date", "last_data_date", "update_frequency")


def available() -> list[str]:
    """所有可用鏈上序列檔名 stem（如 'btc_coinbase_premium_gap'）。"""
    return sorted(p.stem for p in ONCHAIN.glob("*.json"))


def _resolve(name: str) -> Path:
    """name 容錯：'coinbase_premium_gap' / 'btc_coinbase_premium_gap' / 帶 .json 皆可。"""
    stem = name.removesuffix(".json")
    for cand in (stem, f"btc_{stem}"):
        p = ONCHAIN / f"{cand}.json"
        if p.exists():
            return p
    hits = [p for p in ONCHAIN.glob("*.json") if stem in p.stem]
    if len(hits) == 1:
        return hits[0]
    raise FileNotFoundError(f"找不到鏈上序列 {name!r}；可用：{available()}")


@functools.lru_cache(maxsize=64)
def _raw(name: str) -> tuple[dict, tuple[tuple[int, float], ...]]:
    """(metadata, ((timestamp_ms, value), ...))，按時間升冪、同 ts 取最後。純標準庫。"""
    doc = json.loads(_resolve(name).read_text(encoding="utf-8"))
    if isinstance(doc, list):
        meta_d, arr = {}, doc
    else:
        meta_d = {k: v for k, v in doc.items() if k != "data"}
        arr = doc.get("data", [])
    seen: dict[int, float] = {}
    for row in arr:
        v = row.get("value")
        if v is None:
            continue
        seen[int(row["timestamp"])] = float(v)
    return meta_d, tuple(sorted(seen.items()))


def meta(name: str) -> dict:
    """該序列的 metadata（name/description/category/granularity/trading_signal/日期範圍…）。"""
    m, _ = _raw(name)
    return {k: m.get(k) for k in _META_KEYS}


def load(name: str):
    """載入一條鏈上序列 → date-indexed pandas.Series(value)，日頻、升冪、去重。
    不做 lag / 標準化（那是 signal 與 harness 的職責，見 docs/SIGNAL_CONTRACT.md）。"""
    import pandas as pd
    _, pairs = _raw(name)
    idx = pd.to_datetime([ts for ts, _ in pairs], unit="ms").floor("D")
    s = pd.Series([v for _, v in pairs], index=idx, dtype="float64")
    s.name = _resolve(name).stem
    return s


def profile_basic(name: str) -> dict:
    """便宜的描述統計（不碰 Phase 1 的 signal-model 選擇）：n、日期範圍、min/max/mean、
    有無負值、零佔比 — 供資料字典與 Phase 1 的 data_profile 起步用。"""
    _, pairs = _raw(name)
    vals = [v for _, v in pairs]
    if not vals:
        return {"n": 0}

    def _d(ts):
        return _dt.datetime.fromtimestamp(ts / 1000, _dt.timezone.utc).date().isoformat()

    n = len(vals)
    return {
        "n": n,
        "start": _d(pairs[0][0]),
        "end": _d(pairs[-1][0]),
        "min": round(min(vals), 6),
        "max": round(max(vals), 6),
        "mean": round(_st.fmean(vals), 6),
        "has_negative": any(v < 0 for v in vals),
        "pct_zero": round(sum(1 for v in vals if v == 0) / n, 4),
    }


def data_dictionary() -> dict:
    """全部鏈上序列的資料字典：{stem: {**metadata, **profile_basic}}。Phase 1 可直接取用。"""
    return {stem: {**meta(stem), **profile_basic(stem)} for stem in available()}
