#!/usr/bin/env python3
"""
debate_sim_eval.py — 確定性單資產因子回測 harness(供辯論模擬的 Empiricist 用)
==============================================================================
對 BTCUSDT 1d OHLCV(empirical_runs/btcusdt_1d_1500.pkl)評估一個 signal 函數,
輸出真實指標 JSON。無前視:signal_t 預測 t→t+1 報酬;quintile 門檻用滾動窗。

用法:
  uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/debate_sim_eval.py <module_path> [func_name]
  例: ... scripts/debate_sim_eval.py core.signals.F10_Wick_Absorption_Asymmetry factor
"""
import sys, os, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from scipy import stats

DATA = "empirical_runs/btcusdt_1d_1500.pkl"


def evaluate(sig: pd.Series, df: pd.DataFrame) -> dict:
    sig = pd.Series(np.asarray(sig, dtype="float64")).reset_index(drop=True)
    close = df["close"].reset_index(drop=True).astype("float64")
    out = {}
    # 多 horizon full-sample rank-IC
    for h in (1, 3, 5, 10):
        fwd = close.shift(-h) / close - 1.0
        m = sig.notna() & fwd.notna()
        out[f"rank_ic_{h}d"] = round(float(stats.spearmanr(sig[m], fwd[m]).correlation), 4)
    # IC-IR:90 日滾動 rank-IC(h=1)的 mean/std
    fwd1 = close.shift(-1) / close - 1.0
    ics = []
    win = 90
    for i in range(win, len(sig)):
        s, f = sig.iloc[i - win:i], fwd1.iloc[i - win:i]
        mm = s.notna() & f.notna()
        if mm.sum() >= 30:
            ics.append(stats.spearmanr(s[mm], f[mm]).correlation)
    ics = pd.Series(ics).dropna()
    out["ic_mean_roll90"] = round(float(ics.mean()), 4) if len(ics) else None
    out["ic_ir"] = round(float(ics.mean() / ics.std(ddof=1)), 4) if len(ics) > 1 and ics.std() else None
    # 時序 quintile 多空(滾動 252 日門檻,無前視)
    q_hi = sig.rolling(252, min_periods=120).quantile(0.8)
    q_lo = sig.rolling(252, min_periods=120).quantile(0.2)
    pos = pd.Series(0.0, index=sig.index)
    pos[sig >= q_hi] = 1.0
    pos[sig <= q_lo] = -1.0
    strat = (pos * fwd1).dropna()
    n = int((pos != 0).sum())
    if len(strat) and strat.std():
        ann = np.sqrt(365)
        out["ls_sharpe"] = round(float(strat.mean() / strat.std(ddof=1) * ann), 3)
        eq = (1 + strat).cumprod()
        out["ls_max_drawdown"] = round(float((eq / eq.cummax() - 1).min()), 4)
        nz = strat[pos.reindex(strat.index) != 0]
        out["t_stat"] = round(float(nz.mean() / (nz.std(ddof=1) / np.sqrt(len(nz)))), 3) if len(nz) > 1 else None
        out["ls_ann_return"] = round(float(strat.mean() * 365), 4)
    out["n_active_days"] = n
    out["n_obs"] = int(sig.notna().sum())
    # 五分位單調性:quintile 平均次日報酬 對 quintile 序 的 Spearman(≥0.7 才算單調)
    try:
        mm = sig.notna() & fwd1.notna()
        q = pd.qcut(sig[mm], 5, labels=False, duplicates="drop")
        qmean = fwd1[mm].groupby(q).mean()
        out["mono"] = round(float(stats.spearmanr(range(len(qmean)), qmean.values).correlation), 3) if len(qmean) >= 3 else None
    except Exception:
        out["mono"] = None
    return out


def main():
    mod_path = sys.argv[1]
    func = sys.argv[2] if len(sys.argv) > 2 else "factor"
    df = pd.read_pickle(DATA)
    mod = importlib.import_module(mod_path)
    fn = getattr(mod, func)
    sig = fn(df)
    res = {"module": mod_path, "func": func, "data": DATA, "rows": len(df), **evaluate(sig, df)}
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
