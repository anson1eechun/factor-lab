"""
Volume-Weighted Momentum Signal.
Concept: High volume + strong directional close = institutional conviction.
Only fires when volume is elevated (z-score > threshold).
"""
import numpy as np
import pandas as pd

def volume_momentum_signal(df, vol_lookback=20, vol_threshold=1.0):
    """
    Compute volume-weighted momentum signal.
    
    Parameters:
    - vol_lookback: bars for volume z-score computation
    - vol_threshold: minimum volume z-score to trigger signal
    
    Returns: Series of -1 (bearish conviction), +1 (bullish conviction), 0 (no signal)
    """
    o = df["open"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    v = df["volume"].values.astype(float)
    n = len(df)
    
    signal = np.full(n, 0.0)
    
    for i in range(vol_lookback, n):
        # Body ratio: how much of the range was directional
        hl_range = h[i] - l[i]
        if hl_range == 0:
            continue
        body_ratio = (c[i] - o[i]) / hl_range  # -1 to +1
        
        # Direction: just sign of body
        direction = np.sign(body_ratio)
        
        # Volume z-score
        vol_window = v[i-vol_lookback:i]
        vol_mean = np.mean(vol_window)
        vol_std = np.std(vol_window)
        if vol_std == 0:
            continue
        vol_z = (v[i] - vol_mean) / vol_std
        
        # Only fire on high volume with conviction
        if abs(vol_z) > vol_threshold and abs(body_ratio) > 0.3:
            signal[i] = direction * min(abs(vol_z) / vol_threshold, 2.0) / 2.0
            # Clamp to ±1
            signal[i] = np.clip(signal[i], -1.0, 1.0)
    
    warmup = vol_lookback
    signal[:warmup] = np.nan
    return pd.Series(signal, index=df.index, name='volume_momentum')
