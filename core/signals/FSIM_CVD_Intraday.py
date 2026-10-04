"""SIM-012 日內訂單流(CVD)。資料 {asset}_flow_{tf}.pkl(close/volume/taker_buy/tfi)。
- cvd_mom:CVD=cumsum(2·taker_buy−vol) 動量,斜率>0 做多(續勢假設)。
- tfi_rev:近 bar 主動買壓 z 分數反向(反轉,探索中唯一顯著訊號)。
position ∈[-1,1],bar t 用至 t 收盤資訊,持有到 t+1(無前視)。"""
import numpy as np, pandas as pd


def _cols(df):
    c = df["close"].astype(float).reset_index(drop=True)
    vol = df["volume"].astype(float).reset_index(drop=True)
    tb = df["taker_buy"].astype(float).reset_index(drop=True)
    tfi = df["tfi"].astype(float).reset_index(drop=True)
    return c, vol, tb, tfi


def cvd_mom(df, k=6):
    c, vol, tb, tfi = _cols(df)
    cvd = (2 * tb - vol).cumsum()
    slope = cvd - cvd.shift(k)
    z = (slope - slope.rolling(50).mean()) / slope.rolling(50).std()
    return np.tanh(z).fillna(0.0).clip(-1, 1).values


def tfi_rev(df):
    c, vol, tb, tfi = _cols(df)
    z = (tfi - tfi.rolling(20).mean()) / tfi.rolling(20).std()
    return (-np.tanh(z)).fillna(0.0).clip(-1, 1).values
