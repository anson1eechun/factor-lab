"""
FSMC-OrderBlock: Order Block / Breaker Block (SMC/ICT)

Definition: The last opposite-direction candle before a strong impulsive move.
ICT teaches that these order blocks act as support/resistance when price returns.

Mechanics:
  1. Identify impulsive moves: consecutive candles in same direction
     with cumulative move exceeding threshold (e.g. 3+ bars, > 1.5% cumulative).
  2. Walk back to the last opposite-color candle before the impulse.
  3. That candle's range (low to high) is the order block zone.
  4. Signal: when price returns to the OB zone later, expect reversal.

  Bullish OB: last red candle before a strong bullish impulse → buy zone.
  Bearish OB: last green candle before a strong bearish impulse → sell zone.

Signal: +1 = price entering bullish OB (support), -1 = price entering bearish OB (resistance)

Anti look-ahead: OB detected at t, zone active from t+1 onward. Entry checked at current bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    impulse_bars: int = 3,
    impulse_pct: float = 1.5,
    ob_lookback: int = 30,
    **_: object,
) -> pd.Series:
    """
    Parameters
    ----------
    impulse_bars : int
        Minimum consecutive same-direction candles for an impulse.
    impulse_pct : float
        Minimum cumulative price change (%) to qualify as impulse.
    ob_lookback : int
        Max bars an order block stays active.
    """
    df = ohlcv_df.copy()

    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    n = len(df)

    signal = np.zeros(n)

    # Track active OB zones: list of (start_idx, low, high, direction)
    active_obs: list[tuple[int, float, float, int]] = []

    for i in range(impulse_bars + 1, n):
        # --- Detect new impulse ending at i ---
        # Check the last impulse_bars bars
        candles_bull = all(c[j] > o[j] for j in range(i - impulse_bars + 1, i + 1))
        candles_bear = all(c[j] < o[j] for j in range(i - impulse_bars + 1, i + 1))

        if candles_bull or candles_bear:
            pct_move = abs(c[i] - o[i - impulse_bars + 1]) / o[i - impulse_bars + 1] * 100

            if pct_move >= impulse_pct:
                # Walk back to find the last opposite-color candle before this impulse
                impulse_start = i - impulse_bars + 1
                look_back_start = max(0, impulse_start - 10)

                if candles_bull:
                    # Strong bullish impulse → look for last bearish (red) candle
                    for j in range(impulse_start - 1, look_back_start - 1, -1):
                        if c[j] < o[j]:  # red candle
                            zone_low = l[j]
                            zone_high = h[j]
                            active_obs.append((i, zone_low, zone_high, +1))
                            break
                else:
                    # Strong bearish impulse → look for last bullish (green) candle
                    for j in range(impulse_start - 1, look_back_start - 1, -1):
                        if c[j] > o[j]:  # green candle
                            zone_low = l[j]
                            zone_high = h[j]
                            active_obs.append((i, zone_low, zone_high, -1))
                            break

        # --- Expire old OBs ---
        active_obs = [(idx, lo, hi, d) for idx, lo, hi, d in active_obs
                      if i - idx <= ob_lookback]

        # --- Check if price touches OB zone ---
        bull_signal = 0
        bear_signal = 0
        unmitigated: list[tuple[int, float, float, int]] = []

        for idx, lo, hi, d in active_obs:
            mitigated = False
            if d == +1:  # bullish OB = buy zone
                if l[i] <= hi and c[i] >= lo:  # price dipped into zone
                    bull_signal += 1
                    mitigated = True
            else:  # bearish OB = sell zone
                if h[i] >= lo and c[i] <= hi:  # price rallied into zone
                    bear_signal -= 1
                    mitigated = True

            if not mitigated:
                unmitigated.append((idx, lo, hi, d))

        active_obs = unmitigated
        net = bull_signal + bear_signal
        signal[i] = net if net != 0 else 0.0

    warmup = ob_lookback + impulse_bars + 5
    signal[:warmup] = np.nan

    result = pd.Series(signal, index=df.index)
    result = result.shift(1)
    result.name = "FSMC_OrderBlock"
    return result.reindex(ohlcv_df.index)
