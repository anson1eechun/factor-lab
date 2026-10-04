#!/usr/bin/env python3
"""
VWTP REWORK 分析(SIM-2026-06-07-002 的 rework)。全部真實計算。
照 Arbiter 路線:expanding zscore / 非重疊 IC+t / 年度 regime / ETH 多資產 / 參數掃描。
跑法: cd factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/debate_rework_vwtp.py
"""
import json
import numpy as np, pandas as pd
from scipy import stats

BTC = "empirical_runs/btcusdt_1d_1500.pkl"
ETH = "empirical_runs/ethusdt_1d_1000.pkl"


def vwtp_signal(df, window=20, z_window=90, halflife=3, eps=1e-12, zmode="rolling"):
    c = df["close"].astype(float).reset_index(drop=True)
    v = df["volume"].astype(float).reset_index(drop=True)
    r = np.log(c / c.shift(1))
    vrel = v / v.rolling(window, min_periods=window).mean()
    contrib = np.sign(r) * r.abs() * vrel
    num = contrib.rolling(window, min_periods=window).sum()
    den = (r.abs() * vrel).rolling(window, min_periods=window).sum() + eps
    vwtp = num / den
    if zmode == "expanding":
        mean = vwtp.expanding(min_periods=z_window).mean()
        std = vwtp.expanding(min_periods=z_window).std(ddof=1)
    else:
        mean = vwtp.rolling(z_window, min_periods=z_window).mean()
        std = vwtp.rolling(z_window, min_periods=z_window).std(ddof=1)
    z = ((vwtp - mean) / std.replace(0, np.nan)).clip(-3, 3)
    sig = z.ewm(halflife=halflife, adjust=False).mean()
    return sig.shift(1)


def ic_overlap(sig, c, h):
    fwd = c.shift(-h) / c - 1
    m = sig.notna() & fwd.notna()
    return round(float(stats.spearmanr(sig[m], fwd[m]).correlation), 4)


def ic_nonoverlap(sig, c, h):
    fwd = c.shift(-h) / c - 1
    m = sig.notna() & fwd.notna()
    idx = np.where(m.values)[0][::h]          # 每 h 取一,前瞻不重疊
    s, f = sig.values[idx], fwd.values[idx]
    if len(s) < 10:
        return None, None, len(s)
    ic = stats.spearmanr(s, f).correlation
    n = len(s)
    t = ic * np.sqrt((n - 2) / (1 - ic**2)) if abs(ic) < 1 else None
    return round(float(ic), 4), (round(float(t), 2) if t is not None else None), n


def ic_ir(sig, c, win=90):
    fwd = c.shift(-1) / c - 1
    ics = []
    for i in range(win, len(sig)):
        s, f = sig.iloc[i-win:i], fwd.iloc[i-win:i]
        mm = s.notna() & f.notna()
        if mm.sum() >= 30:
            ics.append(stats.spearmanr(s[mm], f[mm]).correlation)
    ics = pd.Series(ics).dropna()
    return (round(float(ics.mean()/ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None)


def ls(sig, c):
    fwd = c.shift(-1) / c - 1
    hi = sig.rolling(252, min_periods=120).quantile(0.8)
    lo = sig.rolling(252, min_periods=120).quantile(0.2)
    pos = pd.Series(0.0, index=sig.index)
    pos[sig >= hi] = 1.0; pos[sig <= lo] = -1.0
    strat = (pos * fwd).dropna()
    if not len(strat) or not strat.std():
        return {}
    eq = (1+strat).cumprod()
    nz = strat[pos.reindex(strat.index) != 0]
    return {"sharpe": round(float(strat.mean()/strat.std(ddof=1)*np.sqrt(365)), 3),
            "maxdd": round(float((eq/eq.cummax()-1).min()), 4),
            "t": round(float(nz.mean()/(nz.std(ddof=1)/np.sqrt(len(nz)))), 3) if len(nz) > 1 else None}


def full(df, **kw):
    c = df["close"].astype(float).reset_index(drop=True)
    sig = vwtp_signal(df, **kw)
    out = {"zmode": kw.get("zmode", "rolling")}
    out["ic_overlap"] = {f"{h}d": ic_overlap(sig, c, h) for h in (1, 5, 10)}
    out["ic_nonoverlap"] = {}
    for h in (1, 5, 10):
        ic, t, n = ic_nonoverlap(sig, c, h)
        out["ic_nonoverlap"][f"{h}d"] = {"ic": ic, "t": t, "n": n}
    out["ic_ir_roll90"] = ic_ir(sig, c)
    out["ls"] = ls(sig, c)
    return out


def main():
    btc = pd.read_pickle(BTC); eth = pd.read_pickle(ETH)
    res = {}
    # 1+2: BTC rolling vs expanding zscore,含非重疊 IC/t
    res["BTC_rolling"] = full(btc, zmode="rolling")
    res["BTC_expanding"] = full(btc, zmode="expanding")
    # 4: ETH 多資產(expanding)
    res["ETH_expanding"] = full(eth, zmode="expanding")
    # 3: 年度 regime 分解(BTC, h=5, expanding signal)
    c = btc["close"].astype(float).reset_index(drop=True)
    sig = vwtp_signal(btc, zmode="expanding")
    yr = pd.to_datetime(btc["timestamp"], unit="ms").dt.year.reset_index(drop=True)
    fwd5 = c.shift(-5)/c - 1
    by_year = {}
    for y in sorted(yr.unique()):
        m = (yr == y) & sig.notna() & fwd5.notna()
        if m.sum() >= 30:
            by_year[int(y)] = {"ic5d": round(float(stats.spearmanr(sig[m], fwd5[m]).correlation), 4), "n": int(m.sum())}
    res["BTC_ic5d_by_year"] = by_year
    # 5: 參數敏感度掃描(BTC, expanding):IC-IR, Sharpe, 非重疊5d IC/t
    sweep = []
    for w in (10, 20, 40):
        for zw in (60, 90, 120):
            for hl in (3, 5):
                s = vwtp_signal(btc, window=w, z_window=zw, halflife=hl, zmode="expanding")
                ic5, t5, n5 = ic_nonoverlap(s, c, 5)
                sweep.append({"w": w, "zw": zw, "hl": hl, "ic_ir": ic_ir(s, c),
                              "sharpe": ls(s, c).get("sharpe"), "ic5d_noov": ic5, "t5d_noov": t5})
    res["param_sweep"] = sweep
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
