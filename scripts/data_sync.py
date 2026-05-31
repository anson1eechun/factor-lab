"""
資料同步管線：Binance REST → Parquet (zstd) 增量儲存，含資料驗證。
無 ccxt 時直接用 CryptoAdapter 的 binance_rest 邏輯 + 自建分頁。

Usage:
  python scripts/data_sync.py --fetch BTC/USDT 1d
  python scripts/data_sync.py --fetch ETH/USDT 1d
  python scripts/data_sync.py --backfill BTC/USDT 1d --days 365
  python scripts/data_sync.py --validate BTC/USDT 1d
  python scripts/data_sync.py --fetch-all
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

import polars as pl

# ---------------------------------------------------------------------------
# 路徑常數
# ---------------------------------------------------------------------------
BASE_DIR = Path("/home/anson/factor-lab")
DATA_DIR = BASE_DIR / "data"

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000  # Binance klines max per request

TF_MAP = {"1d": "1d", "1h": "1h", "4h": "4h", "1w": "1w", "1M": "1M"}
TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000,
    "1d": 86_400_000, "1w": 604_800_000, "1M": 2_592_000_000,
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sym_to_filename(symbol: str) -> str:
    """BTC/USDT → btc"""
    return symbol.replace("/", "").lower()


def parquet_path(symbol: str, timeframe: str) -> Path:
    """Returns data/btc_1d.parquet"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{sym_to_filename(symbol)}_{timeframe}.parquet"
    return DATA_DIR / name


def fetch_binance_klines(
    symbol: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = MAX_LIMIT,
) -> list[tuple[int, float, float, float, float, float]]:
    """Call Binance klines REST directly. Returns list of (ts, open, high, low, close, volume)."""
    sym = symbol.replace("/", "")
    interval = TF_MAP.get(timeframe, timeframe)
    params = f"symbol={sym}&interval={interval}&limit={limit}"
    if start_ms is not None:
        params += f"&startTime={start_ms}"
    if end_ms is not None:
        params += f"&endTime={end_ms}"
    url = f"{BINANCE_KLINE_URL}?{params}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    return [(k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in data]


def rows_to_df(rows: list[tuple[int, float, float, float, float, float]]) -> pl.DataFrame:
    """Convert raw kline rows to polars DataFrame with correct schema."""
    if not rows:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Int64,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
            }
        )
    df = pl.DataFrame(
        rows,
        schema=["timestamp", "open", "high", "low", "close", "volume"],
        orient="row",
    )
    return df


def load_existing(path: Path) -> pl.DataFrame | None:
    """Load existing parquet if it exists, otherwise None."""
    if path.exists():
        return pl.read_parquet(path)
    return None


def merge_dedup_sort(
    existing: pl.DataFrame | None,
    new_df: pl.DataFrame,
) -> pl.DataFrame:
    """Merge new data into existing, deduplicate by timestamp, sort ascending."""
    if existing is None or existing.is_empty():
        combined = new_df
    else:
        combined = pl.concat([existing, new_df], how="vertical")
    combined = combined.unique(subset=["timestamp"], keep="last").sort("timestamp")
    return combined


# ---------------------------------------------------------------------------
# 核心操作
# ---------------------------------------------------------------------------

def fetch_and_store(
    symbol: str,
    timeframe: str = "1d",
    *,
    days: int | None = None,
) -> pl.DataFrame:
    """
    Fetch OHLCV → merge with existing → write parquet.

    If days is None: fetch only the most recent batch (incremental update).
    If days is set: paginate back through history up to `days` worth of data.
    """
    path = parquet_path(symbol, timeframe)
    existing = load_existing(path)

    if days is None:
        # Incremental: fetch latest 1000 candles
        rows = fetch_binance_klines(symbol, timeframe, limit=MAX_LIMIT)
        new_df = rows_to_df(rows)
    else:
        # Backfill: paginate through history
        all_rows: list[tuple[int, float, float, float, float, float]] = []
        cutoff_ms = int((datetime.now(timezone.utc).timestamp() - days * 86400) * 1000)
        end_ms = int(time.time() * 1000)
        while end_ms > cutoff_ms:
            rows = fetch_binance_klines(symbol, timeframe, end_ms=end_ms, limit=MAX_LIMIT)
            if not rows:
                break
            earliest_ts = rows[0][0]
            # Filter out anything before cutoff
            rows = [r for r in rows if r[0] >= cutoff_ms]
            if not rows:
                break
            all_rows = rows + all_rows
            end_ms = earliest_ts - 1  # move window back
            time.sleep(0.2)  # rate-limit politeness
        new_df = rows_to_df(all_rows)

    df = merge_dedup_sort(existing, new_df)
    df.write_parquet(path, compression="zstd")
    print(f"[OK] {symbol} {timeframe} → {path}  ({len(df)} rows)")

    issues = validate_ohlcv(df, timeframe)
    if issues:
        for iss in issues:
            print(f"[WARN] {symbol} {timeframe}: {iss}")
    else:
        print(f"[VALID] {symbol} {timeframe}: no issues")

    return df


def backfill(symbol: str, timeframe: str, days: int) -> pl.DataFrame:
    """Alias for fetch_and_store with days parameter — force full re-fetch."""
    print(f"[BACKFILL] {symbol} {timeframe} fetching ~{days} days of history...")
    return fetch_and_store(symbol, timeframe, days=days)


