#!/usr/bin/env python3
"""EQ SUE/PEAD 評測 — universe = tier=small (S&P600),預登錄規格逐字實作。
SUE = (NI_q − NI_{q-4}) / rolling8(dNI.shift(1)).std,winsor [-5,5];PIT merge_asof on filed。
主規格 = 十分位 × raw;另報 Q5 與 sector-demeaned 變體(N=4)。不做裁決,只印數字。
跑: cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy --with pyarrow \
    python scripts/eq_sue_pead_eval.py [--smoke]"""
import sys
import numpy as np, pandas as pd
from scipy import stats

EQ = "/home/anson/factor-lab/data/equity/"
ANN = np.sqrt(12)
COST = 30 / 1e4  # 30bps 單邊
SMOKE = "--smoke" in sys.argv


def sh(s):
    s = s.dropna()
    return round(float(s.mean() / s.std(ddof=1) * ANN), 2) if len(s) > 1 and s.std() else 0.0


def tstat(s):
    s = s.dropna()
    return round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() else 0.0


def dedup_first_filed(df):
    # 同 (ticker,start,end) 多筆 → 取 filed 最早;穩定排序確保可重現
    df = df.sort_values(["ticker", "start", "end", "filed"], kind="mergesort")
    return df.drop_duplicates(["ticker", "start", "end"], keep="first")


def build_quarters(facts):
    """季度盈餘序列(PIT):真季度 + Q4 推導。回傳 (quarters, 診斷)"""
    f = facts[(facts["concept"] == "NetIncomeLoss")
              & facts["form"].astype(str).str.startswith(("10-K", "10-Q"))]
    f = f[["ticker", "start", "end", "filed", "val"]].dropna().copy()
    for c in ("start", "end", "filed"):
        f[c] = f[c].astype("datetime64[ns]")
    dur = (f["end"] - f["start"]).dt.days
    tq = dedup_first_filed(f[(dur >= 60) & (dur <= 100)])      # 真季度
    fy = dedup_first_filed(f[(dur >= 300) & (dur <= 400)])     # FY 值
    # Q4 推導:FY 期間內 end ∈ (start_FY, end_FY] 的真季度,恰好 3 個才推導
    fy = fy.reset_index(drop=True)
    fy["fyid"] = fy.index
    m = fy.rename(columns={"start": "start_fy", "end": "end_fy", "filed": "filed_fy", "val": "val_fy"}) \
          .merge(tq[["ticker", "end", "val"]], on="ticker", how="inner")
    m = m[(m["end"] > m["start_fy"]) & (m["end"] <= m["end_fy"])]
    agg = m.groupby("fyid").agg(nq=("val", "size"), qsum=("val", "sum"), last_end=("end", "max"))
    ok = agg[agg["nq"] == 3].join(fy.set_index("fyid"))
    q4 = pd.DataFrame({"ticker": ok["ticker"], "start": ok["last_end"], "end": ok["end"],
                       "filed": ok["filed"], "val": ok["val"] - ok["qsum"]})
    quarters = dedup_first_filed(pd.concat([tq, q4], ignore_index=True))
    # shift(4) 需每 ticker 的 end 唯一:同 (ticker,end) 多 start → 取 filed 最早(穩定)
    quarters = quarters.sort_values(["ticker", "end", "filed"], kind="mergesort") \
                       .drop_duplicates(["ticker", "end"], keep="first").reset_index(drop=True)
    diag = dict(n_true_q=len(tq), n_fy=len(fy), n_q4=len(ok),
                q4_rate=len(ok) / max(len(fy), 1))
    return quarters, diag


def add_sue(q):
    q = q.sort_values(["ticker", "end"], kind="mergesort").reset_index(drop=True)
    g = q.groupby("ticker")
    ni4 = g["val"].shift(4)
    gap = (q["end"] - g["end"].shift(4)).dt.days
    q["dNI"] = np.where((gap >= 300) & (gap <= 430), q["val"] - ni4, np.nan)
    l1 = q.groupby("ticker")["dNI"].shift(1)  # 不含當季
    q["sigma"] = l1.groupby(q["ticker"]).rolling(8, min_periods=6).std(ddof=1) \
                   .reset_index(level=0, drop=True)
    q["SUE"] = np.where(q["sigma"].notna() & (q["sigma"] != 0), q["dNI"] / q["sigma"], np.nan)
    q["SUE"] = pd.Series(q["SUE"]).clip(-5, 5)
    return q


