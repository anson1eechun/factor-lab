#!/usr/bin/env python3
"""labkit — factor-lab 辯論流程共用統計/記帳工具。

抽自 scripts/asd_20260914.py(SIM-2026-09-14-001 已複驗的口徑),改為參數化。
舊 runner 不 import 本檔,保持其逐位可重現;新流程一律用本檔,不再每輪重寫。

慣例:
  R(k)   = 在第 k 列建倉持到第 k+1 列的報酬(寬表 dates×assets)。
  SIG(d) = 第 d 列的訊號;entry_lag 決定 d 形成的子組合從哪一列開始賺 R。
           訊號本身已 shift(1)(函數契約)→ entry_lag=0;未 shift 的 panel → entry_lag=1。
"""
import hashlib, datetime, json
import numpy as np, pandas as pd
from scipy import stats

NW_LAG = 10


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def sanitize(o):
    if isinstance(o, dict): return {str(k): sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [sanitize(v) for v in o]
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o); return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(o, (np.bool_, bool)): return bool(o)
    if isinstance(o, (pd.Timestamp, datetime.date)): return str(o)[:10]
    return o


def dump(path, obj):
    with open(path, "w") as f:
        json.dump(sanitize(obj), f, ensure_ascii=False, indent=2)


def nw_t(x, L=NW_LAG):
    """Newey-West(Bartlett)t。"""
    x = pd.Series(x).dropna().values.astype(float)
    n = len(x)
    if n < 3: return float("nan")
    mu = float(x.mean()); e = x - mu
    s = float(np.dot(e, e)) / n
    for l in range(1, min(L, n - 1) + 1):
        s += 2.0 * (1.0 - l / (L + 1.0)) * float(np.dot(e[l:], e[:-l])) / n
    if s <= 0: return float("nan")
    return float(mu / np.sqrt(s / n))


def perf(r, ppy=365.0):
    r = pd.Series(r).dropna()
    if len(r) < 2 or not r.std(ddof=1):
        return {"n": int(len(r))}
    eq = (1 + r).cumprod()
    return {"n": int(len(r)),
            "ann_return": float(r.mean() * ppy),
            "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(ppy)),
            "t_iid": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))),
            "nw_t": nw_t(r),
            "max_drawdown": float((eq / eq.cummax() - 1).min())}


def nonoverlap_t(r, h):
    """把逐期報酬切成不重疊 h 期區塊加總後的 iid t。"""
    r = pd.Series(r).dropna()
    b = r.groupby(np.arange(len(r)) // h).sum()
    b = b.iloc[:-1] if len(r) % h else b
    if len(b) < 3 or not b.std(ddof=1): return float("nan")
    return float(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))


# ------------------------------------------------------------------ 橫截面
def rank_xs(raw, ok=None, min_n=30):
    """每列橫截面 rank → 均勻分數 (-0.5, 0.5)。"""
    ok = raw.notna() if ok is None else (ok & raw.notna())
    raw = raw.where(ok)
    raw = raw.where(raw.notna().sum(axis=1) >= min_n)
    r = raw.rank(axis=1, method="average")
    n = raw.notna().sum(axis=1)
    return r.div(n.where(n > 0), axis=0).sub(0.5 / n.where(n > 0), axis=0) - 0.5


def ic_series(Z, FWD, min_n=30):
    idx, val = [], []
    for dt in Z.index:
        x = Z.loc[dt]; y = FWD.loc[dt]
        m = x.notna() & y.notna()
        if m.sum() >= min_n:
            c = stats.spearmanr(x[m], y[m]).correlation
            if np.isfinite(c):
                idx.append(dt); val.append(c)
    return pd.Series(val, index=idx, dtype=float)


def ic_stats(ic):
    n = len(ic)
    if n < 3: return {"ic_n": n}
    mu = float(ic.mean()); sd = float(ic.std(ddof=1))
    return {"rank_ic": mu, "ic_ir": mu / sd, "ic_t_iid": mu / (sd / np.sqrt(n)),
            "ic_nw_t": nw_t(ic), "ic_n": n}


def xs_corr(A, B, min_n=30):
    """每列橫截面 Spearman 相關的時間平均。"""
    m = A.notna() & B.notna()
    a = A.where(m).rank(axis=1); b = B.where(m).rank(axis=1)
    a = a.sub(a.mean(axis=1), axis=0); b = b.sub(b.mean(axis=1), axis=0)
    c = (a * b).sum(axis=1) / np.sqrt((a ** 2).sum(axis=1) * (b ** 2).sum(axis=1))
    return float(c[m.sum(axis=1) >= min_n].mean())


def xs_resid(Z, CTRL, min_n=30):
    """每列橫截面對控制變數(rank)迴歸取殘差(含截距)。"""
    out = pd.DataFrame(np.nan, index=Z.index, columns=Z.columns)
    for dt in Z.index:
        y = Z.loc[dt]
        X = pd.concat([c.loc[dt] for c in CTRL], axis=1, keys=[f"c{j}" for j in range(len(CTRL))])
        m = y.notna() & X.notna().all(axis=1)
        if m.sum() < min_n + len(CTRL) + 1:
            continue
        Xm = np.column_stack([np.ones(int(m.sum()))] + [stats.rankdata(X.loc[m, c]) for c in X.columns])
        yv = stats.rankdata(y[m])
        beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
        out.loc[dt, y[m].index] = yv - Xm @ beta
    return out