def validate_ohlcv(df: pl.DataFrame, timeframe: str = "1d") -> list[str]:
    """
    Validate OHLCV DataFrame. Returns list of issue strings.

    Checks:
    - timestamp sorted ascending
    - gap detection (gap > 1.5 * expected_interval)
    - high < low
    - high < open
    - high < close
    - zero volume
    """
    issues: list[str] = []

    if df.is_empty():
        issues.append("empty dataframe")
        return issues

    ts = df["timestamp"].to_list()

    # 1. Sorted check
    for i in range(1, len(ts)):
        if ts[i] < ts[i - 1]:
            issues.append(f"timestamp not sorted at index {i}")
            break

    # 2. Gap detection
    expected_ms = TF_MS.get(timeframe)
    if expected_ms and len(ts) > 1:
        threshold_ms = int(expected_ms * 1.5)
        for i in range(1, len(ts)):
            gap = ts[i] - ts[i - 1]
            if gap > threshold_ms:
                t1 = datetime.fromtimestamp(ts[i - 1] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                t2 = datetime.fromtimestamp(ts[i] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                issues.append(
                    f"gap of {gap / expected_ms:.1f}x interval between {t1} and {t2}"
                )

    # 3-5. OHLC sanity
    hi = df["high"].to_list()
    lo = df["low"].to_list()
    op = df["open"].to_list()
    cl = df["close"].to_list()
    vo = df["volume"].to_list()

    for i in range(len(df)):
        if hi[i] < lo[i]:
            issues.append(f"high < low at row {i}")
        if hi[i] < op[i]:
            issues.append(f"high < open at row {i}")
        if hi[i] < cl[i]:
            issues.append(f"high < close at row {i}")

    # 6. Zero volume
    zero_vol_count = sum(1 for v in vo if v == 0.0)
    if zero_vol_count > 0:
        issues.append(f"{zero_vol_count} zero-volume candles")

    return issues


def do_validate(symbol: str, timeframe: str) -> list[str]:
    """Read existing parquet and run validation."""
    path = parquet_path(symbol, timeframe)
    if not path.exists():
        print(f"[MISSING] {path} does not exist")
        return ["file not found"]
    df = pl.read_parquet(path)
    issues = validate_ohlcv(df, timeframe)
    if issues:
        for iss in issues:
            print(f"[ISSUE] {symbol} {timeframe}: {iss}")
    else:
        print(f"[VALID] {symbol} {timeframe}: all checks passed ({len(df)} rows)")
    return issues


FETCH_ALL_DEFAULT = [
    ("BTC/USDT", "1d"),
    ("ETH/USDT", "1d"),
    ("BTC/USDT", "1h"),
    ("ETH/USDT", "1h"),
]


def fetch_all() -> None:
    """Fetch all default symbols/timeframes."""
    for symbol, tf in FETCH_ALL_DEFAULT:
        fetch_and_store(symbol, tf)
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="data_sync: Binance OHLCV → Parquet (zstd) incremental storage"
    )
    sub = parser.add_subparsers(dest="command")

    # --fetch SYMBOL TIMEFRAME
    p_fetch = sub.add_parser("--fetch", help="Fetch and store (incremental)")
    p_fetch.add_argument("symbol", help="e.g. BTC/USDT")
    p_fetch.add_argument("timeframe", help="e.g. 1d, 1h, 4h")

    # --backfill SYMBOL TIMEFRAME --days N
    p_backfill = sub.add_parser("--backfill", help="Full history backfill")
    p_backfill.add_argument("symbol")
    p_backfill.add_argument("timeframe")
    p_backfill.add_argument("--days", type=int, default=365, help="Days of history (default 365)")

    # --validate SYMBOL TIMEFRAME
    p_validate = sub.add_parser("--validate", help="Validate existing data")
    p_validate.add_argument("symbol")
    p_validate.add_argument("timeframe")

    # --fetch-all
    sub.add_parser("--fetch-all", help="Fetch BTC+ETH 1d+1h")

    # Support both "python data_sync.py --fetch BTC/USDT 1d" and
    # "python data_sync.py fetch BTC/USDT 1d" (without dashes as fallback)
    args, unknown = parser.parse_known_args()

    # Handle the case where argparse doesn't match --command properly
    # due to subparser naming with dashes
    if args.command is None and unknown:
        cmd = unknown[0]
        if cmd == "--fetch":
            args.command = "--fetch"
            args.symbol = unknown[1] if len(unknown) > 1 else None
            args.timeframe = unknown[2] if len(unknown) > 2 else None
        elif cmd == "--backfill":
            args.command = "--backfill"
            args.symbol = unknown[1] if len(unknown) > 1 else None
            args.timeframe = unknown[2] if len(unknown) > 2 else None
            # handle --days
            if "--days" in unknown:
                idx = unknown.index("--days")
                if idx + 1 < len(unknown):
                    args.days = int(unknown[idx + 1])
            if not hasattr(args, "days"):
                args.days = 365
        elif cmd == "--validate":
            args.command = "--validate"
            args.symbol = unknown[1] if len(unknown) > 1 else None
            args.timeframe = unknown[2] if len(unknown) > 2 else None
        elif cmd == "--fetch-all":
            args.command = "--fetch-all"

    if args.command == "--fetch":
        if not args.symbol or not args.timeframe:
            parser.error("--fetch requires SYMBOL and TIMEFRAME")
        fetch_and_store(args.symbol, args.timeframe)
    elif args.command == "--backfill":
        backfill(args.symbol, args.timeframe, args.days)
    elif args.command == "--validate":
        do_validate(args.symbol, args.timeframe)
    elif args.command == "--fetch-all":
        fetch_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
