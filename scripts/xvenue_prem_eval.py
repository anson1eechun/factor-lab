#!/usr/bin/env python3
"""SIM-2026-07-03-001 FSIM_XVENUE_PREM_GAP 預註冊評估 harness(全真實、確定性)。

因子:prem = ln(close_CB/close_BN)(同日 UTC 日 K);gap = ma20(prem) − ma120(prem);
訊號 = gap 當日橫截面 z 分數。週頻(每 7 日)調倉 Q5−Q1 等權,報酬用 Binance close。
變體 N=2:V1=gap z(裁決用);V2=z(ma20(prem))(純機制診斷)。

預註冊關卡(2026-07-03,跑前定死):
G1 週頻 rank IC_t≥2 且 mean IC>0
G2 淨LS(10bps/邊) t≥2 且打平成本≥20bps
G3 剔淨LS最佳5%週後均值仍>0
G4 IS(→2024-10-31)/OOS(2024-11-01→) IC 同向皆>0
G5 訊號再延遲1日: IC 同向且 IC_t≥1
G6 五分位嚴格單調遞增
G7 重跑逐位一致(sha256)

缺值政策(跑前定死):prem 以「可得觀測」滾動(20/120 個觀測,非日曆),
Coinbase 缺日不補值;成員資格=當日雙所皆有 K 線且 CB 上市≥60 日。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy \
    python scripts/xvenue_prem_eval.py [cost_bps=10] [lag_extra=0]
"""
import sys, os, json, pickle, hashlib, math
import numpy as np, pandas as pd
from scipy import stats

ER = "/home/anson/factor-lab/empirical_runs/"
MIN_COINS = 8            # 房規(同 crosssec_eval.py)
HOLD = 7                 # 每 7 日調倉=IC horizon(非重疊)
LIST_AGE = 60            # CB 上市滿 60 日才入池
W_S, W_L = 20, 120       # gap 視窗
SPLIT = "2024-11-01"     # IS/OOS 預註冊切點
ANN_W = math.sqrt(52)


def load_panels():
    bn = pickle.load(open(ER + "universe_1d.pkl", "rb"))
    cb = pickle.load(open(ER + "coinbase_1d.pkl", "rb"))
    coins = sorted(set(bn) & set(cb))
    idx = sorted(set().union(*[bn[c]["timestamp"].tolist() for c in coins]))
    close_bn = pd.DataFrame(index=idx, columns=coins, dtype=float)
    prem = pd.DataFrame(index=idx, columns=coins, dtype=float)
    for c in coins:
        b = bn[c].set_index("timestamp")["close"]
        k = cb[c].set_index("timestamp")["close"]
        close_bn[c] = b.reindex(idx)
        both = b.index.intersection(k.index)
        # CB 上市滿 60 日
        first_cb = k.index.min()
        ok = both[(both - first_cb) >= LIST_AGE * 86400000]
        prem.loc[ok, c] = np.log(k.loc[ok] / b.loc[ok]).values
    return close_bn, prem, coins


def rolling_obs(series, w):
    """以可得觀測滾動平均(確定性;缺日不補)。"""
    s = series.dropna()
    return s.rolling(w, min_periods=w).mean().reindex(series.index)


def xs_z(panel):
    mu = panel.mean(axis=1)
    sd = panel.std(axis=1, ddof=1)
    z = panel.sub(mu, axis=0).div(sd, axis=0)
    z[panel.notna().sum(axis=1) < MIN_COINS] = np.nan
    return z


