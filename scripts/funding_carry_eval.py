#!/usr/bin/env python3
"""Funding carry 橫截面評估(可重用)。signal = -rolling_mean(funding, smooth)。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/funding_carry_eval.py [smooth] [hold] [cost_bps]"""
import sys,os,numpy as np,pandas as pd
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.crosssec_eval as X
def main():
    smooth=int(sys.argv[1]) if len(sys.argv)>1 else 7
    hold=int(sys.argv[2]) if len(sys.argv)>2 else 10
    cost=float(sys.argv[3]) if len(sys.argv)>3 else 10.0
    uni=pd.read_pickle(X.UNI); fund=pd.read_pickle(os.path.join(os.path.dirname(X.UNI),"funding_1d.pkl"))
    fw={}
    for co,df in uni.items():
        idx=pd.to_datetime(df["timestamp"],unit="ms"); c=df["close"].astype(float)
        fw[co]=pd.Series((c.shift(-1)/c-1).values,index=idx)
    F=pd.DataFrame(fw).sort_index(); sg={}
    for co,d in fund.items():
        if co not in uni: continue
        idx=pd.to_datetime(d["timestamp"],unit="ms"); s=pd.Series(d["funding"].values,index=idx)
        sg[co]=(-s.rolling(smooth,min_periods=max(2,smooth//2)).mean()).shift(1)
    S=pd.DataFrame(sg).reindex(F.index); S,F=S.align(F,join="inner")
    import json; print(json.dumps({"signal":f"-funding_{smooth}dmean","hold":hold,"cost_bps":cost,**X.evaluate(S,F,cost,np.sqrt(365),hold)},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
