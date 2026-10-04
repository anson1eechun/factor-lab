"""
FSIM: Overnight-Session Drift Reversal (OSDR) — TF=1h
-----------------------------------------------------
Hypothesis (microstructure):
    美盤時段(UTC 13–21,流動性最深)會反向修正亞洲淡時段(UTC 0–7)所累積
    的漂移。每天於 UTC 12 那根 K 線定下方向(對近 24h 內 LOW 窗報酬做反向),
    持倉橫跨美盤、逐根衰減出清,UTC 21 起歸零。

Rules (per 1h bar t;UTC hour 由 timestamp 取):
    ret_t       = close/close.shift(1) - 1
    atr_t       = ((high-low)/close).rolling(168, min_periods=120).mean()   # 7天1h
    LOW         = {0,1,2,3,4,5,6,7}
    low_drift_t = (ret * (hour in LOW)).rolling(24, min_periods=24).sum()    # 近24h LOW 窗累積報酬
    z_t         = low_drift_t / (atr_t * sqrt(8))

    部位(只在美盤持倉,反向修正):
      - t = UTC12      : raw = -clip(z_t,-3,3)/3;死區 |z|<0.8 → pos=0
      - h in {13..20}  : pos = prev_pos * 0.85(逐根衰減,延續前一根)
      - 其餘            : pos = 0(LOW 窗、過渡;UTC 21 起歸零)
      - |pos| 上限 1

Assumptions:
    - timestamp 為毫秒 epoch;hour 由 pd.to_datetime(..., unit='ms').dt.hour 取。
    - 部位序列回傳於 bar t,由 harness 套用至 t→t+1 報酬(本函數不自行 shift)。

Anti look-ahead:
    - ret_t / atr_t / low_drift_t / z_t 皆為僅含 ≤t 資料的 rolling/當根值。
    - UTC12 的方向只用當根 z_t;美盤延續只用前一根已定的部位。
    - 暖機期(rolling 不足)z 為 NaN → pos=0。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LOW = {0, 1, 2, 3, 4, 5, 6, 7}
SESSION = {13, 14, 15, 16, 17, 18, 19, 20}
DECAY = 0.85
DEADZONE = 0.8


def strategy(ohlcv_df: pd.DataFrame, **_: object) -> pd.Series:
    df = ohlcv_df.reset_index(drop=True)
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)

    hour = pd.to_datetime(df["timestamp"], unit="ms").dt.hour

    ret = c / c.shift(1) - 1.0
    atr = ((h - l) / c).rolling(168, min_periods=120).mean()

    low_ret = ret.where(hour.isin(LOW), 0.0)
    low_drift = low_ret.rolling(24, min_periods=24).sum()

    z = low_drift / (atr * np.sqrt(8.0))

    n = len(df)
    pos = np.zeros(n, dtype="float64")
    prev = 0.0
    hr = hour.to_numpy()
    zz = z.to_numpy()

    for t in range(n):
        ht = hr[t]
        if ht == 12:
            zt = zz[t]
            if not np.isfinite(zt) or abs(zt) < DEADZONE:
                cur = 0.0
            else:
                cur = -np.clip(zt, -3.0, 3.0) / 3.0
        elif ht in SESSION:
            cur = prev * DECAY
        else:
            cur = 0.0
        cur = float(np.clip(cur, -1.0, 1.0))
        pos[t] = cur
        prev = cur

    return pd.Series(pos, index=range(n))
