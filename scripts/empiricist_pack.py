#!/usr/bin/env python3
"""empiricist_pack.py — factor-lab 辯論流程的 Empiricist 標準套餐(單一入口)。

輸入是一份預註冊 spec(JSON,凍結後 sha256 記入所有產物),依序:
  stage0     完整性(lint + 截斷無前視)+ 成分符號 + 控制變數適格性 + 便宜篩檢 → PASS / KILL
             **鎖靜默**:只印判決與原因,候選因子的任何聚合數字只落盤不列印。
  lock       主規格獨立跑兩次,差 < 1e-8 才 PASS;FAIL 落盤 lock_fail_N.json 並寫 ledger。
  run        完整套餐 + 閘門表 + DSR/Bonferroni(讀 ledger 家族 N)→ results.json + summary.md + ledger。
  noise      每日橫截面/時序打亂訊號 K 次,估各閘門的純噪音通過率(v2.4 §6)。

  cd /home/anson/factor-lab && uv run --with "numpy>=2" --with pandas --with scipy \
      python scripts/empiricist_pack.py {stage0|lock|run|noise} empirical_runs/<SID>_spec.json

spec 欄位見 SPEC_DEFAULTS;type=cross 用 data=universe_1d(逐幣 factor(df))或 data=panel
(module.xs_panel(**params) 回傳 dict(SIG, R[, F, ok, close, dv, entry_lag]))。
"""
import sys, os, re, json, datetime, importlib, inspect, warnings
import numpy as np, pandas as pd

warnings.filterwarnings("ignore")
ROOT = "/home/anson/factor-lab"
sys.path.insert(0, ROOT); sys.path.insert(0, ROOT + "/scripts")
import labkit as K
import ledger as L

ER = ROOT + "/empirical_runs/"
UNI_PKL = ER + "universe_1d.pkl"
FUNDING_PKL = ER + "funding_1d.pkl"
ASSETS = {"BTC": ER + "btcusdt_1d_1500.pkl", "ETH": ER + "ethusdt_1d_1000.pkl",
          "XAU": ER + "xau_1d.pkl", "OIL": ER + "oil_1d.pkl"}
PPY = {"1d": 365.0, "1w": 52.0}

SPEC_DEFAULTS = {
    "func": "factor", "params": {}, "direction": 1, "components": {}, "planned_trials": 1,
    "oos_start": "2024-01-01", "cost_bps": 10.0, "q": 5,
    # cross
    "data": "universe_1d", "hold": 1, "min_n": 30, "entry_lag": None, "funding": False,
    "controls": ["mom20", "sig20", "max21", "ladv20"],
    # directional
    "assets": ["BTC", "ETH", "XAU", "OIL"], "tfs": ["1d", "1w"], "primary_tf": "1d",
    "construct": "quintile", "vol_target": 0.02,
    # stage0
    "screen_min_t": 1.0,
}

# 閘門表(唯一定義處)。noise = 純噪音下的名目通過率(常態近似);有 <SID>_noise.json 時以實測值取代。
# 第四欄是角色:count = 計入通過數且 FAIL 可否決;veto = 只能否決;disclose = 只揭露,既不計入也不否決。
# 實測噪音通過率 >50% 的 count 閘門自動降為 veto(v2.4 §6)。
#
# v2.5(2026-09-24,使用者決定採 SIM-2026-09-14-001 §11.2 選項 (a)):cross 以排序層為正式判準,
# 美元層降為 disclose。依據 empirical_runs/power_curve_20260924_report.md:T≈5.55 年、~47 幣下,
# 美元層 G2(i) 需真實淨 Sharpe≈1.0 才有 50% 通過,真實 IC 0.01–0.04 落在「排序層必過、美元層必死」帶。
# directional 不受影響。
GATES = {
    "cross": [
        ("S1_ic_mag",   "|rank IC| > 0.02",                            None,   "count"),
        ("S2_ic_t",     "閘門 IC t ≥ 2(hold>1:min(h1 NW, h=hold NW, 非重疊))", 0.023, "count"),
        ("S3_ic_ir",    "IC-IR ≥ 0.3",                                 None,   "count"),
        ("S4_mono",     "Mono ≥ 0.7(五分位多頭淨報酬對分位序)",          0.117,  "count"),  # 精確:14/120 排列
        ("R1_loyo_ic",  "剔最壞單年後 1 日 IC NW t ≥ 1.5",               None,   "count"),
        ("R2_delay_ic", "訊號再延遲 1 期:IC 同號且 NW t ≥ 主規格一半",    None,   "count"),
        ("R3_comp",     "每個成分宣告方向 IC t ≥ 1(同號且有可測貢獻)",     None,   "count"),
        ("M1_marginal", "對全部控制變數聯合 Fama-MacBeth,候選係數 NW t ≥ 2", 0.023, "count"),
        ("D1_bonf",     "閘門 IC t ≥ Bonferroni(N_family)",            None,   "count"),
        ("T1_trade",    "淨 Sharpe ≥ 1.0 或 Mono ≥ 0.7(v2.4 口徑)",     None,   "disclose"),
        ("T2_net_t",    "淨 NW t ≥ 2",                                  0.023,  "disclose"),
        ("T3_maxdd",    "MaxDD > -30%",                                None,   "disclose"),
        ("R1_loyo",     "剔最壞單年後淨 NW t ≥ 1.5",                     None,   "disclose"),
        ("R2_delay",    "延遲 1 期進場同號且淨 |t| ≥ 主規格一半",          None,   "disclose"),
        ("D2_dsr",      "淨 Sharpe > DSR 期望最大值",                    None,   "disclose"),
    ],
    "directional": [
        ("T1_net",      "組合淨 Sharpe > 0.5",                          None,   "count"),
        ("T2_excess",   "對 Always-Long×同 vol-target 主動報酬 Sharpe > 0", None, "count"),
        ("T3_maxdd",    "MaxDD > -30%",                                None,   "count"),
        ("T4_net_t",    "淨 NW t ≥ 2(非重疊 t 輔助)",                   0.023,  "count"),
        ("T5_mono",     "Mono ≥ 0.7",                                  None,   "count"),
        ("R1_assets",   "各資產淨 Sharpe 皆 > 0",                        None,   "count"),
        ("R2_loyo",     "剔最壞單年後淨 NW t ≥ 1.5",                     None,   "count"),
        ("D1_bonf",     "淨 NW t ≥ Bonferroni(N_family)",              None,   "count"),
        ("D2_dsr",      "淨 Sharpe > DSR 期望最大值",                    None,   "count"),
    ],
}


