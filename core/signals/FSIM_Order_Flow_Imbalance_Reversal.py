"""SIM-011 訂單流失衡反轉(cross-sectional)。
機制:當日 taker 主動買盤失衡 TFI=(buy-sell)/vol 越高(追高者多),次日相對報酬越低 → 反轉。
因子值 = -z(TFI)(高分=低近期主動買壓=預期相對強)。資料:universe_flow_1d.pkl。"""
import numpy as np, pandas as pd


def factor(df):
    tfi = pd.Series(df["tfi"].astype(float).values)
    z = (tfi - tfi.rolling(20).mean()) / tfi.rolling(20).std()
    return (-z).values


def factor_raw(df):
    return (-df["tfi"].astype(float)).values
