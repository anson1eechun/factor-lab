"""SIM-013 鏈上供給/清算(BTC 時序)。資料 data/onchain/*.json(ErcinDedeoglu,CC BY 4.0)。
機制:smart-money 往交易所充值=賣壓→看空。各策略回傳 date-indexed position ∈[-1,1]。
harness onchain_eval.py 會 lag(預設1日)對齊 BTC 價,無前視。"""
import json, os
import numpy as np, pandas as pd

OC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "onchain")


def _load(name):
    d = json.load(open(os.path.join(OC, name + ".json")))
    arr = d if isinstance(d, list) else d.get("data")
    df = pd.DataFrame(arr); df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.floor("D")
    return df.set_index("date")["value"].astype(float).sort_index()


def _z(s, w=20):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()


def whale_short():
    # 鯨魚充值比偏高 → 賣壓 → 做空(level IC 最強, t=-2.31)
    return (-np.tanh(_z(_load("btc_exchange_whale_ratio")))).fillna(0.0)


def miner_short():
    # 礦工往交易所淨流 → 賣壓 → 做空
    return (-np.tanh(_z(_load("btc_miner_netflow_total")))).fillna(0.0)


def supply_composite():
    # 供給壓力綜合:whale↑、miner-netflow↑、exchange-netflow↑ 皆賣壓;stablecoin-netflow↑ 為買力
    whale = _z(_load("btc_exchange_whale_ratio"))
    miner = _z(_load("btc_miner_netflow_total"))
    netflow = _z(_load("btc_exchange_netflow"))
    stable = _z(_load("stablecoin_exchange_netflow"))
    score = (-whale - miner - netflow + stable) / 4.0
    return np.tanh(score).fillna(0.0)
