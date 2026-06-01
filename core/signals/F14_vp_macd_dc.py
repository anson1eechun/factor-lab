"""
F14: VP-MACD Directional Conviction Factor (VP-MACD-DC)

Based on VP-MACD (Volatility-Price MACD, 2604.26063):
  - Integrates volatility-adjusted price momentum with volume.
  - Adds a "Directional Conviction" overlay using candle body,
    volume, and volatility confirmation.

Public:
  compute_vp_macd_dc(ohlcv, params) -> np.ndarray

Inputs:
  ohlcv : list[dict]
          Each dict must have keys:
            - open, high, low, close, volume   (numeric)
  params : dict, optional
           Tunable parameters (see "Parameters" in compute_vp_macd_dc docstring).

Formulas (core idea):
  1) Intraday range and direction:
       vol_t         = max(H_t - L_t, |C_t - O_t|)
       body_t        = C_t - O_t
       body_ratio_t  = body_t / (H_t - L_t + ε)

  2) Volume and volatility context (rolling means):
       avg_vol_N(t)   = mean(vol, N)
       avg_vol_mv(t)  = mean(vol, mv)
       vol_ratio_t    = avg_vol_N(t) / (avg_vol_mv(t) + ε)
       volm_ratio_t   = V_t / (mean(V, mv) + ε)

  3) VP* (volume-weighted, volatility- and conviction-adjusted price):
       VP*_t = C_t * (V_t / (mean(V, N) + ε))
               * (1 + α * body_ratio_t + β * vol_ratio_t)

  4) MACD structure:
       MACD_line(t)   = EMA(VP*, fast) - EMA(VP*, slow)
       Signal_line(t) = EMA(MACD_line, signal)
       Histo(t)       = MACD_line(t) - Signal_line(t)

  5) Directional Conviction:
       DC(t) = body_ratio_t * volm_ratio_t * vol_ratio_t

  6) Factor (final):
       z_x(t) = (x_t - mean(x, nv)) / (std(x, nv) + ε)
       Factor(t) = Histo(t)
                   * DC(t)
                   * (1 + λ_vol * z(vol_t) + λ_volm * z(volume_t))

Notes:
  - NaN in the first (max(fast, slow, signal, mv, nv) + safety) bars is normal.
  - No external heavy dependencies: uses only numpy + standard library.
"""

from __future__ import annotations

import json
import math
import urllib.request
from typing import Any, Dict, List, Optional

import numpy as np

EPS = 1e-12


