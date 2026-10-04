#!/usr/bin/env python3
"""FSIM_HollowLeverage 橫截面評估(Empiricist 標準套餐)。
主規格(預註冊):smooth=3, dwin=7, min_coins=40, hold=1, cost=10bps。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/hollow_leverage_eval.py [hold] [cost_bps]
輸出:harness quintile LS(crosssec_eval.evaluate)+ rank-weight 組合 + 年度分解
      + 市場中性檢查 + 尾部剔除 + IS/OOS 對半。全真實。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
import scripts.crosssec_eval as X
from core.signals.FSIM_HollowLeverage import build_signal_matrix

ANN = np.sqrt(365)


def perf(r: pd.Series) -> dict:
    r = r.dropna()
    if not len(r) or not r.std():
        return {}
    eq = (1 + r).cumprod()
    return {"sharpe": round(float(r.mean() / r.std(ddof=1) * ANN), 3),
            "t": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3),
            "ann_ret": round(float(r.mean() * 365), 4),
            "maxdd": round(float((eq / eq.cummax() - 1).min()), 4),
            "n_days": int(len(r))}


def rank_weight_ls(S: pd.DataFrame, F: pd.DataFrame, cost_bps: float) -> tuple[pd.Series, dict]:
    """預註冊組合:w ∝ u(S), dollar-neutral, Σ|w|=2, 日頻 rebalance。"""
    rets, turns = [], []
    w_prev = pd.Series(0.0, index=S.columns)
    idx_out = []
    for dt in S.index:
        x = S.loc[dt]
        m = x.notna() & F.loc[dt].notna()
        if m.sum() < 40:
            continue
        u = x[m].rank() - (m.sum() + 1) / 2.0
        u = u - u.mean()
        w = pd.Series(0.0, index=S.columns)
        w[u.index] = u / u.abs().sum() * 2.0
        turn = float((w - w_prev).abs().sum())
        rets.append(float((w * F.loc[dt].fillna(0)).sum()) - turn * cost_bps / 10000.0)
        turns.append(turn)
        idx_out.append(dt)
        w_prev = w
    r = pd.Series(rets, index=idx_out)
    return r, {"ann_turnover": round(float(np.mean(turns)) * 365, 1)}


def main():
    hold = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    cost = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    uni = pd.read_pickle(X.UNI)
    fund = pd.read_pickle(os.path.join(os.path.dirname(X.UNI), "funding_1d.pkl"))
    S = build_signal_matrix(uni, fund)

    fw = {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms")
        c = df["close"].astype(float)
        fw[co] = pd.Series((c.shift(-1) / c - 1).values, index=idx)
    F = pd.DataFrame(fw).sort_index()
    S = S.reindex(F.index)
    S, F = S.align(F, join="inner")

    out = {"signal": "HollowLeverage(-resid dF|r7,r7lag,f3)", "hold": hold, "cost_bps": cost}
    out["harness_quintile_net"] = X.evaluate(S, F, cost, ANN, hold)
    out["harness_quintile_gross"] = {k: v for k, v in X.evaluate(S, F, 0.0, ANN, hold).items()
                                     if k.startswith("ls_")}

    # 預註冊 rank-weight 組合(僅 hold=1 有意義)
    if hold == 1:
        r_net, tstat = rank_weight_ls(S, F, cost)
        r_gross, _ = rank_weight_ls(S, F, 0.0)
        out["rankw_net"] = {**perf(r_net), **tstat}
        out["rankw_gross"] = perf(r_gross)

        # 年度分解(rank-weight net + 年度 IC)
        ic_by_day = {}
        from scipy import stats as st
        for dt in S.index:
            x, y = S.loc[dt], F.loc[dt]
            m = x.notna() & y.notna()
            if m.sum() >= X.MIN_COINS:
                ic_by_day[dt] = st.spearmanr(x[m], y[m]).correlation
        ic_s = pd.Series(ic_by_day)
        yearly = {}
        for yr, grp in r_net.groupby(r_net.index.year):
            icy = ic_s[ic_s.index.year == yr]
            yearly[str(yr)] = {**perf(grp),
                               "ic_mean": round(float(icy.mean()), 4),
                               "ic_t": round(float(icy.mean() / (icy.std(ddof=1) / np.sqrt(len(icy)))), 2) if len(icy) > 2 else None}
        out["yearly_rankw_net"] = yearly

        # 市場中性檢查:LS 對等權市場
        mkt = F.mean(axis=1).reindex(r_gross.index)
        ok = r_gross.notna() & mkt.notna()
        beta = float(np.cov(r_gross[ok], mkt[ok])[0, 1] / np.var(mkt[ok]))
        out["mkt_neutrality"] = {"corr_vs_ew_mkt": round(float(r_gross[ok].corr(mkt[ok])), 3),
                                 "beta_vs_ew_mkt": round(beta, 3)}

        # 尾部剔除:剔 |r| 最大 5% 日
        thr = r_net.abs().quantile(0.95)
        out["rankw_net_ex_top5pct_days"] = perf(r_net[r_net.abs() < thr])

        # IS/OOS 對半
        half = len(r_net) // 2
        out["rankw_net_first_half"] = perf(r_net.iloc[:half])
        out["rankw_net_second_half"] = perf(r_net.iloc[half:])
        ic1, ic2 = ic_s.iloc[:len(ic_s) // 2], ic_s.iloc[len(ic_s) // 2:]
        out["ic_first_half"] = {"mean": round(float(ic1.mean()), 4),
                                "ir": round(float(ic1.mean() / ic1.std(ddof=1)), 3)}
        out["ic_second_half"] = {"mean": round(float(ic2.mean()), 4),
                                 "ir": round(float(ic2.mean() / ic2.std(ddof=1)), 3)}

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
