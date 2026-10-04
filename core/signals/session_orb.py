"""
Session Opening Range Breakout (ORB) Signal.
Classic intraday strategy: first N bars of session define range,
breakout trades the direction. High-liquidity session filter.
"""
import numpy as np
import pandas as pd

def session_orb_signal(df, orb_bars=2, session_filter='high_liquidity'):
    """
    Session Opening Range Breakout signal.
    
    Parameters:
    - orb_bars: number of initial bars to define opening range per session
    - session_filter: which session to trade
    
    Returns: Series of -1, +1, 0
    """
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    n = len(df)
    
    # Session detection by UTC hour
    hours = df.index.hour
    
    # Define sessions
    sessions = {
        'asia':    ((hours >= 0)  & (hours < 9)).values,
        'london':  ((hours >= 7)  & (hours < 16)).values,
        'ny':      ((hours >= 12) & (hours < 21)).values,
    }
    sessions['high_liquidity'] = (
        (hours >= 0) & (hours < 4) |     # Asia open
        (hours >= 7) & (hours < 11) |    # London open
        (hours >= 12) & (hours < 17)     # NY open
    ).values
    
    in_session = sessions.get(session_filter, sessions['high_liquidity'])
    
    signal = np.full(n, 0.0)
    in_range = False  # Are we currently inside an active range?
    range_high = range_low = 0.0
    
    for i in range(orb_bars + 1, n):
        # Detect session transitions: previous bar not in session, current bar in session
        if in_session[i] and not in_session[i-1]:
            # New session starts — compute opening range from first orb_bars
            # Look back to find first bar of this session
            sess_start = i
            for j in range(i-1, max(0, i-24), -1):
                if not in_session[j]:
                    sess_start = j + 1
                    break
            
            # Opening range = first orb_bars of session
            or_count = min(orb_bars, i - sess_start + 1)
            if or_count >= orb_bars:
                start = sess_start
                end = sess_start + orb_bars
                range_high = np.max(h[start:end])
                range_low = np.min(l[start:end])
                in_range = True
            else:
                in_range = False
                continue
        
        if not in_session[i]:
            in_range = False
            continue
        
        if not in_range:
            continue
        
        # Check for breakout
        if h[i] > range_high and l[i] > range_low:
            # Clean breakout up
            signal[i] = +1.0
        elif l[i] < range_low and h[i] < range_high:
            # Clean breakout down
            signal[i] = -1.0
        
        # Range expires after ~8 bars (120 min for 15m bars, longer for 1h)
        # OR when price fully reverses through range
        bar_in_session = (hours[i] - hours[i-1]) % 24
        if bar_in_session > 8 * orb_bars:
            in_range = False
    
    warmup = orb_bars + 1
    signal[:warmup] = np.nan
    return pd.Series(signal, index=df.index, name='session_orb')
