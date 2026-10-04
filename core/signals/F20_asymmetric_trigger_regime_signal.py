"""
F20: Asymmetric Trigger Regime Signal (ATRS)
--------------------------------------------
Category: Regime / Meta-Factor
Source: candidates/F20_asymmetric_trigger_regime_signal.md

Formula:
    Donchian entry channel = prior 55d high/low
    Donchian exit channel  = prior 20d high/low
    State ∈ {+1=long, -1=short, 0=neutral} — strictly from t-1 channel + t close

    entry_t = (state_{t-1} ≠ long ∧ state_t == long)
            ∨ (state_{t-1} ≠ short ∧ state_t == short)
    exit_t  = (state_{t-1} == long ∧ state_t ≠ long)
            ∨ (state_{t-1} == short ∧ state_t ≠ short)

    λ_in  = (Σ entries over 120d + 0.5) / 120
    λ_out = (Σ exits over 120d  + 0.5) / 120

    ATRS_raw_t = log(λ_in / λ_out)
    signal_t    = MAD_robust_zscore(ATRS_raw, 180d).shift(1).clip(±3)

Hypothesis:
    When λ_in ≫ λ_out, the market is in a trend-generation phase —
    breakouts persist and trend-following factors should increase exposure.
    When λ_in ≈ λ_out, the market is choppy — breakouts are constantly reversed.
    ATRS is a regime overlay, not a directional signal.

Anti look-ahead:
    Donchian channels are computed with .shift(1) so bar t uses t-1 prices.
    State transitions use current-bar close vs. prior-bar channel.
    Final signal is additionally shifted by 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _mad_robust_zscore(series: pd.Series, window: int) -> pd.Series:
    """MAD-based robust z-score (normalized MAD ≈ std for normal data)."""
    med = series.rolling(window, min_periods=window).median()
    mad = (series - med).abs().rolling(window, min_periods=window).median()
    return 0.6745 * (series - med) / mad.replace(0, np.nan)


def factor(
    ohlcv_df: pd.DataFrame,
    entry_window: int = 55,
    exit_window: int = 20,
    trigger_window: int = 120,
    z_window: int = 180,
    clip_z: float = 3.0,
    **_,
) -> pd.Series:
    df = ohlcv_df.copy()

    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)

    # Guard: non-positive prices
    safe = (h > 0) & (l > 0) & (c > 0)
    h = h.where(safe)
    l = l.where(safe)
    c = c.where(safe)

    # ── 1. Donchian Channels (shifted → no look-ahead) ──
    entry_high = h.rolling(entry_window, min_periods=1).max().shift(1)
    entry_low = l.rolling(entry_window, min_periods=1).min().shift(1)
    exit_high = h.rolling(exit_window, min_periods=1).max().shift(1)
    exit_low = l.rolling(exit_window, min_periods=1).min().shift(1)

    # ── 2. State Machine (vectorized) ──
    n = len(df)
    state = np.zeros(n, dtype=np.int8)

    for t in range(1, n):
        prev = state[t - 1]
        ct = c.values[t]

        # neutral / short → long
        if prev <= 0 and ct > entry_high.values[t]:
            state[t] = 1
        # neutral / long → short
        elif prev >= 0 and ct < entry_low.values[t]:
            state[t] = -1
        # long → neutral
        elif prev == 1 and ct < exit_low.values[t]:
            state[t] = 0
        # short → neutral
        elif prev == -1 and ct > exit_high.values[t]:
            state[t] = 0
        else:
            state[t] = prev

    state_s = pd.Series(state, index=df.index)

    # ── 3. Detect entries / exits ──
    prev_state = state_s.shift(1).fillna(0)

    entries = (
        ((prev_state != 1) & (state_s == 1))
        | ((prev_state != -1) & (state_s == -1))
    ).astype(float)

    exits = (
        ((prev_state == 1) & (state_s != 1))
        | ((prev_state == -1) & (state_s != -1))
    ).astype(float)

    # ── 4. Rolling counts → Poisson intensities ──
    entries_roll = entries.rolling(trigger_window, min_periods=30).sum()
    exits_roll = exits.rolling(trigger_window, min_periods=30).sum()

    eps = 0.5
    lambda_in = (entries_roll + eps) / trigger_window
    lambda_out = (exits_roll + eps) / trigger_window

    # ── 5. ATRS_raw = log(λ_in / λ_out) ──
    atrs_raw = np.log(lambda_in.replace(0, np.nan) / lambda_out.replace(0, np.nan))

    # ── 6. MAD robust z-score ──
    signal = _mad_robust_zscore(atrs_raw, z_window)

    # ── 7. Clip ──
    if clip_z is not None and clip_z > 0:
        signal = signal.clip(lower=-clip_z, upper=clip_z)

    # ── 8. Warm-up mask ──
    warmup = entry_window + trigger_window + z_window  # ~355 bars
    if warmup < len(signal):
        signal.iloc[:warmup] = np.nan
    else:
        signal[:] = np.nan

    # ── 9. Anti look-ahead shift ──
    signal = signal.shift(1)

    signal.name = "F20_asymmetric_trigger_regime_signal"
    return signal.reindex(ohlcv_df.index)
