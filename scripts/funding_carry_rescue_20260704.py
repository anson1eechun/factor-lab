#!/usr/bin/env python3
"""SIM-2026-07-04-002 Funding-Carry backward-OOS 救援分析(唯讀;不動任何既有資料/程式)。
S、F 照 scripts/funding_carry_eval.py 原碼建構(smooth=7、min_periods=max(2,7//2)=3、shift(1)、
funding_1d.pkl 已是「當日 funding 之和」)。confirmatory 窗一律經 scripts.crosssec_eval.evaluate。
腿記帳:逐字複刻 evaluate() 的組合迴圈,另記每日多空腿 gross;斷言腿和=LS gross(3 位小數)否則 ABORT。
輸出單一 JSON → empirical_runs/SIM-2026-07-04-002_results.json
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy python scripts/funding_carry_rescue_20260704.py"""
import sys, os, json, datetime
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.crosssec_eval as X

ER = "/home/anson/factor-lab/empirical_runs/"
SMOOTH, HOLD = 7, 10
OUT = ER + "SIM-2026-07-04-002_results.json"

# ---------- S、F 建構(照 funding_carry_eval.py 原碼) ----------
uni = pd.read_pickle(X.UNI)
fund = pd.read_pickle(os.path.join(os.path.dirname(X.UNI), "funding_1d.pkl"))
fw = {}
for co, df in uni.items():
    idx = pd.to_datetime(df["timestamp"], unit="ms"); c = df["close"].astype(float)
    fw[co] = pd.Series((c.shift(-1)/c - 1).values, index=idx)
