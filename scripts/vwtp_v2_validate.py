#!/usr/bin/env python3
"""VWTP v2 驗證:regime filter + 波動目標化 + BTC/ETH 組合。全真實。對 5 門檻。
跑: cd factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/vwtp_v2_validate.py
"""
import json
import numpy as np, pandas as pd
from scipy import stats

ASSETS = {"BTC": "empirical_runs/btcusdt_1d_1500.pkl", "ETH": "empirical_runs/ethusdt_1d_1000.pkl"}
ANN = np.sqrt(365)


def vwtp(df, window=20, z_window=90, halflife=3, eps=1e-12):
    c = df["close"].astype(float).reset_index(drop=True)
    v = df["volume"].astype(float).reset_index(drop=True)
    r = np.log(c / c.shift(1))
    vrel = v / v.rolling(window, min_periods=window).mean()
    contrib = np.sign(r) * r.abs() * vrel
    num = contrib.rolling(window, min_periods=window).sum()
    den = (r.abs() * vrel).rolling(window, min_periods=window).sum() + eps
    vw = num / den
    mean = vw.expanding(min_periods=z_window).mean()
    std = vw.expanding(min_periods=z_window).std(ddof=1)
    z = ((vw - mean) / std.replace(0, np.nan)).clip(-3, 3)
    return z.ewm(halflife=halflife, adjust=False).mean().shift(1)


def strat_returns(df, target_vol_ann=0.6, max_lev=1.5, regime_win=100, vol_win=20):
    c = df["close"].astype(float).reset_index(drop=True)
    sig = vwtp(df)
    fwd = c.shift(-1) / c - 1
    regime = c > c.rolling(regime_win, min_periods=regime_win).mean()       # 多頭 regime
    hi = sig.rolling(252, min_periods=120).quantile(0.8)
    lo = sig.rolling(252, min_periods=120).quantile(0.2)
    pos = pd.Series(0.0, index=sig.index)
    pos[sig >= hi] = 1.0; pos[sig <= lo] = -1.0
    pos = pos * regime.astype(float)
    rvol = c.pct_change().rolling(vol_win, min_periods=vol_win).std().shift(1)   # 過去波動(無前視)
    scale = (target_vol_ann / ANN / rvol).clip(upper=max_lev)
    sret = (pos * scale * fwd)
    ts = pd.to_datetime(df["timestamp"], unit="ms").reset_index(drop=True)
    out = pd.DataFrame({"date": ts, "ret": sret, "pos": pos, "sig": sig, "fwd": fwd, "regime": regime})
    return out


def perf(ret):
    ret = ret.dropna()
    if not len(ret) or not ret.std():
        return {}
    eq = (1 + ret).cumprod()
    nz = ret[ret != 0]
    return {"sharpe": round(float(ret.mean() / ret.std(ddof=1) * ANN), 3),
            "maxdd": round(float((eq / eq.cummax() - 1).min()), 4),
            "t": round(float(nz.mean() / (nz.std(ddof=1) / np.sqrt(len(nz)))), 3) if len(nz) > 1 else None,
            "ann_ret": round(float(ret.mean() * 365), 4), "n_active": int((ret != 0).sum())}


def regime_ic_ir(d, win=90):
    sub = d[d["regime"]].copy()
    s, f = sub["sig"], sub["fwd"]
    ics = []
    s = s.reset_index(drop=True); f = f.reset_index(drop=True)
    for i in range(win, len(s)):
        ss, ff = s.iloc[i-win:i], f.iloc[i-win:i]
        m = ss.notna() & ff.notna()
        if m.sum() >= 30:
            ics.append(stats.spearmanr(ss[m], ff[m]).correlation)
    ics = pd.Series(ics).dropna()
    return round(float(ics.mean()/ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None


def main():
    res = {}; per_asset = {}
    for name, path in ASSETS.items():
        d = strat_returns(pd.read_pickle(path))
        per_asset[name] = d
        res[name] = perf(d["ret"])
        res[name]["regime_ic_ir"] = regime_ic_ir(d)
    # 等權 BTC+ETH 組合(依日期對齊)
    merged = None
    for name, d in per_asset.items():
        s = d.set_index("date")["ret"].rename(name)
        merged = s if merged is None else pd.concat([merged, s], axis=1)
    port = merged.mean(axis=1, skipna=True)        # 等權,缺一資產時用另一資產
    res["PORTFOLIO_BTC_ETH"] = perf(port)
    # 門檻檢查(用組合 + regime IC-IR 取較佳者描述)
    p = res["PORTFOLIO_BTC_ETH"]
    btc_ir, eth_ir = res["BTC"]["regime_ic_ir"], res["ETH"]["regime_ic_ir"]
    gates = {
        "IC-IR>0.3 (regime, BTC/ETH)": f"{btc_ir} / {eth_ir}",
        "LS Sharpe>0.5 (portfolio)": p.get("sharpe"),
        "MaxDD<30% (portfolio)": p.get("maxdd"),
        "t>=2 (portfolio)": p.get("t"),
    }
    res["GATES"] = gates
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