# ------------------------------------------------------------------ spec / io
def load_spec(path):
    spec = {**SPEC_DEFAULTS, **json.load(open(path))}
    for k in ("session", "family", "factor", "module", "type"):
        if not spec.get(k):
            raise SystemExit(f"spec 缺 {k}")
    if spec["type"] not in GATES:
        raise SystemExit("type 必須是 cross 或 directional")
    spec["_path"] = path
    spec["_sha"] = K.sha256_file(path)
    mod = importlib.import_module(spec["module"])
    spec["_mod"] = mod
    spec["_mod_path"] = inspect.getsourcefile(mod)
    spec["_mod_sha"] = K.sha256_file(spec["_mod_path"])
    return spec


def out_path(spec, tag):
    return os.environ.get("FACTORLAB_OUT", ER) + f"{spec['session']}_{tag}"


def stamp(spec):
    return {"session": spec["session"], "family": spec["family"], "factor": spec["factor"],
            "module": spec["module"], "module_path": os.path.relpath(spec["_mod_path"], ROOT),
            "type": spec["type"], "params": spec["params"],
            "asset": spec["data"] if spec["type"] == "cross" else "/".join(spec["assets"]),
            "spec_sha256": spec["_sha"], "module_sha256": spec["_mod_sha"],
            "runner_sha256": K.sha256_file(os.path.abspath(__file__)),
            "time": datetime.datetime.now().isoformat(timespec="seconds")}


def ledger_row(spec, factor, kind, verdict, **metrics):
    keep = {k: v for k, v in metrics.items() if k in L.OPTIONAL and v is not None}
    return {"date": datetime.date.today().isoformat(), "session": spec["session"],
            "family": spec["family"], "kind": kind, "factor": factor, "module": spec["module"],
            "type": spec["type"],
            "asset": spec["data"] if spec["type"] == "cross" else "/".join(spec["assets"]),
            "tf": spec.get("primary_tf", "1d") if spec["type"] == "directional" else "1d",
            "params": spec["params"], "verdict": verdict, **keep}


# ------------------------------------------------------------------ cross:資料
def _wide(uni, fn):
    cols = {}
    for co, df in uni.items():
        idx = pd.to_datetime(df["timestamp"], unit="ms").dt.normalize()
        cols[co] = pd.Series(np.asarray(fn(co, df), dtype="float64").ravel(), index=idx)
    return pd.DataFrame(cols).sort_index()


def load_cross(spec, truncate=0):
    """回傳 dict(SIG, R, F, ok, FWD, entry_lag, CL, DV)。truncate>0 → 丟掉最後 truncate 天的原始資料。"""
    mod, p = spec["_mod"], spec["params"]
    if spec["data"] == "universe_1d":
        fn = getattr(mod, spec["func"])
        uni = pd.read_pickle(UNI_PKL)
        if truncate:
            cut = max(int(d["timestamp"].max()) for d in uni.values()) - truncate * 86_400_000
            uni = {c: d[d["timestamp"] <= cut].reset_index(drop=True) for c, d in uni.items()}
            uni = {c: d for c, d in uni.items() if len(d)}
        SIG = _wide(uni, lambda c, d: fn(d, **p))
        CL = _wide(uni, lambda c, d: d["close"].astype(float)).reindex(index=SIG.index, columns=SIG.columns)
        DV = _wide(uni, lambda c, d: d["close"].astype(float) * d["volume"].astype(float)).reindex_like(CL)
        R = CL.shift(-1) / CL - 1.0
        D = {"SIG": SIG, "R": R, "CL": CL, "DV": DV, "entry_lag": 0}
    elif spec["data"] == "panel":
        D = dict(mod.xs_panel(**p, **({"truncate": truncate} if truncate else {})))
        D.setdefault("entry_lag", 1)
    else:
        raise SystemExit("data 必須是 universe_1d 或 panel")
    if spec["entry_lag"] is not None:
        D["entry_lag"] = int(spec["entry_lag"])
    SIG = D["SIG"] * float(spec["direction"])
    D["SIG"] = SIG
    D["R"] = D["R"].reindex(index=SIG.index, columns=SIG.columns)
    if spec["funding"] and D.get("F") is None:
        fund = pd.read_pickle(FUNDING_PKL)
        cols = {c: pd.Series(d["funding"].astype(float).values,
                             index=pd.to_datetime(d["timestamp"], unit="ms").dt.normalize())
                for c, d in fund.items()}
        FF = pd.DataFrame(cols)
        end = min(FF.dropna(how="all").index.max(), SIG.index.max())
        for k in ("SIG", "R", "CL", "DV"):
            if D.get(k) is not None:
                D[k] = D[k].loc[:end]
        D["F"] = FF.reindex(index=D["SIG"].index, columns=D["SIG"].columns)
    D.setdefault("F", None)
    ok = D.get("ok")
    D["ok"] = (ok.reindex_like(D["SIG"]).fillna(False).astype(bool) if ok is not None
               else D["SIG"].notna())
    D["FWD"] = D["R"].shift(-D["entry_lag"])
    return D


def builtin_controls(D, names):
    """控制變數與訊號同資訊時點:entry_lag=0(訊號已 shift)→ 控制也 shift(1)。"""
    CL, DV = D.get("CL"), D.get("DV")
    if CL is None:
        return {}
    ret = CL / CL.shift(1) - 1.0
    raw = {"mom20": CL / CL.shift(20) - 1.0,
           "sig20": ret.rolling(20, min_periods=20).std(ddof=1),
           "max21": ret.rolling(21, min_periods=21).max()}
    if DV is not None:
        raw["ladv20"] = np.log(DV.rolling(20, min_periods=20).mean().where(lambda x: x > 0))
    sh = 1 - D["entry_lag"]
    return {k: raw[k].shift(sh).reindex_like(D["SIG"]) for k in names if k in raw}


def components_cross(spec, D):
    """module.components(**params) → {name: 寬表}(與 SIG 同網格、同資訊時點)。"""
    if not spec["components"]:
        return {}
    comps = spec["_mod"].components(**spec["params"])
    if spec["data"] == "universe_1d":
        uni = pd.read_pickle(UNI_PKL)
        comps = {name: _wide(uni, lambda c, d, f=f: f(d)) for name, f in comps.items()}
    return {k: v.reindex_like(D["SIG"]) for k, v in comps.items()}


