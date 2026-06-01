#!/usr/bin/env python3
"""
VP-MACD Factor Test (paper 2604.26063)
Volatility-Price Momentum + Volume-adjusted MACD

Factor definition:
- VP(t) = price(t) adjusted by vol + volume:
  VP(t) = price(t) * (1 + λ_vol * vol_score(t) + λ_volm * volm_score(t))
  where vol_score = z(vol_t, n) and volm_score = z(volume_t, n)
- MACD on VP series
- Signal: long when MACD > 0, short when MACD < 0
"""
import sys, os, numpy as np
from pathlib import Path

# Ensure numpy available
sys.path.insert(0, "/home/anson/factor-lab")

# Minimal crypto data fetch using REST (no ccxt)
def fetch_ohlcv(symbol: str, days: int = 400):
    import json, urllib.request
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={days}"
    with urllib.request.urlopen(url, timeout=15) as r:
        rows = json.loads(r.read().decode())
    data = []
    for row in rows:
        data.append({
            'timestamp': row[0],
            'open': float(row[1]),
            'high': float(row[2]),
            'low': float(row[3]),
            'close': float(row[4]),
            'volume': float(row[5]),
        })
    return data

def vp_macd_signal(closes, volumes, fast=12, slow=26, signal=9,
                   λ_vol=0.05, λ_volm=0.03, z_window=60):
    # Normalize volumes
    v = np.array(volumes, dtype=float)
    z_vol = np.zeros_like(v)
    for i in range(len(v)):
        if i < z_window:
            continue
        window = v[max(0, i-z_window):i]
        m, s = window.mean(), window.std()
        if s > 0:
            z_vol[i] = (v[i] - m) / s
    # Compute returns-based volatility
    r = np.array(closes, dtype=float)
    ret = np.zeros(len(closes))
    for i in range(1, len(closes)):
        ret[i] = (closes[i] - closes[i-1]) / closes[i-1]
    z_volatility = np.zeros(len(closes))
    for i in range(len(closes)):
        if i < z_window:
            continue
        window = np.abs(ret[max(0, i-z_window):i])
        m, s = window.mean(), window.std()
        if s > 0:
            z_volatility[i] = (np.abs(ret[i]) - m) / s

    # VP = price adjusted by vol + volume
    vp = np.array(closes, dtype=float)
    for i in range(len(vp)):
        vp[i] = closes[i] * (1 + λ_vol * z_volatility[i] + λ_volm * z_vol[i])

    # MACD on VP
    ema_fast = ema(vp, fast)
    ema_slow = ema(vp, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return histogram

def ema(x, span):
    out = np.zeros_like(x)
    k = 2.0 / (span + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = k * x[i] + (1 - k) * out[i - 1]
    return out

def rank_ic(signal, returns):
    m = min(len(signal), len(returns))
    s = signal[:m]
    r = returns[:m]
    # Spearman: rank correlation
    def rank(arr):
        sorter = arr.argsort()
        ranks = np.empty_like(arr, dtype=float)
        ranks[sorter] = np.arange(1, len(arr)+1, dtype=float)
        return ranks
    from scipy.stats import spearmanr
    rho, _ = spearmanr(rank(s), rank(r))
    return rho

def main():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    # For single-asset signal, test each individually
    all_ics = {}
    for sym in symbols:
        data = fetch_ohlcv(sym, days=400)
        closes = [d["close"] for d in data]
        volumes = [d["volume"] for d in data]

        # Compute VP-MACD signal
        signal = vp_macd_signal(closes, volumes, λ_vol=0.05, λ_volm=0.03)

        # 1-day, 5-day forward returns
        ret1 = np.zeros(len(closes))
        ret5 = np.zeros(len(closes))
        for i in range(1, len(closes)):
            ret1[i] = (closes[i] - closes[i-1]) / closes[i-1]
        for i in range(5, len(closes)):
            ret5[i] = (closes[i] - closes[i-5]) / closes[i-5]

        # Align
        T = min(len(signal), len(ret1), len(ret5))
        sig = signal[:T]
        r1 = ret1[:T]
        r5 = ret5[:T]

        ic1 = rank_ic(sig, r1)
        ic5 = rank_ic(sig, r5)

        all_ics[sym] = {"ic1": float(ic1), "ic5": float(ic5), "sig_mean": float(np.mean(sig)), "sig_std": float(np.std(sig))}
        print(f"{sym}: IC(1d)={ic1:.4f}, IC(5d)={ic5:.4f}, sig_mean={np.mean(sig):.4f}, sig_std={np.std(sig):.4f}")

    # Summary
    avg_ic1 = np.mean([v["ic1"] for v in all_ics.values()])
    avg_ic5 = np.mean([v["ic5"] for v in all_ics.values()])
    print(f"\n=== VP-MACD Factor Summary ===")
    print(f"Avg IC(1d)={avg_ic1:.4f}, Avg IC(5d)={avg_ic5:.4f}")
    if abs(avg_ic1) >= 0.02 or abs(avg_ic5) >= 0.02:
        print("Result: IC threshold PASSED (>=0.02)")
    else:
        print("Result: IC threshold FAILED (<0.02)")

if __name__ == "__main__":
    main()
