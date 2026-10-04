#!/usr/bin/env python3
"""EQ-SIM-2026-07-04-008 EQ_TTM_EP 預註冊評估 harness(全真實、確定性)。

假設(EQ-006 §4 殘留路徑,使用者指定):乾淨 TTM E/P 是否承載「盈餘新近性」訊號。
變體 N=3(跑前宣告,交集樣本=同月同檔 TTM 與 ANN 皆有值):
  V1 裁決 = zn(TTM_EP);V2 控制 = zn(ANN_EP)(EQ-006 v2 年度慣例);V3 診斷 = V1−V2(新近性增量)。
歸因判讀(跑前定死;覆蓋充足=交集月均≥150 檔且有效月≥100):
  (a) V3 IC_t≥+2.4 → 新近性真訊號;(b) |V3 IC_t|<2.4 → 無增量,v1 純 artifact,殘留路徑關閉;
  (c) 覆蓋不足或 V3 IC_t≤−2.4 → 不可判/另立假設。
V1 七關(全過才 validated):①IC_t≥2.4 正向(Bonferroni N=3) ②季頻淨LS(25bps)>0 且多頭超額>0
  ③剔最高5%月 LS 仍>0 ④IS/OOS 兩半(LS 中位切)淨LS 皆>0(IC 兩半另報) ⑤十分位 Spearman>0
  ⑥延遲 filed≤T−30:IC 同向且 IC_t≥2 ⑦可重現(連跑兩次 + 輸入亂序,V1 IC 序列逐位相同)。
公式一次定死:TTM_NI=連續 4 季 val 和(end_q−end_{q−3}∈[180,300] 天=3×真季度帶算術組成);
  知識日 K=4 筆 filed 最大值;staleness T−最新季 end≤240 天;年度 V2 照 eq_r2k_oos.asof(740 天);
  mc=CommonStockSharesOutstanding(asof)×close;zn=(x−median)/std clip±3 by(date,sector);
  fwd=下月 close/close−1;五分位 EW、季頻調倉、25bps/邊;月有效檔<30 剔除。
確定性:載入後先 canonicalize(facts 依全欄位 mergesort)→ 結果為資料內容的純函數,與列序無關。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy --with pyarrow \
    python scripts/eq_ttm_ep_eval.py [--smoke]
"""
import sys, importlib.util
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
ANNZ = np.sqrt(12)
COST = 25 / 1e4
SMOKE = "--smoke" in sys.argv

_spec = importlib.util.spec_from_file_location(
    "eq_sue", "/home/anson/factor-lab/scripts/eq_sue_pead_eval.py")
_sue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sue)
build_quarters = _sue.build_quarters


def sh(s):
    s = s.dropna()
    return round(float(s.mean() / s.std(ddof=1) * ANNZ), 2) if len(s) > 1 and s.std() else 0.0


def tstat(s):
    s = s.dropna()
    return round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0


def asof(facts, base, cn, annual=False, stale=740):
    """逐字沿用 eq_r2k_oos.asof(v2 慣例)"""
    annf = facts["form"].astype(str).str.startswith(("10-K", "20-F"))
    f = facts[(facts["concept"] == cn) & (annf if annual else True)][
        ["ticker", "filed", "start", "end", "val"]].dropna(subset=["ticker", "filed", "val"])
    if annual:
        dur = (f["end"] - f["start"]).dt.days
        f = f[(dur >= 300) & (dur <= 400)]
    f = f.sort_values(["filed", "end"], kind="mergesort").groupby(["ticker", "filed"], as_index=False).last()
    f = f.sort_values("filed", kind="mergesort")
    m = pd.merge_asof(base, f[["ticker", "filed", "val"]].rename(columns={"val": cn}),
                      left_on="date", right_on="filed", by="ticker", direction="backward")
    m.loc[(m["date"] - m["filed"]).dt.days > stale, cn] = np.nan
    return m[cn].values


def build_ttm(quarters):
    """TTM 列:每 (ticker,end) → 連續4季和、知識日 K=max(4 filed)、連續帶 [180,300] 天"""
    q = quarters.sort_values(["ticker", "end"], kind="mergesort").reset_index(drop=True)
    g = q.groupby("ticker")
    vs = [q["val"]] + [g["val"].shift(i) for i in (1, 2, 3)]
    fs = [q["filed"]] + [g["filed"].shift(i) for i in (1, 2, 3)]
    gap = (q["end"] - g["end"].shift(3)).dt.days
    ok = gap.between(180, 300) & pd.concat(vs, axis=1).notna().all(axis=1)
    out = pd.DataFrame({"ticker": q["ticker"], "end": q["end"],
                        "K": pd.concat(fs, axis=1).max(axis=1),
                        "ttm": pd.concat(vs, axis=1).sum(axis=1)})[ok.values]
    return out.reset_index(drop=True)


