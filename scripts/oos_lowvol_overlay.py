#!/usr/bin/env python3
"""預註冊 OOS 驗證 — 低波動 overlay(逆波動加權 long-only vs 等權)。
鎖定設定:RV60(日)、逆波動權重、週頻再平衡(hold=5)、10bps、IS≤2024-12-31 / OOS≥2025-01-01。
衡量:主動報酬 a=r_tilt−r_EW 的 t、IR、MaxDD。裁決規則(預註冊):
  VALIDATE ⟺ OOS a 年化 t≥2 且 IR>0.5 且 主動報酬 MaxDD<30%;否則 REJECT。
不掃參、不挑變體。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/oos_lowvol_overlay.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scripts.crosssec_eval import MIN_COINS

UNI = "/home/anson/factor-lab/empirical_runs/universe_1d.pkl"
ANN = np.sqrt(365)
HOLD = 5                       # 週頻再平衡
COST = 10.0
SPLIT = pd.Timestamp("2025-01-01")


def active_stats(a):
    a = pd.Series(a).dropna()
    if len(a) < 2 or not a.std():
        return {}
    eq = (1 + a).cumprod()
    return {"active_ann": round(float(a.mean()*ANN**2), 4),
            "IR": round(float(a.mean()/a.std(ddof=1)*ANN), 3),
            "active_t": round(float(a.mean()/(a.std(ddof=1)/np.sqrt(len(a)))), 3),
            "active_maxdd": round(float((eq/eq.cummax()-1).min()), 4),
            "n_days": int(len(a))}


def main():
    uni = pd.read_pickle(UNI)
    RV, F = {}, {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms"); c = df["close"].astype(float)
        RV[co] = pd.Series(np.log(c).diff().rolling(60, min_periods=30).std(ddof=1).shift(1).values, index=idx)
        F[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
    RV = pd.DataFrame(RV).sort_index(); F = pd.DataFrame(F).reindex(RV.index)

    rTilt, rEW, wT, wE, since = [], [], None, None, 10**9
    for dt in RV.index:
        v = RV.loc[dt]; m = v.notna() & F.loc[dt].notna() & (v > 0)
        if m.sum() < MIN_COINS:
            rTilt.append(float((wT*F.loc[dt].fillna(0)).sum()) if wT is not None else np.nan)
            rEW.append(float((wE*F.loc[dt].fillna(0)).sum()) if wE is not None else np.nan)
            continue
        if since >= HOLD:
            vv = v[m]; iv = 1.0/vv
            nwT = pd.Series(0.0, index=RV.columns); nwT[vv.index] = (iv/iv.sum()).values
            nwE = pd.Series(0.0, index=RV.columns); nwE[vv.index] = 1.0/len(vv)
            tT = float((nwT-(wT if wT is not None else 0)).abs().sum())
            tE = float((nwE-(wE if wE is not None else 0)).abs().sum())
            wT, wE, since = nwT, nwE, 1
            rTilt.append(float((wT*F.loc[dt].fillna(0)).sum()) - tT*COST/1e4)
            rEW.append(float((wE*F.loc[dt].fillna(0)).sum()) - tE*COST/1e4)
        else:
            since += 1
            rTilt.append(float((wT*F.loc[dt].fillna(0)).sum()))
            rEW.append(float((wE*F.loc[dt].fillna(0)).sum()))
    idx = RV.index
    rT = pd.Series(rTilt, index=idx); rE = pd.Series(rEW, index=idx); a = (rT - rE)
    is_m, oos_m = idx < SPLIT, idx >= SPLIT

    def sharpe(r):
        r = r.dropna(); return round(float(r.mean()/r.std(ddof=1)*ANN), 3) if len(r) > 1 and r.std() else None

    res = {"setting": "逆波動 overlay, RV60(日), hold=5(週頻), 10bps, OOS≥2025-01-01",
           "IS": {"active": active_stats(a[is_m]), "tilt_sharpe": sharpe(rT[is_m]), "EW_sharpe": sharpe(rE[is_m])},
           "OOS": {"active": active_stats(a[oos_m]), "tilt_sharpe": sharpe(rT[oos_m]), "EW_sharpe": sharpe(rE[oos_m])}}
    oa = res["OOS"]["active"]
    res["preregistered_decision"] = ("VALIDATE" if (oa.get("active_t", 0) >= 2 and oa.get("IR", 0) > 0.5
                                      and oa.get("active_maxdd", -1) > -0.30) else "REJECT")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