def build_panel(px, q, tickers, start_date, sec_map):
    base = px[px["ticker"].isin(tickers)][["date", "ticker", "close"]].copy()
    base["date"] = base["date"].astype("datetime64[ns]")
    base = base.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)
    s = q[["ticker", "filed", "end", "SUE"]].dropna(subset=["SUE"]).copy()
    s["filed"] = s["filed"].astype("datetime64[ns]")
    s["end"] = s["end"].astype("datetime64[ns]")

    def pit(delay_days):
        ss = s.copy()
        ss["filed_eff"] = ss["filed"] + pd.Timedelta(days=delay_days)
        ss = ss.sort_values(["filed_eff", "end"], kind="mergesort")
        mm = pd.merge_asof(base, ss.rename(columns={"end": "q_end"}),
                           left_on="date", right_on="filed_eff", by="ticker", direction="backward")
        # staleness:該筆 end >= T − 240 天,否則 NaN
        return mm["SUE"].where((mm["date"] - mm["q_end"]).dt.days <= 240).values

    b = base.copy()
    b["SUE"] = pit(0)
    b["SUE_d30"] = pit(30)  # 延遲壓測:filed <= T − 30
    b["sector"] = b["ticker"].map(sec_map)
    # forward return T→T+1(close-to-close);要求 T+1 確為下一個月(gap<=35天)
    b = b.sort_values(["ticker", "date"], kind="mergesort")
    g = b.groupby("ticker")
    nd, nc = g["date"].shift(-1), g["close"].shift(-1)
    b["fwd"] = np.where((nd - b["date"]).dt.days <= 35, nc / b["close"] - 1, np.nan)
    b = b[b["date"] >= start_date].copy()
    b["SUE_sd"] = b["SUE"] - b.groupby(["date", "sector"])["SUE"].transform("mean")
    return b.sort_values(["date", "ticker"], kind="mergesort").reset_index(drop=True)


def monthly_stats(b, sig, nq, min_n):
    """每月:Rank IC、分位組合(top/bot/EW/各分位均報酬/持股集合)"""
    recs = []
    v = b[b[sig].notna() & b["fwd"].notna()]
    for dt, gd in v.groupby("date"):
        if len(gd) < min_n:  # 有效檔數 < min_n 的月份剔除
            continue
        ic = stats.spearmanr(gd[sig], gd["fwd"]).correlation
        qq = pd.qcut(gd[sig].rank(method="first"), nq, labels=False, duplicates="drop")
        if qq.max() < nq - 1:
            continue
        top, bot = gd[qq == nq - 1], gd[qq == 0]
        recs.append(dict(date=dt, n=len(gd), ic=ic,
                         top=top["fwd"].mean(), bot=bot["fwd"].mean(), ew=gd["fwd"].mean(),
                         tset=frozenset(top["ticker"]), bset=frozenset(bot["ticker"]),
                         dec=[float(gd["fwd"][qq == i].mean()) for i in range(nq)]))
    df = pd.DataFrame(recs)
    if len(df):
        df = df.set_index("date").sort_index()
    return df


def add_turnover(df):
    """月度持股翻動比例(對稱差/總持股數,兩腿平均);首月 0"""
    tt, tb = [], []
    pt = pb = None
    for _, r in df.iterrows():
        if pt is None:
            tt.append(0.0); tb.append(0.0)
        else:
            tt.append(len(r["tset"] ^ pt) / (len(r["tset"]) + len(pt)))
            tb.append(len(r["bset"] ^ pb) / (len(r["bset"]) + len(pb)))
        pt, pb = r["tset"], r["bset"]
    df = df.copy()
    df["turn_top"] = tt
    df["turn"] = (np.array(tt) + np.array(tb)) / 2
    return df


def run_all():
    """全流程(純確定性,函數化,供可重現性比對跑兩次)"""
    facts = pd.read_parquet(EQ + "sec_facts_v2.parquet")
    px = pd.read_parquet(EQ + "prices_monthly.parquet")
    uni = pd.read_csv(EQ + "universe.csv")
    small = uni[uni["tier"] == "small"]["ticker"].tolist()
    if SMOKE:
        small = small[:80]
    start = pd.Timestamp("2018-01-01") if SMOKE else pd.Timestamp("1900-01-01")
    min_n = 10 if SMOKE else 50
    facts = facts[facts["ticker"].isin(small)]
    quarters, diag = build_quarters(facts)
    q = add_sue(quarters)
    sec_map = uni.set_index("ticker")["sector"]
    b = build_panel(px, q, small, start, sec_map)
    return dict(b=b, diag=diag, min_n=min_n,
                shapes=dict(facts=facts.shape, quarters=quarters.shape, panel=b.shape))


