"""
F12_bayesian_drift_uncertainty_signal.py
Bayesian Drift Uncertainty Signal (BDUS)
靈感: 2602.16862 Entropy Regularization — 信念愈強，部位變異應愈大
機制: drift / drift_uncertainty, non-linear squashing at extremes
"""
import pandas as pd
import numpy as np


def factor(df: pd.DataFrame,
           drift_halflife: int = 20,
           drift_vol_window: int = 60) -> pd.Series:
    """
    BDUS = z / sqrt(1 + |z|)   where z = drift / sigma(drift_errors)

    Non-linear squashing: strong signals get compressed (anti-overfitting)
    """
    ret = df["close"].pct_change()

    # EWM drift estimate
    drift = ret.ewm(halflife=drift_halflife).mean()

    # Drift uncertainty: std of EWM prediction errors
    drift_error = ret - drift.shift(1)
    drift_sigma = drift_error.rolling(drift_vol_window,
                                      min_periods=max(10, drift_vol_window//3)).std()

    drift_sigma = drift_sigma.replace(0, np.nan)
    z = drift / drift_sigma

    # Non-linear compression: at |z|→∞, signal → sign(z)
    signal = z / np.sqrt(1 + np.abs(z))

    return signal