F = pd.DataFrame(fw).sort_index()
sg = {}
for co, d in fund.items():
    if co not in uni: continue
    idx = pd.to_datetime(d["timestamp"], unit="ms"); s = pd.Series(d["funding"].values, index=idx)
    sg[co] = (-s.rolling(SMOOTH, min_periods=max(2, SMOOTH//2)).mean()).shift(1)
S = pd.DataFrame(sg).reindex(F.index)
S, F = S.align(F, join="inner")

# ---------- T40 / 首個≥8幣日 ----------
valid = (S.notna() & F.notna()).sum(axis=1)
T40 = valid.index[valid >= 40][0]
T8 = valid.index[valid >= X.MIN_COINS][0]
print(f"T40 = {T40.date()}  (首個 >=40 幣 S、F 皆非 NaN 的 UTC 日)")
print(f"T8  = {T8.date()}  (首個 >={X.MIN_COINS} 幣日,exploratory 窗起點)")


def run_window(t0, t1, cost):
    Sw = S.loc[t0:t1]; Fw = F.loc[t0:t1]
    return X.evaluate(Sw, Fw, cost, np.sqrt(365), 10)


def daily_series(t0, t1, cost_bps, hold=HOLD):
    """逐字複刻 crosssec_eval.evaluate() 的組合迴圈(rets/w/since/qcut/turnover 邏輯不變),
    額外逐日記錄:gross、net、long 腿、short 腿(gross)、turnover、有效幣數、IC、訊號離散度。"""
    Sw = S.loc[t0:t1]; Fw = F.loc[t0:t1]
    MIN_COINS = X.MIN_COINS
    rows = []
    rets, w, since = [], None, 10**9
    for dt in Sw.index:
        x = Sw.loc[dt]; y = Fw.loc[dt]; m = x.notna() & y.notna()
        ic = float(stats.spearmanr(x[m], y[m]).correlation) if m.sum() >= MIN_COINS else np.nan
        disp = float(x[m].std(ddof=1)) if m.sum() >= MIN_COINS else np.nan
        if m.sum() < MIN_COINS:
            if w is not None:
                fv = Fw.loc[dt].fillna(0)
                g = float((w * fv).sum())
                lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
                rets.append(g)
                rows.append((dt, g, g, lg, sh, 0.0, int(m.sum()), ic, disp))
            continue
        xr = x[m].rank(); coins = xr.index
        q = pd.qcut(xr, 5, labels=False, duplicates="drop")
        if since >= hold:
            neww = pd.Series(0.0, index=Sw.columns)
            top = coins[q == q.max()]; bot = coins[q == 0]
            if len(top): neww[top] = 1.0 / len(top)
            if len(bot): neww[bot] = -1.0 / len(bot)
            turn = float((neww - (w if w is not None else 0)).abs().sum())
            w = neww; since = 1
            fv = Fw.loc[dt].fillna(0)
            g = float((w * fv).sum())
            lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
            rets.append(g - turn * cost_bps / 10000.0)
            rows.append((dt, g, g - turn * cost_bps / 10000.0, lg, sh, turn, int(m.sum()), ic, disp))
        else:
            fv = Fw.loc[dt].fillna(0)
            g = float((w * fv).sum())
            lg = float((w.clip(lower=0) * fv).sum()); sh = float((w.clip(upper=0) * fv).sum())
            rets.append(g); since += 1
            rows.append((dt, g, g, lg, sh, 0.0, int(m.sum()), ic, disp))
    df = pd.DataFrame(rows, columns=["dt", "gross", "net", "long", "short", "turn", "n_valid", "ic", "disp"]).set_index("dt")
    return df


def sharpe(r):
    r = pd.Series(r).dropna()
    if len(r) < 2 or not r.std(ddof=1):
        return None
    return float(r.mean() / r.std(ddof=1) * np.sqrt(365))


def sanitize(o):
    if isinstance(o, dict): return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [sanitize(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(o, (pd.Timestamp, datetime.date)): return str(o)[:10]
    return o


# ---------- 視窗定義(confirmatory 僅此) ----------
WINDOWS = {
    "W_back":      (T40, "2022-12-31", [0.0, 10.0]),
    "W_in":        ("2023-01-01", "2026-06-30", [0.0, 10.0]),
    "W_comb":      (T40, "2026-06-30", [0.0, 5.0, 10.0, 20.0]),
    "exploratory": (T8, "2026-06-30", [10.0]),
}

results = {"sim_id": "SIM-2026-07-04-002", "generated_at": str(pd.Timestamp.utcnow())[:19],
           "signal": f"-funding_{SMOOTH}dmean", "hold": HOLD, "min_coins": X.MIN_COINS,
           "n_coins": int(S.shape[1]), "index_days": int(S.shape[0]),
           "index_range": [str(S.index[0].date()), str(S.index[-1].date())],
           "T40": str(T40.date()), "T8_first_ge8": str(T8.date()),
           "windows": {k: [str(pd.Timestamp(v[0]).date()), str(pd.Timestamp(v[1]).date()), v[2]] for k, v in WINDOWS.items()}}

# ---------- confirmatory 跑批(經 X.evaluate) ----------
conf = {}
for name, (t0, t1, costs) in WINDOWS.items():
    conf[name] = {}
    for c in costs:
        conf[name][f"cost_{int(c)}"] = run_window(t0, t1, c)
results["confirmatory"] = conf

# ---------- 腿記帳 + 斷言(對每個視窗) ----------
leg_dec, checks = {}, {"per_day_leg_gap_max": 0.0, "sharpe_crosscheck": []}
daily_cache = {}
ABORT = False
for name, (t0, t1, costs) in WINDOWS.items():
    ds = daily_series(t0, t1, 10.0)   # 權重路徑與 cost 無關;net_c 可由 gross-turn*c/1e4 重建
    daily_cache[name] = ds
    gap = float((ds["long"] + ds["short"] - ds["gross"]).abs().max()) if len(ds) else 0.0
    checks["per_day_leg_gap_max"] = max(checks["per_day_leg_gap_max"], gap)
    if len(ds) and (np.round(ds["long"] + ds["short"], 3) != np.round(ds["gross"], 3)).any():
        print(f"ABORT: {name} 腿和 != LS gross(3 位小數)  max_gap={gap}")
        ABORT = True
    # 複刻迴圈 vs X.evaluate 交叉核對(每個 cost 的 net Sharpe 到 3 位小數)
    for c in costs:
        net_c = ds["gross"] - ds["turn"] * c / 10000.0
        s_mine = sharpe(net_c)
        s_eval = conf[name][f"cost_{int(c)}"].get("ls_sharpe")
        checks["sharpe_crosscheck"].append({"window": name, "cost": c,
                                            "replica": round(s_mine, 3) if s_mine is not None else None,
                                            "evaluate": s_eval})
        if s_mine is None or s_eval is None or abs(round(s_mine, 3) - s_eval) > 0.0010001:
            print(f"ABORT: {name} cost={c} 複刻迴圈 Sharpe {s_mine} != evaluate {s_eval}")
            ABORT = True
    leg_dec[name] = {"n_days": int(len(ds)),
                     "long":  {"mean_daily": float(ds["long"].mean()), "ann_return": float(ds["long"].mean() * 365), "sharpe": sharpe(ds["long"])},
                     "short": {"mean_daily": float(ds["short"].mean()), "ann_return": float(ds["short"].mean() * 365), "sharpe": sharpe(ds["short"])},
                     "gross": {"mean_daily": float(ds["gross"].mean()), "ann_return": float(ds["gross"].mean() * 365), "sharpe": sharpe(ds["gross"])},
                     "avg_turnover_daily": float(ds["turn"].mean())}
if ABORT:
    results["ABORT"] = "leg accounting / replica crosscheck failed"
    with open(OUT, "w") as f: json.dump(sanitize(results), f, ensure_ascii=False, indent=2)
    sys.exit(1)
results["leg_check"] = checks
results["leg_decomposition"] = leg_dec

# ---------- W-back 尾部剝離(剔 gross LS 最佳 5% / 1% 日) ----------
g = daily_cache["W_back"]["gross"]
n = len(g)
strip = {"n_days": n, "gross_sharpe_full": sharpe(g), "gross_ann_return_full": float(g.mean() * 365)}
for pct in (0.01, 0.05):
    k = max(1, int(np.floor(n * pct)))
    kept = g.drop(g.nlargest(k).index)
    strip[f"strip_top{int(pct*100)}pct"] = {"n_stripped": k, "min_stripped_day_ret": float(g.nlargest(k).min()),
                                            "gross_sharpe_after": sharpe(kept), "gross_ann_return_after": float(kept.mean() * 365)}
results["wback_tail_strip"] = strip

# ---------- 逐曆年表(日序列來自 exploratory 全窗) ----------
ds_full = daily_cache["exploratory"]
yearly = []
for yr, dsy in ds_full.groupby(ds_full.index.year):
    yearly.append({"year": int(yr), "n_days": int(len(dsy)),
                   "gross_sharpe": sharpe(dsy["gross"]), "net10_sharpe": sharpe(dsy["net"]),
                   "ic_mean": float(dsy["ic"].mean()) if dsy["ic"].notna().any() else None,
                   "ic_days": int(dsy["ic"].notna().sum()),
                   "n_valid_median": float(dsy["n_valid"].median()),
                   "disp_median": float(dsy["disp"].median()) if dsy["disp"].notna().any() else None})
results["yearly"] = yearly

# ---------- 逐年 gross Sharpe 對訊號離散度 sign-check ----------
ys = [r for r in yearly if r["gross_sharpe"] is not None and r["disp_median"] is not None]
if len(ys) >= 3:
    rho = stats.spearmanr([r["gross_sharpe"] for r in ys], [r["disp_median"] for r in ys])
    agree = sum(1 for r in ys if (r["gross_sharpe"] > 0) == (r["disp_median"] > np.median([q["disp_median"] for q in ys])))
    results["sharpe_vs_dispersion_signcheck"] = {
        "spearman_rho": float(rho.correlation), "pvalue": float(rho.pvalue), "n_years": len(ys),
        "n_years_sign_agree(sharpe>0 vs disp>median)": int(agree),
        "pairs": [{"year": r["year"], "gross_sharpe": round(r["gross_sharpe"], 3), "disp_median": r["disp_median"]} for r in ys]}

with open(OUT, "w") as f:
    json.dump(sanitize(results), f, ensure_ascii=False, indent=2)
print("saved →", OUT)

# ---------- 摘要列印 ----------
for name in WINDOWS:
    for ck, v in conf[name].items():
        print(f"{name:12s} {ck:8s} ls_sharpe={v.get('ls_sharpe')} ic_t={v.get('ic_t')} ic_ir={v.get('ic_ir')} ic_n={v.get('ic_n_days')} maxDD={v.get('ls_max_drawdown')}")
print("leg gap max:", checks["per_day_leg_gap_max"])
print(json.dumps(sanitize({"tail_strip": strip, "yearly": yearly,
                           "signcheck": results.get("sharpe_vs_dispersion_signcheck")}), ensure_ascii=False, indent=1))
