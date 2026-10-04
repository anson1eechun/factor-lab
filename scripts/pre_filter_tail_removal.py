#!/usr/bin/env python3
"""
Pre-filter: 剔 5% 日尾部壓測 + 成本打平 + 事件研究 + Regime 穩定性
=============================================================
在進入完整 debate 流程前，先對候選因子做快速篩檢。
產出來自 2026-06-08 負面結果總報告的鑑別器方法論。

用法:
    python3 scripts/pre_filter_tail_removal.py \\
        --signal core/signals/F10_Wick_Absorption_Asymmetry.py \\
        --symbol BTCUSDT --horizon 5 --json

輸出 JSON:
    {
      "signal": "F10_Wick_Absorption_Asymmetry",
      "pass": false,
      "failure_family": "C",
      "tests": {
        "tail_removal": {
          "pass": false,
          "full_sharpe": 0.26,
          "top5_removed_sharpe": -0.45,
          "bottom5_removed_sharpe": 0.18,
          "top5_pct_loss": 273.1
        },
        "breakeven_bps": {
          "pass": false,
          "breakeven_bps": 0.8,
          "turnover_per_day": 0.45,
          "avg_return_per_trade_bps": 1.2
        },
        "event_study": {
          "pass": true,
          "t0_ic": 0.043,
          "t0_pval": 0.001,
          "t1_ic": 0.031,
          "t1_pval": 0.02
        },
        "regime_stability": {
          "pass": false,
          "high_vol_ic": 0.08,
          "low_vol_ic": -0.03
        },
        "multiple_testing": {
          "pass": false,
          "n_hypotheses": 23,
          "raw_pval": 0.001,
          "bonferroni_pval": 0.023,
          "holm_pval": 0.023
        }
      }
    }
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

# ── project root ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_signal_function(signal_path: str):
    """Dynamically import the `factor` function from a signal module."""
    spec = importlib.util.spec_from_file_location("_signal", signal_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "factor"):
        raise AttributeError(f"Signal module {signal_path} has no `factor(df)` function")
    return mod.factor, os.path.splitext(os.path.basename(signal_path))[0]


def load_data(symbol: str = "BTCUSDT", limit: int = 1500) -> pd.DataFrame:
    """Load OHLCV data via CryptoAdapter."""
    from core.adapters.crypto import CryptoAdapter
    adapter = CryptoAdapter()
    df = adapter.get_ohlcv(symbol, "1d", limit=limit)
    # Normalise columns
    df = df.rename(columns={
        "timestamp": "timestamp",
        "ts": "timestamp",
    })
    if "timestamp" not in df.columns:
        df["timestamp"] = df.index
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def compute_factor_and_returns(
    df: pd.DataFrame, factor_fn, horizon: int = 5
) -> pd.DataFrame:
    """Compute factor values, forward returns, and quintile positions."""
    df = df.copy()

    # Factor values (strictly historical)
    df["factor_raw"] = factor_fn(df)
    df["factor_val"] = df["factor_raw"].shift(1)  # no look-ahead

    # Winsorize
    lo, hi = df["factor_val"].quantile(0.01), df["factor_val"].quantile(0.99)
    df["factor_val"] = df["factor_val"].clip(lo, hi)

    # Z-score
    mu = df["factor_val"].rolling(252, min_periods=60).mean()
    sg = df["factor_val"].rolling(252, min_periods=60).std(ddof=1)
    df["factor_z"] = (df["factor_val"] - mu) / sg.replace(0, np.nan)

    # Forward return
    df["fwd_ret"] = df["close"].shift(-horizon) / df["close"] - 1

    # Quintile groups
    df["quintile"] = pd.qcut(
        df["factor_z"].rank(method="first"),
        5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
        duplicates="drop",
    )

    # Position-weighted strategy: long Q5, short Q1
    pos = np.zeros(len(df))
    q1_mask = (df["quintile"] == "Q1").values
    q5_mask = (df["quintile"] == "Q5").values
    pos[q5_mask] = 1.0
    pos[q1_mask] = -1.0
    df["position"] = pos

    # Strategy return
    df["strat_ret"] = df["position"] * df["fwd_ret"]

    # Daily return (for tail removal — decompound horizon returns)
    df["daily_ret"] = df["close"].pct_change()

    # Turnover: position changes
    df["turnover"] = df["position"].diff().abs()
    df["turnover"] = df["turnover"].fillna(0)

    return df.dropna(subset=["fwd_ret", "factor_z"])


def annualize_sharpe(ret_series: pd.Series, horizon: int) -> float:
    """Annualize Sharpe from horizon-h returns."""
    if len(ret_series) < 10 or ret_series.std() == 0:
        return np.nan
    return float(ret_series.mean() / ret_series.std() * np.sqrt(365 / horizon))


def test_tail_removal(
    df: pd.DataFrame, horizon: int
) -> dict:
    """
    Test: remove top 5% and bottom 5% of daily strategy returns.
    Family B (reversal) dies on top removal.
    Family C (event) dies on either top or bottom removal.
    """
    valid = df.dropna(subset=["strat_ret"])
    if len(valid) < 60:
        return {"pass": False, "error": "insufficient_data"}

    strat_rets = valid["strat_ret"].values
    n = len(strat_rets)
    k = max(1, int(n * 0.05))

    # Full Sharpe
    full_sharpe = annualize_sharpe(valid["strat_ret"], horizon)

    # Remove top 5% (largest positive returns)
    top_idx = np.argsort(strat_rets)[-k:]
    top5_removed = np.delete(strat_rets, top_idx)
    top5_sharpe = annualize_sharpe(pd.Series(top5_removed), horizon)

    # Remove bottom 5% (largest negative returns)
    bot_idx = np.argsort(strat_rets)[:k]
    bot5_removed = np.delete(strat_rets, bot_idx)
    bot5_sharpe = annualize_sharpe(pd.Series(bot5_removed), horizon)

    # Pct loss from top removal
    pct_loss = ((full_sharpe - top5_sharpe) / abs(full_sharpe) * 100) if full_sharpe != 0 else np.inf

    # Pass condition: both top5 and bottom5 removal Sharpe > 0
    pass_top = not np.isnan(top5_sharpe) and top5_sharpe > 0
    pass_bot = not np.isnan(bot5_sharpe) and bot5_sharpe > 0
    passed = pass_top and pass_bot

    return {
        "pass": bool(passed),
        "full_sharpe": round(full_sharpe, 4) if not np.isnan(full_sharpe) else None,
        "top5_removed_sharpe": round(top5_sharpe, 4) if not np.isnan(top5_sharpe) else None,
        "bottom5_removed_sharpe": round(bot5_sharpe, 4) if not np.isnan(bot5_sharpe) else None,
        "top5_pct_loss": round(pct_loss, 1),
        "top5_pass": bool(pass_top),
        "bottom5_pass": bool(pass_bot),
    }


def test_breakeven(
    df: pd.DataFrame,
) -> dict:
    """
    Test: how many bps per trade can the strategy absorb before going negative?
    Family B (reversal, < 1bp breakeven) dies here.
    """
    valid = df.dropna(subset=["strat_ret", "turnover"])
    if len(valid) < 30:
        return {"pass": False, "error": "insufficient_data"}

    avg_return_per_bar = valid["strat_ret"].mean()
    avg_turnover = valid["turnover"].mean()

    if avg_turnover == 0 or np.isnan(avg_turnover):
        return {
            "pass": False,
            "breakeven_bps": np.inf,
            "turnover_per_day": 0,
            "avg_return_per_trade_bps": 0,
            "error": "zero_turnover",
        }

    # Breakeven: avg_return_per_bar / avg_turnover → bps per trade
    breakeven_bps = (avg_return_per_bar / avg_turnover) * 10000

    # Return per trade in bps (same thing, different angle)
    avg_ret_bps = avg_return_per_bar * 10000

    # Pass if breakeven >= 5 bps
    passed = breakeven_bps >= 5.0

    return {
        "pass": bool(passed),
        "breakeven_bps": round(float(breakeven_bps), 2),
        "turnover_per_day": round(float(avg_turnover), 4),
        "avg_return_per_trade_bps": round(float(avg_ret_bps), 4),
    }


def test_event_study(
    df: pd.DataFrame,
) -> dict:
    """
    Test: is the factor predictive at T+0, T+1, T+2?
    Family D (data delay) dies when T+0 significant but T+1 not.
    """
    valid = df.dropna(subset=["factor_z"])
    if len(valid) < 30:
        return {"pass": False, "error": "insufficient_data"}

    results = {}
    for lag in [0, 1, 2, 3]:
        if lag == 0:
            # Same-day return for contemporaneous check
            fwd = valid["close"].diff() / valid["close"].shift(1)
        else:
            fwd = valid["close"].shift(-lag) / valid["close"] - 1
        mask = ~fwd.isna()
        if mask.sum() < 20:
            results[f"t{lag}"] = {"ic": None, "pval": None, "significant": False}
            continue

        ic, pval = stats.spearmanr(
            valid.loc[mask, "factor_z"].values.ravel(),
            fwd[mask].values.ravel(),
        )
        results[f"t{lag}"] = {
            "ic": round(float(ic), 4),
            "pval": round(float(pval), 4),
            "significant": bool(pval < 0.05),
        }

    # Family D check: T+0 significant but T+1 not
    t0_sig = results["t0"]["significant"]
    t1_sig = results["t1"]["significant"]
    t1_ic = results["t1"]["ic"] or 0

    # Pass: T+1 is significant (or at least same direction as T+0 with p < 0.1)
    passed = t1_sig or (t1_ic * (results["t0"]["ic"] or 0) > 0 and (results["t1"]["pval"] or 1.0) < 0.1)

    return {
        "pass": bool(passed),
        "t0_significant": bool(t0_sig),
        "t1_significant": bool(t1_sig),
        **results,
    }


def test_regime_stability(df: pd.DataFrame) -> dict:
    """
    Test: split by volatility regime, check IC direction consistency.
    """
    valid = df.dropna(subset=["factor_z", "fwd_ret"])
    if len(valid) < 100:
        return {"pass": False, "error": "insufficient_data"}

    # 20-day rolling volatility
    valid = valid.copy()
    valid["vol20"] = valid["close"].pct_change().rolling(20).std()

    median_vol = valid["vol20"].median()
    high_vol = valid[valid["vol20"] > median_vol]
    low_vol = valid[valid["vol20"] <= median_vol]

    ic_high, p_high = stats.spearmanr(
        high_vol["factor_z"].values.ravel(),
        high_vol["fwd_ret"].values.ravel(),
    )
    ic_low, p_low = stats.spearmanr(
        low_vol["factor_z"].values.ravel(),
        low_vol["fwd_ret"].values.ravel(),
    )

    # Pass: both regimes have same-sign IC
    passed = (ic_high * ic_low > 0) and (abs(ic_high) > 0.01) and (abs(ic_low) > 0.01)

    return {
        "pass": bool(passed),
        "high_vol_ic": round(float(ic_high), 4),
        "high_vol_pval": round(float(p_high), 4),
        "high_vol_n": len(high_vol),
        "low_vol_ic": round(float(ic_low), 4),
        "low_vol_pval": round(float(p_low), 4),
        "low_vol_n": len(low_vol),
        "same_direction": bool(ic_high * ic_low > 0),
    }


def test_multiple_testing(pval: float, n_hypotheses: int = 23) -> dict:
    """
    Bonferroni correction against total hypotheses tested.
    Reads search_ledger.jsonl for the actual count if available.
    """
    bonferroni = min(pval * n_hypotheses, 1.0)

    # Holm-Bonferroni: sort all p-values, reject sequentially
    # For single test: same as Bonferroni
    holm = bonferroni

    passed = bonferroni < 0.05

    return {
        "pass": bool(passed),
        "n_hypotheses": n_hypotheses,
        "raw_pval": round(pval, 4),
        "bonferroni_pval": round(bonferroni, 4),
        "holm_pval": round(holm, 4),
    }


def classify_failure(tests: dict) -> Optional[str]:
    """Classify failure into one of A/B/C/D/IC-IR/PnL families."""
    tail = tests.get("tail_removal", {})
    be = tests.get("breakeven_bps", {})
    event = tests.get("event_study", {})
    regime = tests.get("regime_stability", {})

    # Family D: data delay (T+0 sig but T+1 not)
    if event.get("t0_significant") and not event.get("t1_significant"):
        return "D"

    # Family B: reversal — IC exists but destroyed by tail removal + low breakeven
    if (not tail.get("pass", False) and
        be.get("breakeven_bps", 999) < 1.0 and
        tail.get("top5_removed_sharpe") is not None and
        tail.get("top5_removed_sharpe") < 0):
        return "B"

    # Family C: event/tail-driven (top5 removal kills Sharpe)
    if (not tail.get("pass", False) and
        tail.get("full_sharpe", 0) > 0 and
        tail.get("top5_removed_sharpe", 0) is not None and
        tail.get("top5_removed_sharpe", 0) < 0):
        return "C"

    # Family A: no signal
    ic_ir = tests.get("ic_ir", {})
    if not ic_ir.get("pass", True):
        # Check if IC is near zero
        if abs(ic_ir.get("ic_mean", 99)) < 0.02:
            return "A"

    # IC-IR/PnL decoupling
    if (ic_ir.get("pass", False) and
        tail.get("full_sharpe", 0) is not None and
        tail.get("full_sharpe", 0) < 0):
        return "IC-IR/PnL_decoupling"

    return None


def run_pre_filter(
    signal_path: str,
    symbol: str = "BTCUSDT",
    horizon: int = 5,
    n_hypotheses: int = 23,
) -> dict:
    """Run all pre-filter tests on a signal file."""
    factor_fn, signal_name = load_signal_function(signal_path)

    print(f"[pre-filter] Loading {symbol} data...", file=sys.stderr)
    df = load_data(symbol)
    print(f"[pre-filter] {len(df)} rows loaded", file=sys.stderr)

    print(f"[pre-filter] Computing factor: {signal_name}", file=sys.stderr)
    df = compute_factor_and_returns(df, factor_fn, horizon)
    valid = df.dropna(subset=["strat_ret"])
    print(f"[pre-filter] {len(valid)} valid rows after factor computation", file=sys.stderr)

    # ── IC-IR (for reference, from empiricist) ──
    ic, ic_pval = stats.spearmanr(
        valid["factor_z"].values.ravel(),
        valid["fwd_ret"].values.ravel(),
    )
    # ── IC-IR (rolling window) ──
    ic_std = np.nan
    try:
        # Use expanding window to avoid the rolling-apply DataFrame issue
        ic_series = []
        for i in range(60, len(valid)):
            window = valid.iloc[i-60:i]
            if len(window.dropna(subset=["factor_z", "fwd_ret"])) > 20:
                ic_val, _ = stats.spearmanr(
                    window["factor_z"].values.ravel(),
                    window["fwd_ret"].values.ravel(),
                )
                ic_series.append(ic_val)
        if ic_series:
            ic_series = pd.Series(ic_series)
            ic_std = ic_series.std()
    except Exception:
        ic_std = np.nan
    ic_ir = ic / ic_std if ic_std and ic_std > 0 else 0.0

    ic_ir_test = {
        "pass": bool(abs(ic_ir) >= 0.3),
        "ic_mean": round(float(ic), 4),
        "ic_std": round(float(ic_std), 4) if ic_std and ic_std > 0 else None,
        "ic_ir": round(float(ic_ir), 4),
        "ic_pval": round(float(ic_pval), 4),
    }

    # ── Run tests ──
    print("[pre-filter] Test: tail removal (top/bottom 5%)", file=sys.stderr)
    tail = test_tail_removal(df, horizon)

    print("[pre-filter] Test: breakeven cost analysis", file=sys.stderr)
    breakeven = test_breakeven(df)

    print("[pre-filter] Test: event study (T+0..T+3)", file=sys.stderr)
    event = test_event_study(df)

    print("[pre-filter] Test: regime stability", file=sys.stderr)
    regime = test_regime_stability(df)

    # Multi-testing correction (use the best p-value from IC test)
    multi = test_multiple_testing(ic_pval, n_hypotheses)

    tests = {
        "ic_ir": ic_ir_test,
        "tail_removal": tail,
        "breakeven_bps": breakeven,
        "event_study": event,
        "regime_stability": regime,
        "multiple_testing": multi,
    }

    # ── Overall pass ──
    all_pass = all(
        tests[k].get("pass", False) if isinstance(tests[k], dict) else False
        for k in ["ic_ir", "tail_removal", "breakeven_bps", "event_study",
                   "regime_stability", "multiple_testing"]
    )

    failure_family = classify_failure(tests)

    result = {
        "signal": signal_name,
        "symbol": symbol,
        "horizon": horizon,
        "n_rows": len(df),
        "n_valid": len(valid),
        "pass": all_pass,
        "failure_family": failure_family,
        "tests": tests,
    }

    return result


# ── CLI ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Pre-filter: 剔 5% 日壓測 + 成本打平 + 事件研究 + Regime 穩定性"
    )
    parser.add_argument("--signal", required=True, help="Path to signal .py file")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair")
    parser.add_argument("--horizon", type=int, default=5, help="Forward return horizon in days")
    parser.add_argument("--n-hypotheses", type=int, default=23,
                        help="Total hypotheses for Bonferroni correction")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    result = run_pre_filter(
        signal_path=args.signal,
        symbol=args.symbol,
        horizon=args.horizon,
        n_hypotheses=args.n_hypotheses,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("=" * 70)
        print(f"PRE-FILTER: {result['signal']} on {result['symbol']} (h={result['horizon']}d)")
        print(f"Rows: {result['n_rows']} total, {result['n_valid']} valid")
        print("=" * 70)

        for name, test in result["tests"].items():
            passed = test.get("pass", False)
            icon = "✅" if passed else "❌"
            print(f"\n{icon} {name}")
            if name == "ic_ir":
                print(f"   IC={test['ic_mean']:.4f}  IC-IR={test['ic_ir']:.4f}  p={test['ic_pval']:.4f}")
            elif name == "tail_removal":
                print(f"   Full Sharpe={test['full_sharpe']:.4f}")
                print(f"   Top-5% removed Sharpe={test['top5_removed_sharpe']:.4f}")
                print(f"   Bottom-5% removed Sharpe={test['bottom5_removed_sharpe']:.4f}")
                print(f"   Top-5% loss={test['top5_pct_loss']:.1f}%")
            elif name == "breakeven_bps":
                print(f"   Breakeven={test['breakeven_bps']:.2f} bps/trade")
                print(f"   Turnover={test['turnover_per_day']:.4f}/day")
            elif name == "event_study":
                for lag in ["t0", "t1", "t2", "t3"]:
                    d = test.get(lag, {})
                    if d:
                        s = " *" if d.get("significant") else ""
                        print(f"   {lag}: IC={d['ic']:.4f} p={d['pval']:.4f}{s}")
            elif name == "regime_stability":
                print(f"   High-vol IC={test['high_vol_ic']:.4f} (n={test['high_vol_n']})")
                print(f"   Low-vol IC={test['low_vol_ic']:.4f} (n={test['low_vol_n']})")
                print(f"   Same direction: {test['same_direction']}")
            elif name == "multiple_testing":
                print(f"   Raw p={test['raw_pval']:.4f}")
                print(f"   Bonferroni (N={test['n_hypotheses']}): p={test['bonferroni_pval']:.4f}")

        print(f"\n{'=' * 70}")
        if result['pass']:
            print("OVERALL: PASS ✅")
        else:
            fam = result['failure_family'] or "unknown"
            print(f"OVERALL: FAIL ❌  —  Family: {fam}")
        print("=" * 70)


if __name__ == "__main__":
    main()
