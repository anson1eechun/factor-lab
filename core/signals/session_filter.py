"""
Session filter for crypto trading — tag each bar with its session and
identify high-liquidity windows.

All timestamps are UTC. Binance klines use UTC open timestamps.

Session definitions (UTC):
  Asia:      00:00-09:00  (Tokyo opens ~00:00, HK ~01:00)
  London:    07:00-16:00  (London opens 08:00 BST = 07:00 UTC)
  New York:  12:00-21:00  (NY opens 09:30 EST = 13:30 UTC)

High-liquidity windows (for signals, not for holding):
  - Asia open:     00:00-04:00 UTC
  - London open:   07:00-11:00 UTC
  - NY open:       12:00-17:00 UTC
  - Overlap (LON+NY): 12:00-16:00 UTC — highest volume

For 4h bars, each bar covers a 4h window starting at its timestamp:
  00:00 → 00:00-04:00 (Asia open)
  04:00 → 04:00-08:00 (Asia late / pre-London)
  08:00 → 08:00-12:00 (London open)
  12:00 → 12:00-16:00 (LON/NY overlap)
  16:00 → 16:00-20:00 (NY afternoon)
  20:00 → 20:00-00:00 (low vol)

For 1h bars, each bar covers a 1h window.
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# ── session masks (returns boolean Series aligned to df index) ──

def session_mask(df: pd.DataFrame, session: str) -> pd.Series:
    """
    Return boolean mask for bars whose OPEN time falls in the given session.
    df must have a 'timestamp' column (int64 ms) or DatetimeIndex.
    
    session: 'asia' | 'london' | 'new_york' | 'asia_open' | 'london_open' |
             'ny_open' | 'overlap' | 'high_liquidity'
    """
    ts = _get_hours(df)
    
    masks = {
        'asia':       (ts >= 0)  & (ts < 9),
        'london':     (ts >= 7)  & (ts < 16),
        'new_york':   (ts >= 12) & (ts < 21),
        'asia_open':  (ts >= 0)  & (ts < 4),
        'london_open':(ts >= 7)  & (ts < 11),
        'ny_open':    (ts >= 12) & (ts < 17),
        'overlap':    (ts >= 12) & (ts < 16),
    }
    
    if session == 'high_liquidity':
        # Combined: Asia open + London open + NY open + overlap
        return (
            masks['asia_open'] | masks['london_open'] | 
            masks['ny_open'] | masks['overlap']
        )
    
    return masks.get(session, pd.Series(True, index=df.index))


def _get_hours(df: pd.DataFrame) -> pd.Series:
    """Extract UTC hour from df (supports timestamp column or DatetimeIndex)."""
    if 'timestamp' in df.columns:
        dt = pd.to_datetime(df['timestamp'], unit='ms')
    elif isinstance(df.index, pd.DatetimeIndex):
        dt = df.index.to_series()
    else:
        # Try converting the index
        dt = pd.to_datetime(df.index)
    return dt.dt.hour


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add session boolean columns to df. Returns modified copy."""
    df = df.copy()
    for sess in ['asia_open', 'london_open', 'ny_open', 'overlap', 'high_liquidity']:
        df[f'session_{sess}'] = session_mask(df, sess).values
    return df
