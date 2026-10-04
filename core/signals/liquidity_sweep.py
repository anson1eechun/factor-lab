"""
Liquidity Sweep Signal — detects stop hunts and reversals.
Concept: When price breaks a recent structural high/low and then reverses,
it signals a liquidity grab (stop hunt) — trade the reversal.
"""
import numpy as np
import pandas as pd

def liquidity_sweep_signal(df, swing_lookback=20, sweep_confirm=2):
    """
    Detect liquidity sweeps and return directional signals.
    
    Parameters:
    - swing_lookback: bars to look back for swing high/low detection
    - sweep_confirm: bars after sweep to confirm reversal
    
    Returns: Series of -1 (bearish after sweep high), +1 (bullish after sweep low), 0 (none)
    """
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    n = len(df)
    
    signal = np.full(n, 0.0)
    
    # Track recent swing highs and lows
    swing_highs = []  # (index, price)
    swing_lows = []   # (index, price)
    
    for i in range(swing_lookback + 2, n - sweep_confirm):
        # Detect swing high: i-swing_lookback is the peak of a window
        window_start = i - swing_lookback
        window_end = i
        mid = i - swing_lookback // 2
        
        # Is mid a swing high? (highest in window, surrounded by lower)
        if (h[mid] >= np.max(h[window_start:window_end+1]) and
            mid > window_start + 3 and mid < window_end - 3):
            swing_highs.append((mid, h[mid]))
        
        # Is mid a swing low?
        if (l[mid] <= np.min(l[window_start:window_end+1]) and
            mid > window_start + 3 and mid < window_end - 3):
            swing_lows.append((mid, l[mid]))
        
        # Prune old swings (> 3x lookback ago)
        cutoff = i - 3 * swing_lookback
        swing_highs = [(idx, px) for idx, px in swing_highs if idx > cutoff]
        swing_lows = [(idx, px) for idx, px in swing_lows if idx > cutoff]
        
        # Check for sweep: price breaks swing level then reverses
        # Sweep high → bearish (price went above swing high, then fell back)
        for idx, price in swing_highs:
            if h[i] > price and c[i+sweep_confirm] < price:
                signal[i] = -1.0
                # Remove this swing high (consumed)
                swing_highs = [(j, p) for j, p in swing_highs if j != idx]
                break
        
        # Sweep low → bullish (price went below swing low, then bounced back)
        for idx, price in swing_lows:
            if l[i] < price and c[i+sweep_confirm] > price:
                signal[i] = +1.0
                swing_lows = [(j, p) for j, p in swing_lows if j != idx]
                break
    
    warmup = swing_lookback + 2 + sweep_confirm
    signal[:warmup] = np.nan
    return pd.Series(signal, index=df.index, name='liquidity_sweep')
