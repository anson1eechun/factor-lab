#!/usr/bin/env python3
"""
Daily Dashboard Refresh.
Regenerates dashboard.html with latest data. Lightweight, no backtest.
"""

import subprocess
import sys
from pathlib import Path

FACTOR_LAB = Path("/home/anson/factor-lab")


def main():
    result = subprocess.run(
        ["python3", "scripts/generate_dashboard.py"],
        capture_output=True, text=True, timeout=120, cwd=str(FACTOR_LAB)
    )
    if result.returncode != 0:
        print(f"Dashboard failed: {result.stderr[:200]}", file=sys.stderr)
        sys.exit(1)
    print("[OK] dashboard.html refreshed")


if __name__ == "__main__":
    main()
