"""SIM-014 風控 overlay 風險訊號(越高越危險)。回傳 date-indexed Series。
資料:data/onchain/*.json(whale)、empirical_runs/funding_1d.pkl(BTC funding)。"""
import json, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OC = os.path.join(ROOT, "data", "onchain")


def _oc(name):
    d = json.load(open(os.path.join(OC, name + ".json")))
    arr = d if isinstance(d, list) else d.get("data")
    df = pd.DataFrame(arr); df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.floor("D")
    return df.set_index("date")["value"].astype(float).sort_index()


def whale_risk():
    return _oc("btc_exchange_whale_ratio")          # 鯨魚充值比高 = 賣壓危險


def funding_risk():
    f = pd.read_pickle(os.path.join(ROOT, "empirical_runs", "funding_1d.pkl"))["BTC"]
    s = pd.Series(f["funding"].astype(float).values,
                  index=pd.to_datetime(f["timestamp"], unit="ms").dt.floor("D"))
    return s.sort_index()                            # funding 高 = 多頭過度槓桿危險


def combo_risk():
    w = whale_risk(); f = funding_risk()
    wz = (w - w.rolling(60).mean()) / w.rolling(60).std()
    fz = (f - f.rolling(60).mean()) / f.rolling(60).std()
    return (wz.reindex(w.index.union(f.index)).ffill() + fz.reindex(w.index.union(f.index)).ffill()) / 2
