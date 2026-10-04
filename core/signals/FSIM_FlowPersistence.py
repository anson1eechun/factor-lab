"""
FSIM: Flow Persistence (taker-flow directional persistence, cross-sectional)
----------------------------------------------------------------------------
Hypothesis:
    Coins whose active-buy net inflow (tfi) has been *directionally consistent*
    over the past N days earn higher relative forward returns (order-flow drift,
    momentum-like rather than mean-reverting).

Formula (per coin, only that coin's own time series):
    1. Rolling-standardise tfi to remove per-coin scale:
        z_t = (tfi_t - rolling_mean(tfi, z_window))
              / rolling_std(tfi, z_window, ddof=1)        (std==0 -> NaN)
       then clip z to +/- clip (tame single-day blow-out volume = tail-robust).
    2. Persistence signal over N = n days:
        consist_t = mean_{k=0..n-1} sign(tfi_{t-k})       (in [-1, 1], pure direction)
        mag_t     = mean_{k=0..n-1} z_{t-k}               (clipped average strength)
        raw_t     = consist_t * mag_t
    3. Return raw (per-coin time-series raw signal; the harness handles the
       cross-sectional daily rank IC / quantile sorting itself).

Anti look-ahead:
    - All rolling / mean / sign aggregations use only data through t.
    - Final signal = raw.shift(1): the signal at t uses only t-1 and earlier,
      matching the harness t -> t+1 forward return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def factor(
    flow_df: pd.DataFrame,
    n: int = 10,
    z_window: int = 60,
    clip: float = 3.0,
    **_: object,
) -> pd.Series:
    df = flow_df.copy()

    tfi = df["tfi"].astype(float)

    # 1. Rolling z-score of tfi, then clip to tame tail days.
    mean = tfi.rolling(z_window, min_periods=z_window).mean()
    std = tfi.rolling(z_window, min_periods=z_window).std(ddof=1)
    z = (tfi - mean) / std.replace(0, np.nan)
    z = z.clip(lower=-clip, upper=clip)

    # 2. Persistence main signal over n days.
    consist = np.sign(tfi).rolling(n, min_periods=n).mean()
    mag = z.rolling(n, min_periods=n).mean()
    raw = consist * mag

    # 3. Shift by 1 to avoid look-ahead.
    signal = raw.shift(1)
    signal.name = "FSIM_FlowPersistence"
    return signal.reindex(flow_df.index)