def pit_ttm(base, ttm, delay_days=0, stale=240):
    s = ttm.copy()
    s["K_eff"] = s["K"] + pd.Timedelta(days=delay_days)
    s = s.sort_values(["K_eff", "end"], kind="mergesort")
    m = pd.merge_asof(base, s.rename(columns={"end": "q_end"}),
                      left_on="date", right_on="K_eff", by="ticker", direction="backward")
    return m["ttm"].where((m["date"] - m["q_end"]).dt.days <= stale).values


def zn_on(df, mask, col):
    """行業內 znorm(交集樣本上計算;樣本外=NaN)"""
    x = df[col].where(mask)
    g = x.groupby([df["date"], df["sector"]])
    return ((x - g.transform("median")) / g.transform(lambda v: v.std())).clip(-3, 3)


def monthly_ic(b, sig, min_n=30):
    v = b[b[sig].notna() & b["fwd"].notna()]
    ic = {}
    for dt, gd in v.groupby("date"):
        if len(gd) >= min_n:
            ic[dt] = stats.spearmanr(gd[sig], gd["fwd"]).correlation
    s = pd.Series(ic).sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def deciles(b, sig, min_n=30):
    v = b[b[sig].notna() & b["fwd"].notna()]
    dec = {}
    for dt, gd in v.groupby("date"):
        if len(gd) < min_n:
            continue
        d = pd.qcut(gd[sig].rank(method="first"), 10, labels=False, duplicates="drop")
        for di in range(int(d.max()) + 1):
            dec.setdefault(di, []).append(gd["fwd"][d == di].mean())
    return [float(np.mean(v)) * 100 for k, v in sorted(dec.items())]


def run_quarterly(b, sig, freq=3, cost=COST):
    """逐字沿用 eq_r2k_oos.run_quarterly(五分位 EW,成本只在 rebalance 收)"""
    bb = b[b[sig].notna() & b["fwd"].notna()]
    dts = sorted(bb["date"].unique())
    htop = hbot = None
    turns, ls, lx = [], {}, {}
    for i, dt in enumerate(dts):
        g = bb[bb["date"] == dt]
        if len(g) < 30:
            continue
        reb = (i % freq == 0) or htop is None
        if reb:
            q = pd.qcut(g[sig].rank(method="first"), 5, labels=False, duplicates="drop")
            if q.max() < 4:
                continue
            nt = set(g[q == q.max()]["ticker"]); nb = set(g[q == 0]["ticker"])
            if htop is not None:
                turns.append(len(nt ^ htop) / (len(nt) + len(htop)))
            htop, hbot = nt, nb
        gt = g[g["ticker"].isin(htop)]; gb = g[g["ticker"].isin(hbot)]
        if not len(gt) or not len(gb):
            continue
        c = cost * turns[-1] * 2 if (reb and turns) else 0.0
        ls[dt] = gt["fwd"].mean() - gb["fwd"].mean() - c
        lx[dt] = gt["fwd"].mean() - g["fwd"].mean() - c
    L = pd.Series(ls).sort_index(); X = pd.Series(lx).sort_index()
    L.index = pd.to_datetime(L.index); X.index = pd.to_datetime(X.index)
    return L, X, turns


