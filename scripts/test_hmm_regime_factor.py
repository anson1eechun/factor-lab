#!/usr/bin/env python3
"""
HMM Regime Timing Factor — test script.
Based on paper 2605.27848: Regime-Based Portfolio Allocation Using HMM + RL.
Uses: returns, volatility, vol-of-vol, range ratio as HMM features.
"""
import sys, math
sys.path.insert(0, '/home/anson/factor-lab')

import numpy as np
from core.adapters.crypto import CryptoAdapter
from core.metrics import rank_ic, ic_series_stats

def main():
    # Fetch data
    a = CryptoAdapter()
    ohlcv_dict = {}
    for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']:
        ohlcv_dict[sym] = a.ohlcv(sym, timeframe='1d')

    # Build aligned closes
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
    ts_map = {}
    for sym, bars in ohlcv_dict.items():
        for b in bars:
            ts_map[b['ts']] = ts_map.get(b['ts'], {})
            ts_map[b['ts']][sym] = b
    ts_list = sorted(ts_map.keys())

    # Filter: keep only timestamps where all 4 assets have data
    valid_ts = [t for t in ts_list if all(s in ts_map[t] for s in symbols)]
    closes = []
    for t in valid_ts:
        closes.append([ts_map[t][s]['close'] for s in symbols])
    closes = np.array(closes, dtype=np.float64)
    T, N_assets = closes.shape
    print(f"Aligned data: T={T}, assets={N_assets}")

    # Build HMM features
    # [mean_return, mean_abs_ret, std_ret, mean_range_ratio]
    F = np.zeros((T, 4))
    for t in range(1, T):
        r = closes[t] / closes[t-1] - 1
        F[t] = [
            np.mean(r),
            np.mean(np.abs(r)),
            np.std(r),
            np.mean(np.abs(r)),
        ]
    F[0] = F[1]  # pad first row

    # Standardize
    mu_f = F.mean(0)
    std_f = F.std(0) + 1e-10
    Fz = (F - mu_f) / std_f

    # ============ HMM (2-state, diagonal cov, Baum-Welch) ============
    K = 2
    D = Fz.shape[1]
    np.random.seed(42)

    pi = np.ones(K) / K
    A = np.ones((K, K)) / K
    mu = np.random.randn(K, D) * 0.5
    sigma = np.ones((K, D)) * 1.0

    def log_gauss(x, m, s):
        # Diagonal
        return -0.5 * np.sum(np.log(2*math.pi*s) + (x-m)**2 / s)

    eps = 1e-300
    for it in range(60):
        # Forward
        alpha = -np.inf * np.ones((T, K))
        for t in range(T):
            for k in range(K):
                lg = log_gauss(Fz[t], mu[k], sigma[k])
                if t == 0:
                    alpha[t, k] = np.log(max(pi[k], eps)) + lg
                else:
                    a_val = -np.inf
                    for j in range(K):
                        v = alpha[t-1, j] + np.log(max(A[j, k], eps)) + lg
                        if v > a_val:
                            a_val = v
                    alpha[t, k] = a_val

        # Backward
        beta = np.zeros((T, K))
        for t in range(T-2, -1, -1):
            for k in range(K):
                b_val = -np.inf
                for j in range(K):
                    lg = log_gauss(Fz[t+1], mu[j], sigma[j])
                    v = np.log(max(A[k, j], eps)) + beta[t+1, j] + lg
                    if v > b_val:
                        b_val = v
                beta[t, k] = b_val

        # Gamma
        gamma = np.zeros((T, K))
        logZ = 0.0
        for t in range(T):
            logM = max(alpha[t, k] + beta[t, k] for k in range(K))
            if t == 0:
                logZ = logM
            for k in range(K):
                val = alpha[t, k] + beta[t, k] - logM
                gamma[t, k] = np.exp(val) if not np.isinf(val) else 0.0

        # M-step: pi
        new_pi = gamma[0] + eps
        new_pi /= new_pi.sum()

        # M-step: A
        new_A = np.zeros((K, K))
        for i in range(K):
            denom = 0.0
            for j in range(K):
                s = 0.0
                for t in range(T-1):
                    lg = log_gauss(Fz[t+1], mu[j], sigma[j])
                    s += np.exp(alpha[t, i] + np.log(max(A[i, j], eps)) + lg + beta[t+1, j])
                new_A[i, j] = s
                denom += s
            if denom > eps:
                new_A[i] /= denom
            else:
                new_A[i] = 1.0 / K

        # M-step: mu, sigma
        new_mu = np.zeros((K, D))
        new_sigma = np.zeros((K, D))
        for k in range(K):
            Nk = gamma[:, k].sum()
            if Nk < 1:
                continue
            for d in range(D):
                new_mu[k, d] = np.sum(gamma[:, k] * Fz[:, d]) / Nk
            for d in range(D):
                new_sigma[k, d] = np.sum(gamma[:, k] * (Fz[:, d] - new_mu[k, d])**2) / Nk
            new_sigma[k] = np.maximum(new_sigma[k], 1e-6)

        # Convergence
        d_mu = float(np.abs(new_mu - mu).max())
        d_A = float(np.abs(new_A - A).max())
        mu, A, sigma, pi = new_mu, new_A, new_sigma, new_pi
        if d_mu < 1e-5 and d_A < 1e-5 and it > 5:
            print(f"Converged iter {it}, logLik={logZ:.2f}")
            break

    # Recompute final gamma
    alpha = -np.inf * np.ones((T, K))
    for t in range(T):
        for k in range(K):
            lg = log_gauss(Fz[t], mu[k], sigma[k])
            if t == 0:
                alpha[t, k] = np.log(max(pi[k], 1e-300)) + lg
            else:
                a_val = -np.inf
                for j in range(K):
                    v = alpha[t-1, j] + np.log(max(A[j, k], 1e-300)) + lg
                    if v > a_val:
                        a_val = v
                alpha[t, k] = a_val

    beta = np.zeros((T, K))
    for t in range(T-2, -1, -1):
        for k in range(K):
            b_val = -np.inf
            for j in range(K):
                lg = log_gauss(Fz[t+1], mu[j], sigma[j])
                v = np.log(max(A[k, j], 1e-300)) + beta[t+1, j] + lg
                if v > b_val:
                    b_val = v
            beta[t, k] = b_val

    gamma = np.zeros((T, K))
    for t in range(T):
        logM = max(alpha[t, k] + beta[t, k] for k in range(K))
        for k in range(K):
            val = alpha[t, k] + beta[t, k] - logM
            gamma[t, k] = np.exp(val) if not np.isinf(val) else 0.0

    # ============ Factor ============
    signal = gamma[:, 0] - gamma[:, 1]  # positive = State 0 favored

    # Compute cross-sectional average forward returns
    ret_1d = np.array([float(np.mean(closes[t+1] / closes[t] - 1)) for t in range(T-1)])
    ret_5d = np.array([float(np.mean(closes[t+5] / closes[t] - 1)) for t in range(T-5)])

    # IC (1-day)
    m1 = min(len(signal), len(ret_1d))
    ic1 = rank_ic(signal[:m1].tolist(), ret_1d[:m1].tolist())

    # IC (5-day)
    m5 = min(len(signal), len(ret_5d))
    ic5 = rank_ic(signal[:m5].tolist(), ret_5d[:m5].tolist())

    print(f"\n=== HMM Regime Factor: Proposer + Empiricist Summary ===")
    print(f"Transition:\n{A}")
    print(f"Mu:\n{mu}")
    print(f"Signal: mean={signal.mean():.4f}, std={signal.std():.4f}")
    print(f"Rank-IC (1-day): {ic1:.4f}")
    print(f"Rank-IC (5-day): {ic5:.4f}")
    print(f"ic_min_abs=0.02: 1-day {'PASS' if abs(ic1) > 0.02 else 'FAIL'}, 5-day {'PASS' if abs(ic5) > 0.02 else 'FAIL'}")

    # Also check: does high-prob State 0 correlate with lower vol?
    # Split into high-signal vs low-signal
    mid = np.median(signal)
    high_sig = [ret_5d[t] for t in range(len(ret_5d)) if signal[t] > mid]
    low_sig  = [ret_5d[t] for t in range(len(ret_5d)) if signal[t] <= mid]
    if high_sig and low_sig:
        print(f"5d ret (high signal): mean={np.mean(high_sig):.6f}, std={np.std(high_sig):.6f}")
        print(f"5d ret (low signal):  mean={np.mean(low_sig):.6f}, std={np.std(low_sig):.6f}")

if __name__ == "__main__":
    main()