def bt(spec, D, SIG=None, **kw):
    a = dict(hold=spec["hold"], cost_bps=spec["cost_bps"], entry_lag=D["entry_lag"],
             q=spec["q"], min_n=spec["min_n"])
    a.update(kw)
    return K.backtest_xs(D["SIG"] if SIG is None else SIG, D["R"], D["F"], **a)


def ic(spec, D, SIG=None):
    return K.ic_stats(K.ic_series(D["SIG"] if SIG is None else SIG, D["FWD"], spec["min_n"]))


def fwd_h(D, h):
    return np.expm1(np.log1p(D["R"]).rolling(h, min_periods=h).sum().shift(-(h - 1 + D["entry_lag"])))


def ic_gate(spec, D, SIG=None):
    """閘門用 IC。量級/IC-IR(S1/S3)維持 1 日 IC(門檻按 1 日校準,長 horizon 會自然放大);
    顯著性 gate_t(S2/D1/stage0 篩檢)在 hold>1 時取 min(1 日 NW t, h=hold 的 NW t[lag ≥ h], 非重疊 t)。"""
    s = ic(spec, D, SIG)
    h = int(spec["hold"])
    out = {**s, "h": h, "gate_t": s.get("ic_nw_t", float("nan"))}
    if h == 1:
        return out
    ics = K.ic_series(D["SIG"] if SIG is None else SIG, fwd_h(D, h), spec["min_n"])
    if len(ics) < 3:
        return {**out, "gate_t": float("nan")}
    sub = ics.iloc[::h]
    out.update({"h_rank_ic": float(ics.mean()), "h_ic_nw_t": K.nw_t(ics, L=max(10, h)),
                "h_nonoverlap_t": float(sub.mean() / (sub.std(ddof=1) / np.sqrt(len(sub))))
                if len(sub) > 2 else float("nan")})
    out["gate_t"] = float(np.nanmin([out["gate_t"], out["h_ic_nw_t"], out["h_nonoverlap_t"]]))
    return out


def control_eligible(own_ic, cand_ic, rho):
    """v2.4 §4:控制先乘 sign(ρ)(與候選的橫截面相關)對齊;對齊後更強且與候選 IC 反號
    → 殘差化會把控制的 alpha 加回候選(殘留 >100% 的算術 artifact),不適格。"""
    return not (abs(own_ic) > abs(cand_ic) and np.sign(np.sign(rho) * own_ic) != np.sign(cand_ic))


# ------------------------------------------------------------------ directional:資料與組合
def to_weekly(df):
    d = df.copy(); d.index = pd.to_datetime(d["timestamp"], unit="ms")
    w = pd.DataFrame({"open": d["open"].resample("W").first(), "high": d["high"].resample("W").max(),
                      "low": d["low"].resample("W").min(), "close": d["close"].resample("W").last(),
                      "volume": d["volume"].resample("W").sum()}).dropna()
    w["timestamp"] = w.index.values.astype("datetime64[ms]").astype("int64")
    return w.reset_index(drop=True)


def load_dir(spec, asset, tf, truncate=0):
    df = pd.read_pickle(ASSETS[asset])
    if truncate:
        df = df.iloc[:-truncate]
    return to_weekly(df) if tf == "1w" else df.reset_index(drop=True)