def run_all(shuffle=False):
    facts = pd.read_parquet(EQ + "sec_facts_v2.parquet")
    px = pd.read_parquet(EQ + "prices_monthly.parquet")
    uni = pd.read_csv(EQ + "universe.csv")
    small = sorted(uni[uni["tier"] == "small"]["ticker"].tolist())
    if SMOKE:
        small = small[:80]
    facts = facts[facts["ticker"].isin(small)].copy()
    for c in ("start", "end", "filed"):
        facts[c] = facts[c].astype("datetime64[ns]")
    if shuffle:                        # 規格第9條:輸入亂序不變性測試
        facts = facts.sample(frac=1, random_state=42)
    # canonicalize:結果=資料內容的純函數
    facts = facts.sort_values(list(facts.columns), kind="mergesort").reset_index(drop=True)

    quarters, diag = build_quarters(facts)
    ttm = build_ttm(quarters)

    base = px[px["ticker"].isin(small)][["date", "ticker", "close"]].copy()
    base["date"] = base["date"].astype("datetime64[ns]")
    base = base.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)

    B = base.copy()
    B["ttm_ni"] = pit_ttm(base, ttm, 0)
    B["ttm_ni_d30"] = pit_ttm(base, ttm, 30)
    B["ann_ni"] = asof(facts, base, "NetIncomeLoss", annual=True, stale=740)
    B["shrs"] = asof(facts, base, "CommonStockSharesOutstanding", annual=False, stale=740)
    B["mc"] = B["shrs"] * B["close"]
    B.loc[B["mc"] <= 0, "mc"] = np.nan
    B["TTM_EP_raw"] = B["ttm_ni"] / B["mc"]
    B["ANN_EP_raw"] = B["ann_ni"] / B["mc"]
    B["TTM_EP_d30_raw"] = B["ttm_ni_d30"] / B["mc"]
    B["sector"] = B["ticker"].map(uni.set_index("ticker")["sector"])
    B = B.sort_values(["ticker", "date"], kind="mergesort")
    B["fwd"] = B.groupby("ticker")["close"].shift(-1) / B["close"] - 1
    B = B.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)

    inter = B["TTM_EP_raw"].notna() & B["ANN_EP_raw"].notna()          # 交集樣本
    inter_d = B["TTM_EP_d30_raw"].notna() & B["ANN_EP_raw"].notna()    # 延遲變體交集
    B["V1"] = zn_on(B, inter, "TTM_EP_raw")
    B["V2"] = zn_on(B, inter, "ANN_EP_raw")
    B["V3"] = B["V1"] - B["V2"]
    B["V1_d30"] = zn_on(B, inter_d, "TTM_EP_d30_raw")
    cov = B[inter & B["fwd"].notna()].groupby("date")["ticker"].count()
    return dict(B=B, diag=diag, cov=cov,
                n_ttm=len(ttm), inter_months=int((cov >= 30).sum()),
                cov_mean=float(cov.mean()) if len(cov) else 0.0)


def main():
    r = run_all()
    B, diag, cov = r["B"], r["diag"], r["cov"]
    print(f"== EQ_TTM_EP | tier=small | 交集樣本 ==")
    print(f"[覆蓋] 真季度 {diag['n_true_q']} | Q4推導率 {diag['q4_rate']:.1%} | TTM 列 {r['n_ttm']} | "
          f"交集月均 {r['cov_mean']:.0f} 檔 | 有效月(≥30檔) {r['inter_months']} | "
          f"歸因覆蓋門檻(≥150檔均/≥100月): {'足' if r['cov_mean'] >= 150 and r['inter_months'] >= 100 else '不足'}")
    ics = {}
    for v in ("V1", "V2", "V3", "V1_d30"):
        ic = monthly_ic(B, v)
        ics[v] = ic
        print(f"[IC] {v:6}: mean {ic.mean():+.4f}  IC_t {tstat(ic)}  IC-IR(年化) "
              f"{round(float(ic.mean()/ic.std(ddof=1)*ANNZ), 2) if ic.std() else 0}  (n={len(ic)})")
    ic1 = ics["V1"]
    mid_ic = ic1.index[len(ic1) // 2]
    print(f"[IC 兩半(另報)] V1 IS {ic1[ic1.index < mid_ic].mean():+.4f} / OOS {ic1[ic1.index >= mid_ic].mean():+.4f} | "
          f"V3 IS {ics['V3'][ics['V3'].index < mid_ic].mean():+.4f} / OOS {ics['V3'][ics['V3'].index >= mid_ic].mean():+.4f}")
    dec = deciles(B, "V1")
    mono = stats.spearmanr(range(len(dec)), dec).correlation
    print(f"[⑤] V1 十分位 D1(貴)→D10(便宜) %/月: " + " ".join(f"{x:+.2f}" for x in dec) + f"  Spearman {mono:+.2f}")
    for v in ("V1", "V2"):
        L, X, turns = run_quarterly(B, v)
        ex5 = L[L < L.quantile(.95)]
        mid = L.index[len(L) // 2]
        print(f"[LS] {v}: 季頻淨LS(25bps) Sh {sh(L)} (t={tstat(L)}, 均{L.mean()*100:+.2f}%/月)  "
              f"多頭超額 Sh {sh(X)} (t={tstat(X)}, 均{X.mean()*100:+.2f}%/月)  換手/rebal {np.mean(turns):.2f}")
        print(f"      剔最高5%月 LS Sh {sh(ex5)} (均{ex5.mean()*100:+.2f}%/月)  |  "
              f"IS(→{mid.date()}) {sh(L[L.index < mid])} / OOS {sh(L[L.index >= mid])}")
    # ⑦ 可重現性:連跑 + 亂序
    ic_a = monthly_ic(run_all()["B"], "V1")
    ic_b = monthly_ic(run_all(shuffle=True)["B"], "V1")
    same = ic1.equals(ic_a) and ic1.equals(ic_b)
    print(f"[⑦] 可重現(重跑+輸入亂序,V1 IC 逐位): {'PASS' if same else 'FAIL'}")


if __name__ == "__main__":
    main()