def main():
    r = run_all()
    b, diag, min_n = r["b"], r["diag"], r["min_n"]
    if SMOKE:
        print(f"[smoke] facts {r['shapes']['facts']}  quarters {r['shapes']['quarters']}  panel {r['shapes']['panel']}")

    main_df = add_turnover(monthly_stats(b, "SUE", 10, min_n))
    if not len(main_df):
        print("主規格無有效月份,中止"); return
    ic = main_df["ic"].dropna()
    if SMOKE:
        print("[smoke] 前幾個月 IC:")
        for dt, v in ic.head(6).items():
            print(f"  {dt.date()}  {v:+.4f}")

    ls = main_df["top"] - main_df["bot"]
    ls_net = ls - COST * main_df["turn"] * 2          # 換手 × 2 腿,30bps 單邊
    lx = main_df["top"] - main_df["ew"]
    lx_net = lx - COST * main_df["turn_top"]          # 多頭單腿成本
    a_top = main_df["top"] - main_df["ew"]
    a_bot = main_df["ew"] - main_df["bot"]

    print(f"\n== SUE/PEAD | tier=small | 主規格 = 十分位 × raw =="
          f"\n樣本 {main_df.index.min().date()} → {main_df.index.max().date()}  (n={len(main_df)} 月)")
    print(f"[10] 真季度筆數 {diag['n_true_q']} | FY 筆數 {diag['n_fy']} | Q4 推導成功 {diag['n_q4']} "
          f"(成功率 {diag['q4_rate']:.1%}) | 月均有效檔數 {main_df['n'].mean():.0f} | "
          f"平均月換手 {main_df['turn'].iloc[1:].mean():.3f}" if len(main_df) > 1 else "")
    print(f"[1] Rank IC: mean {ic.mean():+.4f}  IC_t {tstat(ic)}  IC-IR(年化) {round(float(ic.mean()/ic.std(ddof=1)*ANN),2)}  (n={len(ic)})")
    print(f"[2] 十分位等權: D10 Sh {sh(main_df['top'])}  D1 Sh {sh(main_df['bot'])}  "
          f"LS毛 Sh {sh(ls)}  LS淨@30bps Sh {sh(ls_net)}")
    print(f"[3] 多頭腿(D10)對 EW universe 超額: 毛 Sh {sh(lx)}  淨@30bps Sh {sh(lx_net)}")
    print(f"[4] 分腿毛 alpha: D10−EW Sh {sh(a_top)} (t={tstat(a_top)})  |  EW−D1 Sh {sh(a_bot)} (t={tstat(a_bot)})")
    print(f"[5] 剔除 LS 最高 5% 月份: LS毛 Sh {sh(ls[ls < ls.quantile(.95)])}")
    is_m = main_df.index.year <= 2019
    print(f"[6] IS(2014-2019): IC_t {tstat(main_df['ic'][is_m])}  淨LS Sh {sh(ls_net[is_m])}  (n={int(is_m.sum())})"
          f"  |  OOS(2020-2026): IC_t {tstat(main_df['ic'][~is_m])}  淨LS Sh {sh(ls_net[~is_m])}  (n={int((~is_m).sum())})")
    dec = np.array(main_df["dec"].tolist()).mean(axis=0) * 100
    mono = stats.spearmanr(range(len(dec)), dec).correlation
    print(f"[7] 十分位均月報酬(%) D1→D10: " + " ".join(f"{x:+.2f}" for x in dec) + f"  Spearman {mono:+.2f}")
    d30 = monthly_stats(b, "SUE_d30", 10, min_n)
    print(f"[8] 延遲壓測 filed<=T−30: IC_t {tstat(d30['ic']) if len(d30) else 'NA'}  (n={len(d30)})")
    print("[9] 其他變體:")
    for nq, sig, nm in [(5, "SUE", "五分位 × raw"), (10, "SUE_sd", "十分位 × sector-demeaned"),
                        (5, "SUE_sd", "五分位 × sector-demeaned")]:
        vd = monthly_stats(b, sig, nq, min_n)
        if len(vd):
            print(f"    {nm:26}: IC_t {tstat(vd['ic'])}  LS毛 Sh {sh(vd['top']-vd['bot'])}  (n={len(vd)})")
        else:
            print(f"    {nm:26}: 無有效月份")
    # [11] 可重現性:全流程重跑,比對主規格 IC 序列逐位相同
    r2 = run_all()
    ic2 = monthly_stats(r2["b"], "SUE", 10, r2["min_n"])["ic"]
    same = main_df["ic"].equals(ic2) and main_df["ic"].index.equals(ic2.index)
    print(f"[11] 可重現性(全流程跑兩次,IC 序列逐位比對): {'PASS' if same else 'FAIL'}")


if __name__ == "__main__":
    main()