def dir_series(spec, df, tf, sig=None):
    """回傳 DataFrame(date, sig, fwd, pos, gross, net, bench_net, turn)。sig 給定時略過 factor()。"""
    c = df["close"].astype(float).reset_index(drop=True)
    if sig is None:
        fn = getattr(spec["_mod"], spec["func"])
        sig = pd.Series(np.asarray(fn(df, **spec["params"]), dtype="float64")) * float(spec["direction"])
    fwd = c.shift(-1) / c - 1.0
    if spec["construct"] == "quintile":
        qwin = 252 if tf == "1d" else 52
        hi = sig.rolling(qwin, min_periods=qwin // 2).quantile(0.8)
        lo = sig.rolling(qwin, min_periods=qwin // 2).quantile(0.2)
        pos = pd.Series(0.0, index=sig.index); pos[sig >= hi] = 1.0; pos[sig <= lo] = -1.0
    else:
        pos = np.sign(sig).fillna(0.0)
    if spec["vol_target"]:
        tgt = spec["vol_target"] * (np.sqrt(7.0) if tf == "1w" else 1.0)
        rvol = c.pct_change().rolling(20, min_periods=20).std().shift(1)
        scale = (tgt / rvol).clip(upper=1.0).fillna(0.0)
    else:
        scale = pd.Series(1.0, index=sig.index)
    cb = spec["cost_bps"] / 1e4
    posn = pos * scale
    turn = posn.diff().abs().fillna(posn.abs())
    gross = (posn * fwd).fillna(0.0)
    bturn = scale.diff().abs().fillna(scale.abs())
    return pd.DataFrame({"date": pd.to_datetime(df["timestamp"], unit="ms").values, "sig": sig, "fwd": fwd,
                         "pos": posn, "gross": gross, "net": (gross - turn * cb).fillna(0.0),
                         "bench_net": (scale * fwd - bturn * cb).fillna(0.0), "turn": turn})


def mono_ts(sig, fwd, q=5):
    from scipy import stats
    m = sig.notna() & fwd.notna()
    try:
        lab = pd.qcut(sig[m], q, labels=False, duplicates="drop")
    except ValueError:
        return None
    qm = fwd[m].groupby(lab).mean()
    return float(stats.spearmanr(range(len(qm)), qm.values).correlation) if len(qm) >= 3 else None


def dir_block(s, ppy, oos_start):
    from scipy import stats
    net = s["net"]
    m = s["sig"].notna() & s["fwd"].notna()
    yr = pd.DatetimeIndex(s["date"]).year
    active = net - s["bench_net"]
    p, b = K.perf(net, ppy), K.perf(s["bench_net"], ppy)
    oos = pd.DatetimeIndex(s["date"]) >= pd.Timestamp(oos_start)
    yearly = {int(y): K.perf(net[yr == y], ppy).get("sharpe") for y in sorted(set(yr))}
    loyo = {int(y): K.nw_t(net[yr != y]) for y in sorted(set(yr))}
    return {**p,
            "gross_sharpe": K.perf(s["gross"], ppy).get("sharpe"),
            "t_nonoverlap": K.nonoverlap_t(net, 5 if ppy > 100 else 4),
            "rank_ic": float(stats.spearmanr(s["sig"][m], s["fwd"][m]).correlation) if m.sum() > 10 else None,
            "mono": mono_ts(s["sig"], s["fwd"]),
            "ann_turnover": float(s["turn"].sum() / (len(s) / ppy)),
            "cost_drag_ann": float((s["gross"] - net).mean() * ppy),
            "bench_sharpe": b.get("sharpe"),
            "excess_sharpe_diff": (p.get("sharpe") or 0) - (b.get("sharpe") or 0),
            "active": K.perf(active, ppy),
            "is_sharpe": K.perf(net[~oos], ppy).get("sharpe"),
            "oos_sharpe": K.perf(net[oos], ppy).get("sharpe"),
            "yearly_sharpe": yearly, "loyo_nw_t": loyo,
            "loyo_min": float(np.nanmin(list(loyo.values()))) if loyo else None}


def run_directional(spec):
    res = {"per": {}}
    for tf in spec["tfs"]:
        frames = {}
        for a in spec["assets"]:
            s = dir_series(spec, load_dir(spec, a, tf), tf)
            frames[a] = s
            res["per"][f"{a}_{tf}"] = dir_block(s, PPY[tf], spec["oos_start"])
        cols = {k: v.set_index("date")[["gross", "net", "bench_net", "turn"]] for k, v in frames.items()}
        port = pd.concat(cols, axis=1)
        ps = pd.DataFrame({c: port.xs(c, axis=1, level=1).mean(axis=1) for c in ["gross", "net", "bench_net", "turn"]})
        allsig = pd.concat([f["sig"] for f in frames.values()]); allfwd = pd.concat([f["fwd"] for f in frames.values()])
        ps = ps.reset_index().rename(columns={"index": "date"})
        ps["sig"] = np.nan; ps["fwd"] = np.nan
        blk = dir_block(ps, PPY[tf], spec["oos_start"])
        blk["rank_ic"] = float(np.nanmean([res["per"][f"{a}_{tf}"]["rank_ic"] or np.nan for a in spec["assets"]]))
        blk["mono"] = mono_ts(allsig.reset_index(drop=True), allfwd.reset_index(drop=True))
        res[f"portfolio_{tf}"] = blk
    return res


# ------------------------------------------------------------------ stage0
def lint(spec):
    """訊號程式碼不得出現負向 shift 或 *_fwd(v2.4 §7)。panel 模式的報酬建構須放在 lint_paths 以外。"""
    hits = []
    for p in spec.get("lint_paths") or [spec["_mod_path"]]:
        src = open(os.path.join(ROOT, p) if not os.path.isabs(p) else p).read()
        hits += [f"{os.path.basename(p)}:{pat}" for pat in (r"shift\(\s*-", r"_fwd") if re.search(pat, src)]
    return {"lint_ok": not hits, "lint_hits": hits}


def truncation_identical(spec, n=40):
    if spec["type"] == "cross":
        a = load_cross(spec)["SIG"]; b = load_cross(spec, truncate=n)["SIG"]
        ov = a.index.intersection(b.index)
        A, B = a.loc[ov], b.loc[ov].reindex(columns=a.columns)
        return bool(((A.isna() & B.isna()) | ((A - B).abs() < 1e-12)).all().all())
    ok = True
    for asset in spec["assets"]:
        df = load_dir(spec, asset, "1d")
        fn = getattr(spec["_mod"], spec["func"])
        a = pd.Series(np.asarray(fn(df, **spec["params"]), dtype="float64"))
        b = pd.Series(np.asarray(fn(df.iloc[:-n].reset_index(drop=True), **spec["params"]), dtype="float64"))
        A = a.iloc[:len(b)]
        ok &= bool(((A.isna() & b.isna()) | ((A - b).abs() < 1e-12)).all())
    return ok


def cmd_stage0(spec):
    reasons, out = [], {**stamp(spec), "stage": 0}
    out.update(lint(spec))
    if not out["lint_ok"]:
        reasons.append(f"lint:訊號模組引用 {out['lint_hits']}")
    out["no_lookahead_truncation_identical"] = truncation_identical(spec)
    if not out["no_lookahead_truncation_identical"]:
        reasons.append("截斷重算與全樣本不一致(前視)")

    fam_rows = [r for r in L.load() if r["_family"] == spec["family"] and r["_kind"] in ("status", "closure")]
    out["family_closures"] = [str(r.get("factor"))[:80] + " → " + str(r.get("verdict"))[:160] for r in fam_rows]

    sign = np.sign(spec["direction"])
    if spec["type"] == "cross":
        D = load_cross(spec)
        main = ic(spec, D)
        comps = components_cross(spec, D)
        out["components"] = {}
        for name, Z in comps.items():
            s = ic(spec, D, Z.where(D["ok"]) * sign)
            decl = int(spec["components"][name])
            out["components"][name] = {"declared": decl, **s}
            if np.sign(s.get("rank_ic", 0)) != decl:
                reasons.append(f"成分 {name} 實測符號與宣告相反(敘事不成立)")
            elif decl * s.get("ic_nw_t", 0) < spec["screen_min_t"]:
                reasons.append(f"成分 {name} 宣告方向 t < {spec['screen_min_t']}(無可測貢獻,組合屬稀釋)")
        ctrl = builtin_controls(D, spec["controls"])
        out["controls_own_ic"] = {k: ic(spec, D, v.where(D["ok"])) for k, v in ctrl.items()}
        out["controls_xs_rho"] = {k: K.xs_corr(D["SIG"], v.where(D["ok"]), spec["min_n"]) for k, v in ctrl.items()}
        out["controls_eligible"] = {
            k: control_eligible(v.get("rank_ic", 0), main.get("rank_ic", 0), out["controls_xs_rho"][k])
            for k, v in out["controls_own_ic"].items()}
        main = {**main, "gate_ic": ic_gate(spec, D)}
        screen_t = main["gate_ic"]["gate_t"]
    else:
        s = dir_series(spec, load_dir(spec, spec["assets"][0], spec["primary_tf"]), spec["primary_tf"])
        screen_t = K.nw_t(s["net"])
        main = {"screen_asset": spec["assets"][0], "net_nw_t": screen_t}
    out["screen"] = {**main, "rule": f"宣告方向閘門 t(h=hold)≥ {spec['screen_min_t']}",
                     "noise_pass_rate": "≈16%(單尾 t≥1)"}
    if not (screen_t >= spec["screen_min_t"]):
        reasons.append(f"便宜篩檢未過(宣告方向 t < {spec['screen_min_t']})")
    out["verdict"] = "KILL" if reasons else "PASS"
    out["reasons"] = reasons
    K.dump(out_path(spec, "stage0.json"), out)
    L.append([ledger_row(spec, f"{spec['factor']} stage0 篩檢", "trial",
                         "KILL_STAGE0" if reasons else "PENDING", stage="stage0",
                         note="; ".join(reasons)[:200] or "stage0 PASS")])
    # 鎖靜默:只印判決、原因、家族封線與控制變數適格性(非候選因子數字)
    print(f"stage0 {out['verdict']}")
    for r in reasons:
        print("  ✗", r)
    for c in out["family_closures"]:
        print("  [封線/狀態]", c)
    if spec["type"] == "cross":
        print("  控制變數適格:", out["controls_eligible"])
    print("→", out_path(spec, "stage0.json"))


# ------------------------------------------------------------------ lock
def main_metrics(spec):
    if spec["type"] == "cross":
        D = load_cross(spec)
        b = bt(spec, D)
        p = K.perf(b["net"]); s = ic(spec, D)
        return {"net_sharpe": p.get("sharpe"), "net_nw_t": p.get("nw_t"), "rank_ic": s.get("rank_ic"),
                "turn_mean": float(b["turn"].mean())}
    s = dir_series(spec, load_dir(spec, spec["assets"][0], spec["primary_tf"]), spec["primary_tf"])
    p = K.perf(s["net"], PPY[spec["primary_tf"]])
    return {"net_sharpe": p.get("sharpe"), "net_nw_t": p.get("nw_t"), "turn_sum": float(s["turn"].sum())}


def cmd_lock(spec):
    st0 = out_path(spec, "stage0.json")
    if not os.path.exists(st0) or json.load(open(st0))["verdict"] != "PASS":
        raise SystemExit("stage0 未 PASS,不得上鎖")
    a, b = main_metrics(spec), main_metrics(spec)
    diffs = {k: abs((a[k] or 0) - (b[k] or 0)) for k in a}
    ok = all(v < 1e-8 for v in diffs.values())
    payload = {**stamp(spec), "abs_diffs": diffs, "tolerance": 1e-8, "PASS": ok}
    if not ok:
        n = 1
        while os.path.exists(out_path(spec, f"lock_fail_{n}.json")):
            n += 1
        K.dump(out_path(spec, f"lock_fail_{n}.json"), payload)
        L.append([ledger_row(spec, f"[lock-FAIL] {spec['factor']} 第 {n} 次", "lock_fail", "FAIL")])
        raise SystemExit("複製鎖 FAIL(已落盤並計入 ledger)")
    K.dump(out_path(spec, "lock.json"), payload)
    print("複製鎖 PASS(鎖靜默:數字只落盤)")


# ------------------------------------------------------------------ run
def gates_cross(spec, res, N):
    m, gi, g = res["main"], res["gate_ic"], {}
    thr_b = K.bonferroni_t(N)
    thr_d = K.dsr_threshold(N, m["T_years"])
    g["S1_ic_mag"] = abs(gi.get("rank_ic", 0)) > 0.02
    g["S2_ic_t"] = gi.get("gate_t", 0) >= 2.0
    g["S3_ic_ir"] = gi.get("ic_ir", 0) >= 0.3
    g["T1_trade"] = (m.get("sharpe", 0) >= 1.0) or ((res["mono"] or 0) >= 0.7)
    g["T2_net_t"] = m.get("nw_t", 0) >= 2.0
    g["T3_maxdd"] = m.get("max_drawdown", -1) > -0.30
    g["R1_loyo"] = (res["loyo_min"] or -9) >= 1.5
    d = res["delayed"]
    g["R2_delay"] = bool(np.sign(d.get("nw_t", 0)) == np.sign(m.get("nw_t", 0))
                         and abs(d.get("nw_t", 0)) >= 0.5 * abs(m.get("nw_t", 0)))
    comps = res.get("components", {})
    g["R3_comp"] = (all(v["declared"] * v.get("ic_nw_t", 0) >= spec["screen_min_t"] for v in comps.values())
                    if comps else None)
    g["D1_bonf"] = gi.get("gate_t", 0) >= thr_b
    g["D2_dsr"] = m.get("sharpe", 0) > thr_d
    # v2.5 排序層閘門(SIG 已乘宣告方向,正值 = 宣告方向)
    rl = res["rank_layer"]
    g["S4_mono"] = (res["mono"] or 0) >= 0.7
    g["R1_loyo_ic"] = (rl["loyo_ic_min"] if rl["loyo_ic_min"] is not None else -9) >= 1.5
    t0, td = m.get("ic_nw_t", 0) or 0, rl["delayed_ic"].get("ic_nw_t", 0) or 0
    g["R2_delay_ic"] = bool(t0 > 0 and td >= 0.5 * t0)
    fm = rl.get("fm_marginal")
    g["M1_marginal"] = None if fm is None else bool((fm.get("nw_t") or 0) >= 2.0)
    return g, {"N_family": N, "bonferroni_t": thr_b, "dsr_expected_max": thr_d}


def gates_dir(spec, res, N):
    m = res[f"portfolio_{spec['primary_tf']}"]
    T = m["n"] / PPY[spec["primary_tf"]]
    thr_b, thr_d = K.bonferroni_t(N), K.dsr_threshold(N, T)
    per = [v for k, v in res["per"].items() if k.endswith(spec["primary_tf"])]
    g = {"T1_net": m.get("sharpe", 0) > 0.5,
         "T2_excess": m["active"].get("sharpe", 0) > 0,
         "T3_maxdd": m.get("max_drawdown", -1) > -0.30,
         "T4_net_t": m.get("nw_t", 0) >= 2.0,
         "T5_mono": (m.get("mono") or 0) >= 0.7,
         "R1_assets": all((v.get("sharpe") or 0) > 0 for v in per),
         "R2_loyo": (m.get("loyo_min") or -9) >= 1.5,
         "D1_bonf": m.get("nw_t", 0) >= thr_b,
         "D2_dsr": m.get("sharpe", 0) > thr_d}
    return g, {"N_family": N, "bonferroni_t": thr_b, "dsr_expected_max": thr_d, "T_years": T}


def run_cross(spec):
    D = load_cross(spec)
    b = bt(spec, D)
    s = ic(spec, D)
    res = {"main": {**K.perf(b["net"]), **s,
                    "gross_sharpe": K.perf(b["gross"]).get("sharpe"),
                    "turn_mean": float(b["turn"].mean()), "cost_drag_ann": float(b["cost"].mean() * 365),
                    "funding_ann": float(b["fund"].mean() * 365), "n_missing_R": int(b["n_missing_R"].sum()),
                    "date_first": b.index.min(), "date_last": b.index.max(), "T_years": len(b) / 365.0}}
    res["gate_ic"] = ic_gate(spec, D)
    # 非重疊 IC(各 horizon)
    res["ic_horizons"] = {}
    for h in (1, 5, 10, 20):
        ics = K.ic_series(D["SIG"], fwd_h(D, h), spec["min_n"])
        sub = ics.iloc[::h]
        res["ic_horizons"][h] = {"rank_ic": float(ics.mean()) if len(ics) else None, "nw_t": K.nw_t(ics, L=max(10, h)),
                                 "nonoverlap_t": float(sub.mean() / (sub.std(ddof=1) / np.sqrt(len(sub))))
                                 if len(sub) > 2 else None}
    # 年度 + LOYO
    yr = b.index.year
    res["yearly"] = {int(y): {"sharpe": K.perf(b.loc[yr == y, "net"]).get("sharpe"),
                              "ic": float(K.ic_series(D["SIG"].loc[D["SIG"].index.year == y],
                                                      D["FWD"].loc[D["FWD"].index.year == y], spec["min_n"]).mean())}
                     for y in sorted(set(yr))}
    loyo = {int(y): K.nw_t(b.loc[yr != y, "net"]) for y in sorted(set(yr))}
    res["loyo_nw_t"] = loyo
    res["loyo_min"] = float(np.nanmin(list(loyo.values())))
    oos = b.index >= pd.Timestamp(spec["oos_start"])
    res["is_oos"] = {"is": K.perf(b.loc[~oos, "net"]), "oos": K.perf(b.loc[oos, "net"])}
    # 單調性(各分位 long-only 淨報酬)
    res["quintile_mean_net"], res["mono"] = mono_of(spec, D)
    # 穩健性 / disclosure
    res["delayed"] = K.perf(bt(spec, D, entry_lag=D["entry_lag"] + 1)["net"])
    res["disclosure"] = {"fixed_weight_no_drift": K.perf(bt(spec, D, drift=False)["net"]),
                         "zero_cost": K.perf(b["gross"] + b["fund"])}
    comps = components_cross(spec, D)
    sign = np.sign(spec["direction"])
    res["components"] = {}
    for name, Z in comps.items():
        Zr = K.rank_xs(Z * sign, D["ok"], spec["min_n"])
        res["components"][name] = {"declared": int(spec["components"][name]), **ic(spec, D, Zr),
                                   **{f"net_{k}": v for k, v in K.perf(bt(spec, D, Zr)["net"]).items()
                                      if k in ("sharpe", "nw_t")}}
    # 控制變數(=Risk 的 book):自身 IC、適格性、殘差化、相關、邊際 Sharpe
    ctrl = builtin_controls(D, spec["controls"])
    risk = {"controls": {}}
    book = []
    for k, Z in ctrl.items():
        Zr = K.rank_xs(Z, D["ok"], spec["min_n"])
        own = ic(spec, D, Zr)
        cb = bt(spec, D, Zr)["net"]
        book.append(cb.rename(k))
        rho = K.xs_corr(D["SIG"], Zr, spec["min_n"])
        eligible = control_eligible(own.get("rank_ic", 0), s.get("rank_ic", 0), rho)
        risk["controls"][k] = {"own_ic": own.get("rank_ic"), "own_ic_nw_t": own.get("ic_nw_t"),
                               "own_net_sharpe": K.perf(cb).get("sharpe"), "xs_rho": rho,
                               "corr_net": float(b["net"].corr(cb)), "eligible_v24_4": eligible}
    if ctrl:
        el = [ctrl[k] for k, v in risk["controls"].items() if v["eligible_v24_4"]]
        if el:
            Zres = K.rank_xs(K.xs_resid(D["SIG"], el, spec["min_n"]), D["ok"], spec["min_n"])
            risk["resid_eligible_controls"] = {**K.perf(bt(spec, D, Zres)["net"]), **ic(spec, D, Zres)}
        bk = pd.concat(book, axis=1).mean(axis=1)
        risk["book_sharpe"] = K.perf(bk).get("sharpe")
        risk["blend_50_50_sharpe"] = K.perf(0.5 * bk + 0.5 * b["net"].reindex(bk.index)).get("sharpe")
        risk["marginal_sharpe"] = (risk["blend_50_50_sharpe"] or 0) - (risk["book_sharpe"] or 0)
    risk["breakeven_cost_bps"] = (float(b["gross"].mean() / (b["turn"].mean() / 1e4))
                                  if b["turn"].mean() else None)
    res["risk"] = risk
    res["rank_layer"] = rank_layer(spec, D, ctrl)
    return res


def mono_of(spec, D):
    """各分位 long-only 淨報酬均值與其對分位序的 Spearman。"""
    from scipy import stats
    qm = [float(bt(spec, D, which=i)["net"].mean()) for i in range(spec["q"])]
    return qm, float(stats.spearmanr(np.arange(spec["q"]), qm).correlation)


def rank_layer(spec, D, ctrl):
    """v2.5 排序層:IC 版 LOYO、訊號延遲 1 期的 IC、對全部控制的聯合 Fama-MacBeth。
    run 與 noise 共用,確保噪音通過率量的是同一個計算。"""
    ics = K.ic_series(D["SIG"], D["FWD"], spec["min_n"])
    iy = ics.index.year
    loyo_ic = {int(y): K.nw_t(ics[iy != y]) for y in sorted(set(iy))}
    rl = {"loyo_ic_nw_t": loyo_ic,
          "loyo_ic_min": float(np.nanmin(list(loyo_ic.values()))) if loyo_ic else None,
          "delayed_ic": ic(spec, D, D["SIG"].shift(1))}
    if ctrl:
        Zs = K.rank_xs(D["SIG"], D["ok"], spec["min_n"])
        cs = [K.rank_xs(Z, D["ok"], spec["min_n"]) for Z in ctrl.values()]
        coef = K.fm_coef(D["FWD"], Zs, cs, spec["min_n"])
        rl["fm_marginal"] = {"controls": list(ctrl), "n_days": int(len(coef)),
                             "mean_coef": float(coef.mean()) if len(coef) else None,
                             "nw_t": K.nw_t(coef) if len(coef) > 2 else None}
    return rl


def gate_defs(spec):
    """套用實測噪音通過率(若有)。回傳 [(key, desc, noise, role, measured)]。"""
    p = out_path(spec, "noise.json")
    meas = json.load(open(p))["noise_pass_rate"] if os.path.exists(p) else {}
    return [(k, d, meas.get(k, n), "veto" if (r == "count" and meas.get(k, 0) > 0.5) else r, k in meas)
            for k, d, n, r in GATES[spec["type"]]]


def summary_md(spec, res, gates, dfl):
    names = gate_defs(spec)
    lines = [f"# {spec['session']} — {spec['factor']}(Empiricist 套餐摘要)", "",
             f"spec sha256 `{spec['_sha'][:12]}` · module sha256 `{spec['_mod_sha'][:12]}` · "
             f"family `{spec['family']}` N(run 時,Arbiter 以 `ledger.py n` 為準)={dfl['N_family']} · Bonferroni t={dfl['bonferroni_t']:.3f} · "
             f"DSR 期望最大 Sharpe={dfl['dsr_expected_max']:.3f}", "",
             "| 閘門 | 條件 | 結果 | 計入 | 噪音通過率 |", "|---|---|---|---|---|"]
    ROLE = {"count": "是", "veto": "否(只能否決)", "disclose": "揭露(不計入、不否決)"}
    for key, desc, noise, role, measured in names:
        v = gates.get(key)
        mark = "—" if v is None else ("PASS" if v else "FAIL")
        lines.append(f"| {key} | {desc} | {mark} | {ROLE[role]} | "
                     f"{'' if noise is None else f'{noise:.1%}' + ('(實測)' if measured else '(名目)')} |")
    passed = sum(1 for k, _, _, r, _ in names if r == "count" and gates.get(k))
    total = sum(1 for k, _, _, r, _ in names if r == "count" and gates.get(k) is not None)
    vetoed = [k for k, _, _, r, _ in names if r in ("count", "veto") and gates.get(k) is False]
    lines += ["", f"**計入閘門通過 {passed}/{total}**"
              + (f" · 否決:{', '.join(vetoed)}" if vetoed else ""), ""]
    if spec["type"] == "cross":
        lines += ["> v2.5:cross 以排序層為正式判準;美元層閘門只揭露。**VALIDATE 代表排序層異象成立且對 book 有增量,"
                  "不代表可交易**——可變現性見下方揭露指標與 power_curve_20260924_report.md。", ""]
    f = lambda x: "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    if spec["type"] == "cross":
        m = res["main"]
        lines += ["| 指標 | 值 |", "|---|---|"]
        for k in ("rank_ic", "ic_ir", "ic_nw_t", "sharpe", "gross_sharpe", "nw_t", "max_drawdown",
                  "turn_mean", "cost_drag_ann", "funding_ann", "T_years"):
            lines.append(f"| {k} | {f(m.get(k))} |")
        lines += [f"| mono | {f(res['mono'])} |", f"| loyo_min | {f(res['loyo_min'])} |",
                  f"| delayed nw_t | {f(res['delayed'].get('nw_t'))} |",
                  f"| IS / OOS Sharpe | {f(res['is_oos']['is'].get('sharpe'))} / {f(res['is_oos']['oos'].get('sharpe'))} |", ""]
        gi = res["gate_ic"]
        lines.append(f"閘門 t(S2/D1)={f(gi.get('gate_t'))} = min(h1 NW t={f(gi.get('ic_nw_t'))}"
                     + (f", h{gi['h']} NW t={f(gi.get('h_ic_nw_t'))}, h{gi['h']} 非重疊 t={f(gi.get('h_nonoverlap_t'))}"
                        if gi["h"] > 1 else "") + ")")
        lines.append("非重疊 IC t: " + " · ".join(f"h{h}={f(v['nonoverlap_t'])}" for h, v in res["ic_horizons"].items()))
        if res["components"]:
            lines.append("成分: " + " · ".join(f"{k}(宣告{v['declared']:+d}) IC={f(v.get('rank_ic'))} t={f(v.get('ic_nw_t'))} 淨Sh={f(v.get('net_sharpe'))}"
                                             for k, v in res["components"].items()))
        r = res["risk"]
        if r.get("controls"):
            lines.append("控制/book: " + " · ".join(f"{k} IC={f(v['own_ic'])} XSρ={f(v.get('xs_rho'))} 淨報酬ρ={f(v['corr_net'])}{'' if v['eligible_v24_4'] else '(不適格)'}"
                                                   for k, v in r["controls"].items()))
            lines.append(f"殘差化(適格控制) 淨Sh={f(r.get('resid_eligible_controls', {}).get('sharpe'))} · "
                         f"邊際 Sharpe={f(r.get('marginal_sharpe'))} · 打平成本={f(r.get('breakeven_cost_bps'))}bps")
    else:
        lines += ["| 範圍 | 淨Sh | NW t | 非重疊t | 超額(主動)Sh | MaxDD | Mono | LOYO min | OOS Sh |", "|---|---|---|---|---|---|---|---|---|"]
        rows = {**{k: v for k, v in res["per"].items()}, **{k: res[k] for k in res if k.startswith("portfolio_")}}
        for k, v in rows.items():
            lines.append(f"| {k} | {f(v.get('sharpe'))} | {f(v.get('nw_t'))} | {f(v.get('t_nonoverlap'))} | "
                         f"{f(v['active'].get('sharpe'))} | {f(v.get('max_drawdown'))} | {f(v.get('mono'))} | "
                         f"{f(v.get('loyo_min'))} | {f(v.get('oos_sharpe'))} |")
    return "\n".join(lines) + "\n"


def cmd_run(spec):
    lk = out_path(spec, "lock.json")
    if not os.path.exists(lk) or not json.load(open(lk))["PASS"] or json.load(open(lk))["spec_sha256"] != spec["_sha"]:
        raise SystemExit("複製鎖未通過或 spec 已變更,不得執行")
    res = run_cross(spec) if spec["type"] == "cross" else run_directional(spec)
    rows = []
    if spec["type"] == "cross":
        m = res["main"]
        rows.append(ledger_row(spec, f"{spec['factor']} 主規格", "trial", "PENDING", preregistered=True,
                               net_sharpe=m.get("sharpe"), net_nw_t=m.get("nw_t"), gross_sharpe=m.get("gross_sharpe"),
                               rank_ic=m.get("rank_ic"), ic_ir=m.get("ic_ir"), ic_nw_t=m.get("ic_nw_t"),
                               max_drawdown=m.get("max_drawdown"), turn_mean=m.get("turn_mean"),
                               T_years=m.get("T_years"), mono=res["mono"]))
        for k, v in res["components"].items():
            rows.append(ledger_row(spec, f"{spec['factor']} 成分 {k}", "diag", "DIAG",
                                   rank_ic=v.get("rank_ic"), ic_nw_t=v.get("ic_nw_t"), net_sharpe=v.get("net_sharpe")))
        if "resid_eligible_controls" in res["risk"]:
            v = res["risk"]["resid_eligible_controls"]
            rows.append(ledger_row(spec, f"{spec['factor']} ⊥ 適格控制", "diag", "DIAG",
                                   rank_ic=v.get("rank_ic"), ic_nw_t=v.get("ic_nw_t"),
                                   net_sharpe=v.get("sharpe"), net_nw_t=v.get("nw_t")))
        rows.append(ledger_row(spec, f"{spec['factor']} 延遲進場", "gate", "DIAG",
                               net_sharpe=res["delayed"].get("sharpe"), net_nw_t=res["delayed"].get("nw_t")))
    else:
        per = res["per"] if len(spec["assets"]) > 1 else {}
        for k, v in {**per, **{k: res[k] for k in res if k.startswith("portfolio_")}}.items():
            main = k == f"portfolio_{spec['primary_tf']}"
            kind, verdict = (("trial", "PENDING") if main else ("trial", "DISCLOSURE") if k.startswith("portfolio_")
                             else ("diag", "DIAG"))
            rows.append(ledger_row(spec, f"{spec['factor']} {k}", kind, verdict,
                                   preregistered=main, net_sharpe=v.get("sharpe"), net_nw_t=v.get("nw_t"),
                                   gross_sharpe=v.get("gross_sharpe"), t_nonoverlap=v.get("t_nonoverlap"),
                                   excess_vs_benchmark=v["active"].get("sharpe"), max_drawdown=v.get("max_drawdown"),
                                   mono=v.get("mono"), rank_ic=v.get("rank_ic")))
    L.append(rows)
    N, _ = L.family_n(spec["family"])
    gates, dfl = (gates_cross if spec["type"] == "cross" else gates_dir)(spec, res, N)
    res.update({**stamp(spec), "gates": gates, "deflation": dfl, "gate_defs": gate_defs(spec)})
    K.dump(out_path(spec, "results.json"), res)
    md = summary_md(spec, res, gates, dfl)
    open(out_path(spec, "summary.md"), "w").write(md)
    print(md)


# ------------------------------------------------------------------ noise
def cmd_noise(spec, k=20, seed=0):
    """每日橫截面打亂(cross)/ 時序區塊打亂(directional)K 次,實測各閘門純噪音通過率。"""
    rng = np.random.default_rng(seed)
    hits = {}
    for i in range(k):
        if spec["type"] == "cross":
            D = load_cross(spec)
            S = D["SIG"].copy()
            vals = np.array(S.values, dtype=float)
            for r in range(vals.shape[0]):
                m = ~np.isnan(vals[r]); vals[r, m] = rng.permutation(vals[r, m])
            D["SIG"] = pd.DataFrame(vals, index=S.index, columns=S.columns)
            b = bt(spec, D); s = ic_gate(spec, D); p = K.perf(b["net"])
            g = {"S2_ic_t": s.get("gate_t", 0) >= 2, "S3_ic_ir": s.get("ic_ir", 0) >= 0.3,
                 "T2_net_t": p.get("nw_t", 0) >= 2, "T1_trade": p.get("sharpe", 0) >= 1.0,
                 "T3_maxdd": p.get("max_drawdown", -1) > -0.30}
            # v2.5 排序層計入閘門,與 run 共用同一計算
            rl = rank_layer(spec, D, builtin_controls(D, spec["controls"]))
            t0, td = s.get("ic_nw_t", 0) or 0, rl["delayed_ic"].get("ic_nw_t", 0) or 0
            fm = rl.get("fm_marginal")
            g.update({"S1_ic_mag": abs(s.get("rank_ic", 0)) > 0.02,
                      "S4_mono": (mono_of(spec, D)[1] or 0) >= 0.7,
                      "R1_loyo_ic": (rl["loyo_ic_min"] if rl["loyo_ic_min"] is not None else -9) >= 1.5,
                      "R2_delay_ic": bool(t0 > 0 and td >= 0.5 * t0),
                      **({"M1_marginal": (fm.get("nw_t") or 0) >= 2.0} if fm else {})})
        else:
            df = load_dir(spec, spec["assets"][0], spec["primary_tf"])
            sig = dir_series(spec, df, spec["primary_tf"])["sig"].values.copy()
            m = ~np.isnan(sig); sig[m] = rng.permutation(sig[m])
            s = dir_series(spec, df, spec["primary_tf"], sig=pd.Series(sig))
            p = K.perf(s["net"], PPY[spec["primary_tf"]])
            g = {"T4_net_t": p.get("nw_t", 0) >= 2, "T1_net": p.get("sharpe", 0) > 0.5,
                 "T2_excess": K.perf(s["net"] - s["bench_net"]).get("sharpe", 0) > 0,
                 "T3_maxdd": p.get("max_drawdown", -1) > -0.30}
        for kk, v in g.items():
            hits[kk] = hits.get(kk, 0) + int(bool(v))
    out = {**stamp(spec), "K": k, "noise_pass_rate": {kk: v / k for kk, v in hits.items()}}
    K.dump(out_path(spec, "noise.json"), out)
    print(json.dumps(out["noise_pass_rate"], ensure_ascii=False))


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    spec = load_spec(path)
    {"stage0": cmd_stage0, "lock": cmd_lock, "run": cmd_run,
     "noise": lambda s: cmd_noise(s, int(sys.argv[3]) if len(sys.argv) > 3 else 20)}[cmd](spec)


if __name__ == "__main__":
    main()
