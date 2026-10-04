"""
FSMC_FVG_Session: Fair Value Gap with session-aware filtering.

Same FVG continuation logic as FSMC_FVG (v2), but signals only fire when
the bar falls in a high-liquidity session (Asia open, London open, NY open,
or London/NY overlap). Signals during low-volume periods (Asia late,
NY afternoon, overnight) are suppressed.

This directly addresses the SMC premise that "smart money" activity
concentrates in high-volume sessions. If FVG has predictive power,
filtering by session should improve signal-to-noise ratio.

Parameters:
  fvg_lookback: int = 20     max bars an FVG zone stays active
  min_gap_pct:  float = 0.5  minimum gap as % of price to qualify as FVG
  session_filter: str = 'high_liquidity'  which session mask to use
      Options: 'high_liquidity' (default), 'overlap', 'asia_open',
               'london_open', 'ny_open', or 'all' (no filter)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_filter import session_mask


def factor(
    ohlcv_df: pd.DataFrame,
    fvg_lookback: int = 20,
    min_gap_pct: float = 0.5,
    session_filter: str = 'high_liquidity',
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    n = len(df)

    signal = np.full(n, 0.0)

    # Session mask: which bars are in the target liquidity window
    in_session = session_mask(df, session_filter).values

    active_zones: list[tuple[int, float, float, int]] = []

    for i in range(2, n):
        avg_price = c[i]

        # ── Detect new FVG (always, regardless of session) ──
        candle_0_lo = l[i - 2]
        candle_0_hi = h[i - 2]
        candle_2_lo = l[i]
        candle_2_hi = h[i]

        gap_threshold = avg_price * min_gap_pct / 100.0

        # Bullish FVG: displaced lower (candle_0.low > candle_2.high)
        if candle_0_lo - candle_2_hi > gap_threshold:
            zone_bottom = candle_2_hi
            zone_top = candle_0_lo
            active_zones.append((i, zone_bottom, zone_top, +1))

        # Bearish FVG: displaced higher (candle_0.high < candle_2.low)
        if candle_2_lo - candle_0_hi > gap_threshold:
            zone_bottom = candle_0_hi
            zone_top = candle_2_lo
            active_zones.append((i, zone_bottom, zone_top, -1))

        # ── Expire old zones ──
        active_zones = [
            (idx, bot, top, d)
            for idx, bot, top, d in active_zones
            if i - idx <= fvg_lookback
        ]

        # ── Check mitigation → signal (ONLY if bar is in-session) ──
        if not in_session[i]:
            continue  # suppress signals outside high-liquidity windows

        bull_signal = 0
        bear_signal = 0
        unmitigated = []

        for idx, bot, top, d in active_zones:
            mitigated = False
            if d == +1:  # bullish FVG = displaced lower → continuation DOWN
                if l[i] <= top and l[i] >= bot:
                    bear_signal -= 1
                    mitigated = True
            else:  # bearish FVG = displaced higher → continuation UP
                if h[i] >= bot and h[i] <= top:
                    bull_signal += 1
                    mitigated = True

            if not mitigated:
                unmitigated.append((idx, bot, top, d))

        active_zones = unmitigated
        net = bull_signal + bear_signal
        if net != 0:
            signal[i] = net

    # Warmup
    warmup = fvg_lookback + 2
    signal[:warmup] = np.nan

    result = pd.Series(signal, index=df.index)
    result = result.shift(1)  # anti-lookahead
    result.name = f"FSMC_FVG_Session({session_filter})"
    return result.reindex(ohlcv_df.index)