def weekly_eval(sig, close_bn, cost_bps, tag):
    # T 訊號 → T+1 收盤進場,持有 7 日(close_{t+1}→close_{t+8}),防同收盤微結構陷阱
    fwd = close_bn.shift(-(HOLD + 1)) / close_bn.shift(-1) - 1.0
    valid_days = [t for t in sig.index if sig.loc[t].notna().sum() >= MIN_COINS]
    if not valid_days:
        return {"tag": tag, "error": "no valid days"}
    grid = []
    t0 = valid_days[0]
    pos = {t: i for i, t in enumerate(sig.index)}
    i0 = pos[t0]
    for t in valid_days:
        if (pos[t] - i0) % HOLD == 0 and pos[t] + HOLD + 1 < len(sig.index):
            grid.append(t)
    ics, ls_g, turns, qrows, dates = [], [], [], [], []
    w_prev = pd.Series(0.0, index=sig.columns)
    for t in grid:
        x = sig.loc[t]; y = fwd.loc[t]
        m = x.notna() & y.notna()
        if m.sum() < MIN_COINS:
            continue
        ics.append(float(stats.spearmanr(x[m], y[m]).correlation))
        r = x[m].rank(method="average")
        q = pd.qcut(r, 5, labels=False, duplicates="drop")
        w = pd.Series(0.0, index=sig.columns)
        top = r.index[q == q.max()]; bot = r.index[q == 0]
        w[top] = 1.0 / len(top); w[bot] = -1.0 / len(bot)
        ls_g.append(float((w[m] * y[m]).sum()))
        turns.append(float((w - w_prev).abs().sum()))
        w_prev = w
        qrows.append([float(y[m][q == qi].mean()) for qi in range(int(q.max()) + 1)])
        dates.append(t)
    ic = pd.Series(ics, index=dates); g = pd.Series(ls_g, index=dates)
    tu = pd.Series(turns, index=dates)
    net = g - tu * cost_bps / 1e4
    out = {"tag": tag, "n_weeks": len(ic), "cost_bps": cost_bps}
    out["ic_mean"] = round(float(ic.mean()), 5)
    out["ic_ir"] = round(float(ic.mean() / ic.std(ddof=1)), 4)
    out["ic_t"] = round(float(ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic)))), 3)
    for nm, r in [("gross", g), ("net", net)]:
        eq = (1 + r).cumprod()
        out[f"ls_{nm}_sharpe"] = round(float(r.mean() / r.std(ddof=1) * ANN_W), 3)
        out[f"ls_{nm}_t"] = round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3)
        out[f"ls_{nm}_mean_wk"] = round(float(r.mean()), 6)
        out[f"ls_{nm}_maxdd"] = round(float((eq / eq.cummax() - 1).min()), 4)
    out["turnover_mean"] = round(float(tu.mean()), 4)
    out["breakeven_bps"] = round(float(g.mean() / tu.mean() * 1e4), 2) if tu.mean() else None
    k = max(1, int(math.ceil(0.05 * len(net))))
    out["ex_top5_net_mean_wk"] = round(float(net.drop(net.nlargest(k).index).mean()), 6)
    out["ex_top5_gross_mean_wk"] = round(float(g.drop(g.nlargest(k).index).mean()), 6)
    split_ms = int(pd.Timestamp(SPLIT).value // 10**6)
    is_m, oos_m = ic.index < split_ms, ic.index >= split_ms
    out["ic_is"] = round(float(ic[is_m].mean()), 5) if is_m.any() else None
    out["ic_oos"] = round(float(ic[oos_m].mean()), 5) if oos_m.any() else None
    out["net_is_mean_wk"] = round(float(net[is_m].mean()), 6) if is_m.any() else None
    out["net_oos_mean_wk"] = round(float(net[oos_m].mean()), 6) if oos_m.any() else None
    # 年度 regime
    yr = pd.Series([pd.Timestamp(t, unit="ms").year for t in ic.index], index=ic.index)
    out["by_year"] = {int(y): {"ic": round(float(ic[yr == y].mean()), 5),
                               "net_wk": round(float(net[yr == y].mean()), 6),
                               "n": int((yr == y).sum())} for y in sorted(yr.unique())}
    qdf = pd.DataFrame([r for r in qrows if len(r) == 5])
    qm = [round(float(qdf[i].mean()), 6) for i in range(5)]
    out["quintile_fwd_mean"] = qm
    out["mono_strict"] = bool(all(qm[i] < qm[i + 1] for i in range(4)))
    out["mono_spearman"] = round(float(stats.spearmanr(range(5), qm).correlation), 3)
    out["first_week"] = pd.Timestamp(dates[0], unit="ms").date().isoformat()
    out["last_week"] = pd.Timestamp(dates[-1], unit="ms").date().isoformat()
    return out


def main():
    cost = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    lag_extra = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    close_bn, prem, coins = load_panels()
    ma_s = prem.apply(lambda s: rolling_obs(s, W_S))
    ma_l = prem.apply(lambda s: rolling_obs(s, W_L))
    gap = ma_s - ma_l
    if lag_extra:
        gap = gap.shift(lag_extra); ma_s = ma_s.shift(lag_extra)
    res = {"session": "SIM-2026-07-03-001", "factor": "FSIM_XVENUE_PREM_GAP",
           "n_coins_overlap": len(coins), "lag_extra": lag_extra,
           "coins": coins,
           "prem_std_median": round(float(prem.std().median()), 5)}
    res["V1_gap_z"] = weekly_eval(xs_z(gap), close_bn, cost, "V1 gap z")
    res["V2_level_z_diagnostic"] = weekly_eval(xs_z(ma_s), close_bn, cost, "V2 level z(僅診斷)")
    blob = json.dumps(res, ensure_ascii=False, sort_keys=True)
    res["output_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    print(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True))
    fn = ER + f"SIM-2026-07-03-001_xvenue_metrics{'_lag'+str(lag_extra) if lag_extra else ''}.json"
    with open(fn, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
