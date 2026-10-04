"""
FSMC_FVG: Fair Value Gap — CONTINUATION version (v2)

Empirically: on BTC daily, price entering an FVG zone CONTINUES in the same
direction rather than reversing. This makes FVG a momentum/continuation signal.

  Bullish FVG: candle_0.low > candle_2.high (gap down, displacement lower)
    → When price later drops into this zone → BEARISH continuation (-1)
  Bearish FVG: candle_0.high < candle_2.low (gap up, displacement higher)
    → When price later rises into this zone → BULLISH continuation (+1)

Signal: +1 bullish continuation, -1 bearish continuation.

Anti look-ahead: FVG detected at t, zone valid from t+1. shift(1) applied.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def factor(
    ohlcv_df: pd.DataFrame,
    fvg_lookback: int = 20,
    min_gap_pct: float = 0.05,
    **_: object,
) -> pd.Series:
    df = ohlcv_df.copy()

    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    n = len(df)

    signal = np.full(n, 0.0)

    active_zones: list[tuple[int, float, float, int]] = []
    # direction: +1 = bullish FVG (gap down), -1 = bearish FVG (gap up)

    for i in range(2, n):
        avg_price = c[i]

        # Detect new FVG
        candle_0_lo = l[i - 2]
        candle_0_hi = h[i - 2]
        candle_2_lo = l[i]
        candle_2_hi = h[i]

        gap_threshold = avg_price * min_gap_pct / 100.0

        # Bullish FVG: displaced lower (candle_0 low > candle_2 high)
        if candle_0_lo - candle_2_hi > gap_threshold:
            zone_bottom = candle_2_hi
            zone_top = candle_0_lo
            active_zones.append((i, zone_bottom, zone_top, +1))

        # Bearish FVG: displaced higher (candle_0 high < candle_2 low)
        if candle_2_lo - candle_0_hi > gap_threshold:
            zone_bottom = candle_0_hi
            zone_top = candle_2_lo
            active_zones.append((i, zone_bottom, zone_top, -1))

        # Expire old zones
        active_zones = [(idx, bot, top, d)
                        for idx, bot, top, d in active_zones
                        if i - idx <= fvg_lookback]

        # Check mitigation → CONTINUATION signal
        bull_signal = 0
        bear_signal = 0
        unmitigated = []

        for idx, bot, top, d in active_zones:
            mitigated = False
            if d == +1:  # bullish FVG = displaced lower → continuation DOWN
                if l[i] <= top and l[i] >= bot:
                    bear_signal -= 1  # bearish continuation
                    mitigated = True
            else:  # bearish FVG = displaced higher → continuation UP
                if h[i] >= bot and h[i] <= top:
                    bull_signal += 1  # bullish continuation
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
    result = result.shift(1)
    result.name = "FSMC_FVG"
    return result.reindex(ohlcv_df.index)
