"""
F11_volatility_compression_indicator.py
Volatility Compression Indicator (VCI)
靈感: 2605.11423 Vol-Volume-Gap Classifier + volatility mean reversion
機制: short-term vol / long-term vol, negative sign → compression = bullish
"""
import pandas as pd
import numpy as np


def factor(df: pd.DataFrame,
           short_window: int = 5,
           long_window: int = 20,
           smoothing_halflife: int = 3) -> pd.Series:
    """
    VCI = -EWM( std(ret, short) / std(ret, long), hl=smoothing )

    Signal direction: negative VCI → vol compression → bullish
    """
    ret = df["close"].pct_change()
    short_vol = ret.rolling(short_window, min_periods=max(3, short_window//2)).std()
    long_vol = ret.rolling(long_window, min_periods=max(5, long_window//2)).std()
    long_vol = long_vol.replace(0, np.nan)

    vci_raw = short_vol / long_vol  # >1: expanding, <1: compressing
    vci = -vci_raw.ewm(halflife=smoothing_halflife).mean()

    return vci
