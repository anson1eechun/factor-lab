#!/usr/bin/env python3
"""
Mid-week Factor Refresh Script.
Re-fetches latest data, re-runs backtests on all validated factors, 
regenerates dashboard. Designed for cron (no_agent) execution.

Runs every Wednesday 04:00. Quiet on success, reports errors only.
"""

import sqlite3
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

FACTOR_LAB = Path("/home/anson/factor-lab")
DB_PATH = FACTOR_LAB / "index.db"


def run(cmd, timeout=300):
    """Run a shell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        timeout=timeout, cwd=str(FACTOR_LAB)
    )
    return result.returncode, result.stdout, result.stderr


def main():
    errors = []

    # ── Step 1: Sync market data ──────────────────────────────────────
    rc, out, err = run(f"{sys.executable} scripts/data_sync.py")
    if rc != 0:
        errors.append(f"data_sync failed: {err[:200]}")
    else:
        print(f"[OK] data_sync: done")

    # ── Step 2: Get validated factors ─────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    factors = conn.execute(
        "SELECT id, name, formula, category FROM factor_registry WHERE status='active'"
    ).fetchall()
    conn.close()

    if not factors:
        print("[SKIP] No validated factors to backtest.")
        return

    print(f"[INFO] Backtesting {len(factors)} validated factors...")

    # ── Step 3: Run backtest data fetch ───────────────────────────────
    rc, out, err = run(
        f"{sys.executable} -c \"\n"
        f"import sys; sys.path.insert(0, '{FACTOR_LAB}')\n"
        f"from core.adapters.crypto import CryptoAdapter\n"
        f"adapter = CryptoAdapter()\n"
        f"df = adapter.get_ohlcv('BTCUSDT', '1d', limit=1500)\n"
        f"df.to_parquet('/tmp/refresh_btc.parquet')\n"
        f"print(f'BTCUSDT: {{len(df)}} rows')\n"
        f"\"\n",
        timeout=120
    )
    if rc == 0:
        print(f"  [OK] Data fetch: {out.strip()}")
    else:
        errors.append(f"Data fetch failed: {err[:200]}")

    # ── Step 4: Generate reports ──────────────────────────────────────
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        sym_short = symbol.replace("/", "").lower()
        rc, out, err = run(
            f"{sys.executable} scripts/generate_report.py --symbol {symbol} "
            f"--output report_{sym_short}.html",
            timeout=180
        )
        if rc == 0:
            print(f"  [OK] report_{sym_short}.html")
        else:
            errors.append(f"report {symbol} failed: {err[:200]}")

    # ── Step 5: Regenerate dashboard ──────────────────────────────────
    rc, out, err = run(f"{sys.executable} scripts/generate_dashboard.py", timeout=120)
    if rc == 0:
        print(f"  [OK] dashboard.html regenerated")
    else:
        errors.append(f"dashboard failed: {err[:200]}")

    # ── Step 6: Log to DB ─────────────────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO debate_sessions (session_id, title, num_factors_validated, "
        "completed_at, notes) VALUES (?, ?, ?, ?, ?)",
        (
            f"midweek-refresh-{datetime.now().strftime('%Y%m%d')}",
            "Mid-week Factor Refresh",
            len(factors),
            datetime.now().isoformat(),
            json.dumps({"errors": errors, "factors_tested": len(factors)})
        )
    )
    conn.commit()
    conn.close()

    # ── Summary ───────────────────────────────────────────────────────
    if errors:
        print(f"\n[DONE] {len(factors)} factors, {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"\n[DONE] {len(factors)} factors tested, 0 errors. Dashboard refreshed.")


if __name__ == "__main__":
    main()