def ema(x: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average, span-based alpha.
       Finds first non-NaN and initializes there; earlier positions remain NaN."""
    if span < 1:
        raise ValueError("EMA span must be >= 1")
    alpha = 2.0 / (span + 1.0)
    out = np.full_like(x, np.nan, dtype=float)
    start = None
    for i in range(len(x)):
        if not np.isnan(x[i]):
            start = i
            break
    if start is None:
        return out
    out[start] = x[start]
    for i in range(start + 1, len(x)):
        if not np.isnan(x[i]):
            out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Simple rolling mean; NaN where window not full."""
    if window < 1:
        return np.full_like(x, np.nan, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(window - 1, len(x)):
        out[i] = np.mean(x[i - window + 1 : i + 1])
    return out


def rolling_std(x: np.ndarray, window: int) -> np.ndarray:
    """Simple rolling standard deviation (ddof=1); NaN where not full."""
    if window < 2:
        return np.full_like(x, np.nan, dtype=float)
    out = np.full_like(x, np.nan, dtype=float)
    for i in range(window - 1, len(x)):
        out[i] = float(np.std(x[i - window + 1 : i + 1], ddof=1))
    return out


def compute_vp_macd_dc(
    ohlcv: List[Dict[str, float]],
    params: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """
    Compute VP-MACD Directional Conviction Factor.

    Parameters
    ----------
    ohlcv : list[dict]
        Each element must contain:
            - open, high, low, close, volume (float)
    params : dict, optional
        Tuning parameters. Defaults:
            - fast    = 12          (MACD fast EMA)
            - slow    = 26          (MACD slow EMA)
            - signal  = 9           (MACD signal EMA)
            - N       = 14          (VP* volume/adj window)
            - mv      = 20          (DC normalization window)
            - nv      = 60          (z-score windows)
            - α       = 0.5         (body_ratio weight in VP*)
            - β       = 0.3         (vol_ratio weight in VP*)
            - λ_vol   = 0.05        (volatility z-scale in Factor)
            - λ_volm  = 0.03        (volume z-scale in Factor)

    Returns
    -------
    np.ndarray
        Array of factor values, aligned with input; leading NaN until warm-up.
    """
    if not ohlcv:
        return np.array([], dtype=float)

    # Default parameters
    p = {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "N": 14,
        "mv": 20,
        "nv": 60,
        "alpha": 0.5,    # α
        "beta": 0.3,     # β
        "lambda_vol": 0.05,   # λ_vol
        "lambda_volm": 0.03,  # λ_volm
    }
    if params:
        p.update(params)

    fast = int(p["fast"])
    slow = int(p["slow"])
    signal_span = int(p["signal"])
    N = int(p["N"])
    mv = int(p["mv"])
    nv = int(p["nv"])
    alpha = float(p["alpha"])
    beta = float(p["beta"])
    lam_vol = float(p["lambda_vol"])
    lam_volm = float(p["lambda_volm"])

    # Extract to arrays
    o = np.array([float(c["open"]) for c in ohlcv], dtype=float)
    h = np.array([float(c["high"]) for c in ohlcv], dtype=float)
    l = np.array([float(c["low"]) for c in ohlcv], dtype=float)
    c = np.array([float(c["close"]) for c in ohlcv], dtype=float)
    v = np.array([float(c["volume"]) for c in ohlcv], dtype=float)
    n = len(c)

    # Basic series
    hl_range = h - l  # can be 0 for some bars
    body = c - o
    body_abs = np.abs(body)
    vol = np.maximum(hl_range, body_abs)

    # Rolling stats
    avg_vol_N = rolling_mean(vol, N)
    avg_vol_mv = rolling_mean(vol, mv)
    avg_vol_mv = np.where(avg_vol_mv == 0, EPS, avg_vol_mv)
    avg_v_N = rolling_mean(v, N)
    avg_v_mv = rolling_mean(v, mv)

    # body_ratio_t = body_t / (H-L + ε)
    body_ratio = body / (hl_range + EPS)

    # vol_ratio_t = avg_vol_N / (avg_vol_mv + ε)
    vol_ratio = avg_vol_N / (avg_vol_mv + EPS)

    # volm_ratio_t = V_t / (mean(V, mv) + ε)
    volm_ratio = v / (avg_v_mv + EPS)

    # VP*_t
    vol_weight = v / (avg_v_N + EPS)
    conv_adj = 1.0 + alpha * body_ratio + beta * vol_ratio
    vp_star = c * vol_weight * conv_adj

    # MACD
    ema_fast = ema(vp_star, fast)
    ema_slow = ema(vp_star, slow)
    macd_line = ema_fast - ema_slow

    signal_line = ema(macd_line, signal_span)
    histo = macd_line - signal_line

    # Directional Conviction: DC(t) = body_ratio * volm_ratio * vol_ratio
    dc = body_ratio * volm_ratio * vol_ratio

    # z-scores for volatility and volume (window = nv)
    z_vol = np.full(n, np.nan, dtype=float)
    z_volm = np.full(n, np.nan, dtype=float)

    for i in range(nv - 1, n):
        s_vol = float(np.std(vol[i - nv + 1 : i + 1], ddof=1))
        m_vol = float(np.mean(vol[i - nv + 1 : i + 1]))
        z_vol[i] = (vol[i] - m_vol) / (s_vol + EPS)

        s_volm = float(np.std(v[i - nv + 1 : i + 1], ddof=1))
        m_volm = float(np.mean(v[i - nv + 1 : i + 1]))
        z_volm[i] = (v[i] - m_volm) / (s_volm + EPS)

    # Factor(t) = Histo * DC * (1 + λ_vol * z(vol) + λ_volm * z(volume))
    factor = np.full(n, np.nan, dtype=float)
    for i in range(n):
        if (
            not np.isnan(histo[i])
            and not np.isnan(dc[i])
            and not np.isnan(z_vol[i])
            and not np.isnan(z_volm[i])
        ):
            adj = 1.0 + lam_vol * z_vol[i] + lam_volm * z_volm[i]
            factor[i] = histo[i] * dc[i] * adj

    return factor


# ---------------------------------------------------------------------------
# Smoke test (self-contained via Binance REST)
# ---------------------------------------------------------------------------

def _fetch_btcusdt(limit: int = 500, interval: str = "1d") -> List[Dict[str, float]]:
    """Fetch BTCUSDT klines from Binance REST (no external deps)."""
    symbol = "BTCUSDT"
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval={interval}&limit={limit}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    candles = []
    for k in data:
        candles.append(
            {
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
        )
    return candles


def _basic_stats(values: np.ndarray):
    valid = values[~np.isnan(values)]
    if valid.size == 0:
        print("[Smoke] No valid factor values.")
        return
    print(f"[Smoke] Valid count : {valid.size}")
    print(f"[Smoke] mean        : {np.mean(valid):.6f}")
    print(f"[Smoke] std         : {np.std(valid, ddof=1):.6f}")
    print(f"[Smoke] min         : {np.min(valid):.6f}")
    print(f"[Smoke] max         : {np.max(valid):.6f}")
    print(f"[Smoke] median      : {np.median(valid):.6f}")
    print(f"[Smoke] skew        : {float(skew(valid)):.4f}")


def skew(x: np.ndarray) -> float:
    """Fisher–Pearson skewness (basic)."""
    n = len(x)
    if n < 3:
        return 0.0
    m = np.mean(x)
    s = np.std(x, ddof=1)
    if s == 0:
        return 0.0
    return float(np.mean(((x - m) / s) ** 3))


if __name__ == "__main__":
    print("=== F14 VP-MACD-DC Smoke Test ===")
    ohlcv = _fetch_btcusdt(limit=500, interval="1d")
    print(f"Fetched {len(ohlcv)} BTCUSDT daily candles from Binance.")

    # Default params
    factor = compute_vp_macd_dc(ohlcv)

    print("\n--- Default parameters ---")
    _basic_stats(factor)

    # Slight parameter variation
    alt_params = {"fast": 9, "slow": 21, "signal": 5, "N": 10, "mv": 15, "nv": 40}
    factor_alt = compute_vp_macd_dc(ohlcv, params=alt_params)
    print("\n--- Alt parameters ---")
    _basic_stats(factor_alt)