def fm_coef(Y, Z, CTRL, min_n=30):
    """Fama-MacBeth:每列橫截面 rank 迴歸 Y ~ 1 + Z + CTRL,回傳 Z 係數的時間序列。

    與 xs_resid 同樣全部取 rank、含截距。這是「候選在控制變數之外是否仍有資訊」的聯合檢定,
    不是「扣掉控制後還剩多少」的保留率,所以沒有 v2.4 §4 那種控制更強且反號時的殘留 >100% artifact。
    """
    idx, vals = [], []
    for dt in Z.index:
        y = Y.loc[dt]
        X = pd.concat([Z.loc[dt]] + [c.loc[dt] for c in CTRL], axis=1,
                      keys=[f"x{j}" for j in range(len(CTRL) + 1)])
        m = y.notna() & X.notna().all(axis=1)
        k = X.shape[1]
        if m.sum() < min_n + k + 1:
            continue
        Xm = np.column_stack([np.ones(int(m.sum()))] + [stats.rankdata(X.loc[m, c]) for c in X.columns])
        beta, *_ = np.linalg.lstsq(Xm, stats.rankdata(y[m]), rcond=None)
        idx.append(dt); vals.append(beta[1])
    return pd.Series(vals, index=idx, dtype=float)


def qweights(row, q=5, min_n=30, scale=1.0, which="ls"):
    """訊號列 → 目標權重(毛曝險 2*scale)。which='ls' 或 quintile 序號 0..q-1(long-only)。"""
    x = row.dropna()
    if len(x) < min_n:
        return None
    lab = pd.qcut(x.rank(method="average"), q, labels=False, duplicates="drop")
    if lab.max() != q - 1:
        return None
    w = pd.Series(0.0, index=row.index)
    if which == "ls":
        top = x.index[lab == q - 1]; bot = x.index[lab == 0]
        w[top] = scale / len(top); w[bot] = -scale / len(bot)
    else:
        sel = x.index[lab == which]
        w[sel] = scale / len(sel)
    return w


def backtest_xs(SIG, R, F=None, hold=1, cost_bps=10.0, drift=True, which="ls",
                entry_lag=0, q=5, min_n=30):
    """重疊 Jegadeesh-Titman。每個子組合毛曝險 2/hold;持有期內權重隨報酬漂移(v2.4 §7)。

    F:每列資金費率(多方付正);None 表示無現金流腿(須在預註冊申報)。
    回傳 DataFrame(index=列日期)欄位 gross/cost/fund/net/turn/n_pos/n_missing_R。
    """
    dates = list(SIG.index)
    subs, rows = [], []
    prevW = pd.Series(0.0, index=SIG.columns)
    for k, dt in enumerate(dates):
        subs = [(d, w) for (d, w) in subs if d + entry_lag + hold - 1 >= k]
        d_new = k - entry_lag
        if d_new >= 0:
            w = qweights(SIG.iloc[d_new], q=q, min_n=min_n, scale=1.0 / hold, which=which)
            if w is not None:
                subs.append((d_new, w))
        if not subs:
            turn = float(prevW.abs().sum())
            if turn > 0:
                c = turn * cost_bps / 1e4
                rows.append((dt, 0.0, c, 0.0, -c, turn, 0, 0))
            prevW = pd.Series(0.0, index=SIG.columns)
            continue
        W = pd.concat([w for _, w in subs], axis=1).sum(axis=1)
        rv = R.loc[dt]
        n_missing = int(rv.isna()[W != 0].sum())
        rv = rv.fillna(0.0)
        fund = -float((W * F.loc[dt].fillna(0.0)).sum()) if F is not None else 0.0
        turn = float((W - prevW).abs().sum())
        gross = float((W * rv).sum())
        cost = turn * cost_bps / 1e4
        rows.append((dt, gross, cost, fund, gross - cost + fund, turn, int((W != 0).sum()), n_missing))
        if drift:
            subs = [(d, w * (1.0 + rv)) for (d, w) in subs]
        prevW = pd.concat([w for _, w in subs], axis=1).sum(axis=1)
    return pd.DataFrame(rows, columns=["dt", "gross", "cost", "fund", "net", "turn",
                                       "n_pos", "n_missing_R"]).set_index("dt")


# ------------------------------------------------------------------ 家族/多重比較
def bonferroni_t(n, alpha=0.05):
    """雙尾 Bonferroni 臨界 |t|(常態近似)。"""
    return float(stats.norm.isf(alpha / (2 * max(n, 1))))


def dsr_threshold(n, t_years):
    """純噪音下 N 次搜尋的期望最大 Sharpe ≈ SE×√(2 ln N),SE≈1/√T年。"""
    if n <= 1: return 0.0
    return float(np.sqrt(2 * np.log(n)) / np.sqrt(t_years))
