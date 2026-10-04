"""SIM-016 衍生品定位策略(BTC 方向型,日線)。資料 empirical_runs/deriv_btc.pkl。
參考常見策略:
- contra_global_ls:散戶帳戶多空比過高=群眾過度做多→反向做空(contrarian)。
- follow_top_pos:頂級交易者持倉多空比高=聰明錢做多→跟單。
- smart_dumb_div:聰明錢(頂級持倉)vs 散戶(全體帳戶)背離→站聰明錢一方。
- oi_breakout:OI 急增(z 高)視為新部位湧入,搭配近期動能順勢。
回傳 date-indexed position ∈[-1,1]。harness onchain_eval.py 會 lag(防前視)對齊 BTC 價。"""
import os
import numpy as np, pandas as pd

P = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "empirical_runs", "deriv_btc.pkl")


def _load():
    d = pd.read_pickle(P)
    d.index = pd.to_datetime(d["date"])
    return d


def _z(s, w=30):
    return (s - s.rolling(w).mean()) / s.rolling(w).std()


def contra_global_ls():
    d = _load()
    return (-np.tanh(_z(d["global_acct_ls"]))).fillna(0.0).clip(-1, 1)


def follow_top_pos():
    d = _load()
    return (np.tanh(_z(d["top_pos_ls"]))).fillna(0.0).clip(-1, 1)


def smart_dumb_div():
    d = _load()
    div = _z(d["top_pos_ls"]) - _z(d["global_acct_ls"])      # 聰明錢相對散戶更看多
    return (np.tanh(div)).fillna(0.0).clip(-1, 1)


def oi_breakout():
    d = _load()
    oi_z = _z(d["oi"].pct_change(), 30)                       # OI 變化 z
    mom = np.sign(d["oi"].pct_change(5).fillna(0))            # 佔位:OI 自身動能方向(順勢需價,改用onchain harness外接)
    return (np.tanh(oi_z) * mom).fillna(0.0).clip(-1, 1)
