"""
F13_tail_event_asymmetry_ratio.py
Tail-Event Asymmetry Ratio (TEAR)
靈感: 2605.26890 Nonlinear & Heavy-Tailed Predictability
機制: 正尾/負尾事件密度不對稱 → 預測方向延續
"""
import pandas as pd
import numpy as np


def factor(df: pd.DataFrame,
           tail_window: int = 60,
           tail_sigma: float = 1.5,
           smoothing_halflife: int = 5) -> pd.Series:
    """
    TEAR = upper_tail_density / (upper + lower_tail_density)
    signal = EWM(TEAR - 0.5, hl=5)

    Positive TEAR skew → optimistic → trend continuation
    Negative TEAR skew → pessimistic → downward pressure
    """
    ret = df["close"].pct_change()
    vol = ret.rolling(tail_window,
                      min_periods=max(10, tail_window//3)).std()

    # Tail event masks
    upper_mask = ret > vol * tail_sigma
    lower_mask = ret < -vol * tail_sigma

    # Rolling density of tail events (EMA for smoothness)
    upper_density = upper_mask.astype(float).ewm(span=tail_window).mean()
    lower_density = lower_mask.astype(float).ewm(span=tail_window).mean()

    total_density = upper_density + lower_density
    total_density = total_density.replace(0, np.nan)

    tear = upper_density / total_density  # [0, 1]
    signal = (tear - 0.5).ewm(halflife=smoothing_halflife).mean()

    return signal
