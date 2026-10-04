"""SIM-018 小時框震盪通道回歸(BTC/ETH 永續 15m/30m)。
機制:盤整 regime 中價格觸及通道極端後向中樞回歸;趨勢 regime 用 ER 過濾避開。
規格(預登錄,不掃參數):
- z = (close − SMA48) / std48;進場 z 下穿 −2 做多 / 上穿 +2 做空(僅 regime 通過時)
- regime:Kaufman ER(96) < 其過去 1440 根滾動中位數(僅用 ≤t 資訊)
- 出場:z 回到 0、持倉滿 48 根、或 close 對進場開盤價逆行 > 2×ATR48(進場時值)
- 全部決策用 bar t 收盤資訊,t+1 開盤成交;單一部位不加倉。
回傳 pos:pos[i] = bar i 期間持有的部位(已含 1 bar 執行延遲,無前視)。"""
import numpy as np
import pandas as pd


def _indicators(df, n=48, er_n=96, er_med_w=1440):
    c = df["close"]
    sma = c.rolling(n).mean()
    sd = c.rolling(n).std(ddof=1)
    z = (c - sma) / sd
    tr = np.maximum(df["high"] - df["low"],
                    np.maximum((df["high"] - c.shift(1)).abs(), (df["low"] - c.shift(1)).abs()))
    atr = tr.rolling(n).mean()
    er = (c - c.shift(er_n)).abs() / c.diff().abs().rolling(er_n).sum()
    er_ok = er < er.rolling(er_med_w).median()
    return z, atr, er_ok


def position_series(df, n=48, z_in=2.0, er_n=96, er_med_w=1440, hold_max=48, stop_atr=2.0, **_):
    z, atr, er_ok = _indicators(df, n, er_n, er_med_w)
    zv, av, ok = z.values, atr.values, er_ok.values
    O, C = df["open"].values, df["close"].values
    N = len(df)
    pos = np.zeros(N)
    d = 0            # 目前部位方向(於 bar t 收盤後決定,bar t+1 生效)
    entry_i = -1     # 進場 bar(成交於該 bar open)
    ep = ea = np.nan
    for i in range(N - 1):
        if d == 0:
            if ok[i] and not np.isnan(zv[i]) and not np.isnan(av[i]):
                if zv[i] < -z_in and zv[i - 1] >= -z_in:
                    d, entry_i = +1, i + 1
                elif zv[i] > z_in and zv[i - 1] <= z_in:
                    d, entry_i = -1, i + 1
                if d != 0:
                    ep, ea = O[i + 1], av[i]          # 進場價=下一根開盤(持有期間回顧為已知);ATR=決策時值
                    pos[i + 1] = d
        else:
            exit_now = False
            if i >= entry_i:                          # 進場 bar 收盤起才檢查出場
                if (d == 1 and zv[i] >= 0) or (d == -1 and zv[i] <= 0):
                    exit_now = True                   # 回到中樞
                elif i - entry_i + 1 >= hold_max:
                    exit_now = True                   # 持滿
                elif (d == 1 and C[i] < ep - stop_atr * ea) or (d == -1 and C[i] > ep + stop_atr * ea):
                    exit_now = True                   # 停損
            if exit_now:
                d = 0                                 # bar i+1 開盤平倉 → bar i+1 起空手
            else:
                pos[i + 1] = d
    return pd.Series(pos, index=df.index)


def factor(ohlcv_df, **kw):
    """契約相容:回傳部位序列(已含執行延遲,harness 不需再 shift)。"""
    return position_series(ohlcv_df, **kw)
