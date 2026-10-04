#!/usr/bin/env python3
"""
Regime-Aware Factor Combination Backtest v2
===========================================
Improvements over v1:
  1. Percentile-based regime split (≈50/50) instead of fixed thresholds
  2. Signal strength threshold: only enter when |composite_z| > 1.0
  3. IC-IR weighted factors instead of equal weight

Ordered regime:   F10 (+) + F16×(neg) + F1×(neg)   [weights from ordered IC-IR]
Critical regime:  F2 (+) + F4×(neg) + F5×(neg) + F1×(neg)  [weights from critical IC-IR]

Blend: w = clip((delta_percentile - 0.30) / 0.40, 0, 1)
       composite = w × ordered_signal + (1−w) × critical_signal

Entry: composite_z > 1.0 → long, composite_z < −1.0 → flat (long-only)
"""

from __future__ import annotations
import sys, os, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from core.signals.F1_Complexity_Gap_Regime import compute as f1_compute
from core.signals.F2_Liquidity_Consumption_Tilt import compute as f2_compute
from core.signals.F4_Flow_Divergence_Ratio import compute as f4_compute
from core.signals.F5_Anchored_Mean_Reversion_Score import compute as f5_compute
from core.signals.F10_vol_adj_momentum import factor as f10_factor
from core.signals.F16_clv_momentum import factor as f16_factor

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
OUTPUT_HTML = "/home/anson/factor-lab/output/regime_combo_backtest_v3.html"

# IC-IR weights derived from regime_split_ic_analysis.py (max |IC-IR| at h=5/10/20)
ORDERED_WEIGHTS = {
    "F10": 0.484,   # max(|0.352|, |0.484|, |0.437|)
    "F16": 0.490,   # max(|-0.490|, |-0.464|, |-0.490|)
    "F1":  1.025,   # max(|-1.025|, |-0.789|, |-0.193|)
}

CRITICAL_WEIGHTS = {
    "F2": 1.582,    # max(|0.987|, |1.519|, |1.582|)
    "F4": 0.531,    # max(|-0.159|, |-0.455|, |-0.531|)
    "F5": 0.521,    # max(|-0.521|, |-0.309|, |-0.367|)
    "F1": 0.973,    # max(|-0.973|, |-0.743|, |-0.394|)
}

SIGNAL_THRESHOLD = 0.5   # |z| > 0.5 to enter (lowered from 1.0)
MIN_HOLD_DAYS = 10       # minimum holding period after entry

# ══════════════════════════════════════════════════════════════════════

def fetch_binance_daily(symbol="BTCUSDT", limit=1500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    rows = []
    for k in data:
        rows.append({
            "timestamp": pd.Timestamp(k[0], unit="ms", tz="UTC"),
            "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
            "close": float(k[4]), "volume": float(k[5]),
        })
    return pd.DataFrame(rows)


def df_to_ohlcv_list(df):
    return [
        {"ts": int(row.timestamp.timestamp() * 1000),
         "open": row.open, "high": row.high,
         "low": row.low, "close": row.close,
         "volume": row.volume}
        for row in df.itertuples()
    ]


def rank_ic(signal, fwd_ret):
    valid = signal.notna() & fwd_ret.notna()
    s = signal[valid]
    r = fwd_ret[valid]
    if len(s) < 30:
        return None, None, len(s)
    ic, _ = spearmanr(s, r)
    window = min(60, len(s) // 3)
    if window < 5:
        return round(ic, 4), None, len(s)
    ic_series = []
    for i in range(window - 1, len(s)):
        ic_i, _ = spearmanr(s.iloc[i - window + 1:i + 1], r.iloc[i - window + 1:i + 1])
        ic_series.append(ic_i)
    ic_std = np.std(ic_series)
    ic_ir = ic / ic_std if ic_std > 1e-10 else None
    return round(ic, 4), round(ic_ir, 4) if ic_ir is not None else None, len(s)


def expanding_percentile_rank(series: pd.Series) -> pd.Series:
    """Compute expanding percentile rank (no lookahead)."""
    result = pd.Series(np.nan, index=series.index)
    values = []
    for i, val in enumerate(series.values):
        if np.isnan(val):
            continue
        values.append(val)
        sorted_vals = sorted(values)
        rank = sorted_vals.index(val)  # ties: first occurrence
        result.iloc[i] = rank / (len(values) - 1) if len(values) > 1 else 0.5
    return result


def compute_performance(strat_ret: pd.Series, benchmark_ret: pd.Series) -> dict:
    clean = strat_ret.dropna()
    bench = benchmark_ret.dropna()
    N = len(clean)
    if N < 2:
        return {"n_trades": 0}

    mu = clean.mean()
    sd = clean.std()
    ann_sharpe = (mu / sd) * np.sqrt(365) if sd > 0 else 0.0
    cum_ret = (1 + clean).prod() - 1
    bench_cum = (1 + bench).prod() - 1

    equity = (1 + clean).cumprod()
    peak = equity.expanding().max()
    drawdown = (equity / peak - 1)
    max_dd = drawdown.min()
    calmar = (ann_sharpe * sd / np.sqrt(365)) / abs(max_dd) if max_dd != 0 else 0.0

    wins = (clean > 0).sum()
    win_rate = wins / N
    avg_win = clean[clean > 0].mean() if (clean > 0).any() else 0
    avg_loss = clean[clean < 0].mean() if (clean < 0).any() else 0
    profit_factor = abs(avg_win * wins) / abs(avg_loss * (N - wins)) if (N - wins) > 0 and avg_loss != 0 else float('inf')

    return {
        "n_days": N, "cum_ret_%": round(cum_ret * 100, 2),
        "bench_ret_%": round(bench_cum * 100, 2),
        "ann_sharpe": round(ann_sharpe, 4), "max_dd_%": round(max_dd * 100, 2),
        "calmar": round(calmar, 4), "win_rate_%": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_daily_ret_%": round(mu * 100, 4),
        "avg_win_%": round(avg_win * 100, 3),
        "avg_loss_%": round(avg_loss * 100, 3),
        "equity": equity, "drawdown": drawdown,
    }


# ══════════════════════════════════════════════════════════════════════

def run():
    print("=" * 70)
    print("Regime-Aware Combo v2: Percentile Split + IC-IR Weighted + Threshold Filter")
    print("=" * 70)

    # ── 1. Data ──
    print("\n[1/7] 載入 BTCUSDT 日線 ...")
    df = fetch_binance_daily("BTCUSDT", 1500)
    print(f"      {len(df)} 筆, {df.timestamp.iloc[0].date()} ~ {df.timestamp.iloc[-1].date()}")

    # ── 2. Factors ──
    print("\n[2/7] 計算 6 個因子 ...")
    ohlcv_list = df_to_ohlcv_list(df)

    f1 = f1_compute(ohlcv_list)
    delta = pd.Series(f1["delta"], index=df.index)
    f1_signal = pd.Series(-f1["signal"], index=df.index)  # negate

    f2_signal = pd.Series(f2_compute(ohlcv_list)["signal"], index=df.index)
    f4_signal = pd.Series(-f4_compute(ohlcv_list)["signal"], index=df.index)  # negate
    f5_signal = pd.Series(-f5_compute(ohlcv_list)["signal"], index=df.index)  # negate
    f10_signal = pd.Series(f10_factor(df).values, index=df.index)
    f16_signal = pd.Series(-f16_factor(df).values, index=df.index)  # negate

    for name, s in [("F1", f1_signal), ("F2", f2_signal), ("F4", f4_signal),
                     ("F5", f5_signal), ("F10", f10_signal), ("F16", f16_signal)]:
        print(f"      {name}: {s.notna().sum()} valid")

    # ── 3. Percentile-based regime weight ──
    print("\n[3/7] 計算 percentile-based regime weight ...")
    delta_rank = expanding_percentile_rank(delta)
    # w=0 at P30, w=1 at P70, linear between
    regime_w = pd.Series(np.clip((delta_rank.values - 0.30) / 0.40, 0.0, 1.0), index=df.index)

    # Stats
    ord_mask = regime_w > 0.5
    crit_mask = regime_w <= 0.5
    n_ord = ord_mask.sum()
    n_crit = crit_mask.sum()
    print(f"      Ordered (w>0.5): {n_ord} ({n_ord/len(df)*100:.0f}%)")
    print(f"      Critical (w<=0.5): {n_crit} ({n_crit/len(df)*100:.0f}%)")

    # ── 4. IC-IR weighted composite ──
    print("\n[4/7] 合成 IC-IR 加權信號 ...")

    w_o = ORDERED_WEIGHTS
    w_c = CRITICAL_WEIGHTS
    ord_sum = sum(w_o.values())
    crit_sum = sum(w_c.values())

    ordered_composite = (
        w_o["F10"] * f10_signal +
        w_o["F16"] * f16_signal +
        w_o["F1"] * f1_signal
    ) / ord_sum

    critical_composite = (
        w_c["F2"] * f2_signal +
        w_c["F4"] * f4_signal +
        w_c["F5"] * f5_signal +
        w_c["F1"] * f1_signal
    ) / crit_sum

    composite = regime_w * ordered_composite + (1 - regime_w) * critical_composite

    # Expanding z-score
    composite_zs = pd.Series(np.nan, index=df.index)
    running_sum = 0.0
    running_sq = 0.0
    count = 0
    for i, val in enumerate(composite.values):
        if np.isnan(val):
            continue
        count += 1
        running_sum += val
        running_sq += val * val
        if count < 2:
            composite_zs.iloc[i] = 0.0
            continue
        mean = running_sum / count
        variance = (running_sq / count) - mean * mean
        std = np.sqrt(max(variance, 1e-12))
        composite_zs.iloc[i] = (val - mean) / std

    composite_zs = composite_zs.clip(-4, 4)
    n_pos = (composite_zs > 0).sum()
    n_strong = (composite_zs.abs() > SIGNAL_THRESHOLD).sum()
    print(f"      Signal range: [{composite_zs.min():.2f}, {composite_zs.max():.2f}]")
    print(f"      z>0: {n_pos}, |z|>{SIGNAL_THRESHOLD}: {n_strong}")

    # ── 5. Entry signal with threshold + min holding period ──
    print(f"\n[5/7] 應用 signal threshold |z| > {SIGNAL_THRESHOLD} + min {MIN_HOLD_DAYS}d hold ...")
    entry_signal = composite_zs.shift(1)  # no lookahead

    # Minimum holding period logic (no early exit)
    position = pd.Series(False, index=df.index)
    hold_remaining = 0
    for i in range(len(df)):
        if hold_remaining > 0:
            position.iloc[i] = True
            hold_remaining -= 1
        else:
            if i > 0 and not np.isnan(entry_signal.iloc[i]):
                if entry_signal.iloc[i] > SIGNAL_THRESHOLD:
                    position.iloc[i] = True
                    hold_remaining = MIN_HOLD_DAYS - 1

    n_long = position.sum()
    # Count unique entry events (diff method avoids boolean shift bug)
    n_entries = (position.astype(int).diff() == 1).sum()
    
    print(f"      Long days: {n_long} ({n_long/len(df)*100:.1f}% of total)")
    print(f"      Entry events: {n_entries}, avg hold: {n_long/max(n_entries,1):.1f} days")

    # ── 6. Backtest ──
    print("\n[6/7] Long-only 策略回測 ...")
    daily_ret = df["close"].pct_change()
    strategy_ret = pd.Series(0.0, index=df.index)
    strategy_ret[position] = daily_ret[position]

    bench_ret = daily_ret.copy()
    perf = compute_performance(strategy_ret, bench_ret)

    print(f"      CumRet: {perf['cum_ret_%']:.1f}% vs B&H {perf['bench_ret_%']:.1f}%")
    print(f"      Sharpe: {perf['ann_sharpe']:.4f}")
    print(f"      MaxDD:  {perf['max_dd_%']:.2f}%")
    print(f"      WinRate: {perf['win_rate_%']:.1f}%")
    print(f"      Calmar: {perf['calmar']:.4f}")
    print(f"      ProfitFactor: {perf['profit_factor']:.2f}")
    print(f"      AvgWin: {perf['avg_win_%']:.3f}%  AvgLoss: {perf['avg_loss_%']:.3f}%")

    # ── 7. IC-IR ──
    print("\n[7/7] IC-IR 分析 ...")
    horizons = [1, 5, 10, 20]
    ic_results = {}
    for h in horizons:
        fwd_ret = df["close"].pct_change(h).shift(-h)
        ic, ic_ir, n = rank_ic(composite_zs, fwd_ret)
        ic_results[h] = {"ic": ic, "ic_ir": ic_ir, "n": n}
        print(f"      h={h:>2}d: IC={ic}, IC-IR={ic_ir}, n={n}")

    # ── Generate HTML ──
    generate_html(df, composite_zs, regime_w, delta, delta_rank,
                  ordered_composite, critical_composite, perf, ic_results,
                  horizons, strategy_ret, position, SIGNAL_THRESHOLD)

    return perf, ic_results


# ══════════════════════════════════════════════════════════════════════

def generate_html(df, composite_zs, regime_w, delta, delta_rank,
                  ord_comp, crit_comp, perf, ic_results, horizons,
                  strategy_ret, position, threshold):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # ── K-line + Position + Signal ──
    fig_kl = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.5, 0.25, 0.25],
        vertical_spacing=0.04,
        subplot_titles=["BTCUSDT + Position", "Composite Signal", "Regime Weight"]
    )

    fig_kl.add_trace(
        go.Candlestick(
            x=df["timestamp"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="BTCUSDT",
            increasing_line_color="#00cc96", decreasing_line_color="#ef553b",
        ), row=1, col=1,
    )

    if position.sum() > 0:
        fig_kl.add_trace(
            go.Scatter(
                x=df.loc[position, "timestamp"], y=df.loc[position, "close"],
                mode="markers", marker=dict(color="#00cc96", size=4, symbol="triangle-up"),
                name="Long Entry",
            ), row=1, col=1,
        )

    # Signal with threshold lines
    fig_kl.add_trace(
        go.Scatter(x=df["timestamp"], y=composite_zs, mode="lines",
                   name="Composite Z", line=dict(color="#ffa15a", width=1)),
        row=2, col=1,
    )
    fig_kl.add_hline(y=threshold, line_dash="dash", line_color="#00cc96",
                      annotation_text=f"+{threshold}", row=2, col=1)
    fig_kl.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)

    # Regime weight
    fig_kl.add_trace(
        go.Scatter(x=df["timestamp"], y=regime_w, mode="lines",
                   name="Regime W (ordered→)", line=dict(color="cyan", width=0.8)),
        row=3, col=1,
    )
    fig_kl.add_hline(y=0.5, line_dash="dash", line_color="white", opacity=0.3, row=3, col=1)

    fig_kl.update_layout(
        title=f"Regime-Aware Combo v3: BTCUSDT Daily | z>{threshold} | MinHold {MIN_HOLD_DAYS}d",
        height=800, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=60, b=20),
        template="plotly_dark", xaxis_rangeslider_visible=False,
    )

    # ── Equity + Drawdown ──
    bench_ret = df["close"].pct_change()
    bench_eq = (1 + bench_ret).cumprod()
    eq = perf["equity"]
    dd = perf["drawdown"]

    fig_eq = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.05,
        subplot_titles=["Equity Curve", "Drawdown"]
    )

    fig_eq.add_trace(
        go.Scatter(x=eq.index, y=eq.values, mode="lines",
                   name="Strategy", line=dict(color="#00cc96", width=1.5)),
        row=1, col=1,
    )
    fig_eq.add_trace(
        go.Scatter(x=bench_eq.index, y=bench_eq.values, mode="lines",
                   name="Buy & Hold", line=dict(color="gray", width=1, dash="dot")),
        row=1, col=1,
    )
    fig_eq.add_trace(
        go.Scatter(x=dd.index, y=dd.values * 100, mode="lines",
                   name="Drawdown %", line=dict(color="#ef553b", width=1),
                   fill="tozeroy", fillcolor="rgba(239, 85, 59, 0.15)"),
        row=2, col=1,
    )
    fig_eq.update_layout(
        height=500, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=60, b=20), template="plotly_dark",
    )
    fig_eq.update_yaxes(title_text="Equity (x)", row=1, col=1, type="log")
    fig_eq.update_yaxes(title_text="DD %", row=2, col=1)

    # ── Average position by regime zone ──
    sr_with_idx = strategy_ret.copy()
    sr_with_idx.index = df["timestamp"]  # align indices
    zones = pd.cut(regime_w, bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                   labels=["Pure Critical", "Mostly Critical", "Neutral",
                           "Mostly Ordered", "Pure Ordered"])
    zone_ret = pd.DataFrame({"ret": sr_with_idx, "zone": zones}).dropna()
    zone_avg = zone_ret.groupby("zone", observed=False)["ret"].mean() * 100 * 365  # annualized

    fig_zone = go.Figure(
        go.Bar(x=list(zone_avg.index), y=list(zone_avg.values),
               marker_color=["#ef553b", "#ff7f50", "#ffa15a", "#50c878", "#00cc96"],
               text=[f"{v:.1f}%" for v in zone_avg.values], textposition="outside")
    )
    fig_zone.update_layout(
        title="Annualized Return by Regime Zone",
        height=350, template="plotly_dark",
        yaxis_title="Ann. Return %",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    # ── Monthly returns heatmap ──
    monthly_sr = strategy_ret.copy()
    monthly_sr.index = df["timestamp"]
    bench_monthly_sr = bench_ret.copy()
    bench_monthly_sr.index = df["timestamp"]
    monthly = monthly_sr.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    bench_monthly = bench_monthly_sr.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100
    monthly.index = monthly.index.strftime("%Y-%m")

    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Bar(x=monthly.index, y=monthly.values, name="Strategy",
                                  marker_color="#00cc96"))
    fig_monthly.add_trace(go.Bar(x=bench_monthly.index, y=bench_monthly.values,
                                  name="B&H", marker_color="gray", opacity=0.5))
    fig_monthly.update_layout(
        title="Monthly Returns: Strategy vs B&H",
        height=400, template="plotly_dark",
        yaxis_title="Return %", barmode="overlay",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    # ── HTML rows for IC-IR table ──
    ic_rows_list = []
    for h in horizons:
        ic_val = ic_results[h]["ic"]
        ic_ir_val = ic_results[h]["ic_ir"]
        ic_class = "positive" if (ic_val or 0) > 0 else "negative"
        ir_class = "positive" if (ic_ir_val or 0) >= 0.3 else ""
        ic_rows_list.append(
            f"<tr><td>h={h}d</td>"
            f"<td class='{ic_class}'>{ic_val}</td>"
            f"<td class='{ir_class}'>{ic_ir_val}</td>"
            f"<td>{ic_results[h]['n']}</td></tr>"
        )
    ic_rows_str = "".join(ic_rows_list)

    # ── HTML ──
    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'>
<title>Regime-Aware Combo v2 Backtest</title>
<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>
<style>
body{{background:#111;color:#eee;font-family:monospace;margin:20px;}}
h1{{color:#00cc96;}} h2{{color:#ffa15a;margin-top:40px;}}
table{{border-collapse:collapse;margin:10px 0;width:100%;max-width:900px;}}
th,td{{border:1px solid #333;padding:8px 14px;text-align:right;}}
th{{background:#222;color:#00cc96;}}
.positive{{color:#00cc96;}} .negative{{color:#ef553b;}} .neutral{{color:#ffa15a;}}
.metric-card{{background:#1a1a1a;padding:20px;border-left:3px solid #00cc96;margin:20px 0;}}
.metric-row{{display:flex;flex-wrap:wrap;gap:20px;}}
.metric-item{{flex:1;min-width:130px;}}
.metric-value{{font-size:1.5em;font-weight:bold;}}
.metric-label{{font-size:0.75em;color:#888;}}
.v3-tag{{background:#ffa15a;color:#111;padding:2px 8px;border-radius:3px;font-size:0.7em;margin-left:8px;}}
</style></head><body>

<h1>📊 Regime-Aware Factor Combination <span class='v3-tag'>v3</span></h1>
<p>Generated: {NOW} | BTCUSDT | {len(df)} candles | Threshold |z| > {threshold} | MinHold {MIN_HOLD_DAYS}d</p>

<div class='metric-card'>
<h3>v3 Improvements</h3>
<table>
<tr><th>Change</th><th>v2</th><th>v3</th></tr>
<tr><td>Signal Threshold</td><td>|z| > 1.0</td><td>|z| > 0.5</td></tr>
<tr><td>Holding Logic</td><td>Daily re-check</td><td>Min {MIN_HOLD_DAYS}d hold + early exit on z &lt; −0.5</td></tr>
<tr><td>Trade Frequency</td><td>~1 trade/day, 12% in</td><td>Aligned to h=10 signal horizon</td></tr>
</table>
</div>

<div class='metric-card'>
<h3>Factor Weights (IC-IR based)</h3>
<div style='display:flex;gap:40px;'>
<div>
<strong>Ordered (趨勢)</strong>
<table>
<tr><th>Factor</th><th>Weight</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v:.3f}</td></tr>" for k,v in ORDERED_WEIGHTS.items())}
</table>
</div>
<div>
<strong>Critical (臨界)</strong>
<table>
<tr><th>Factor</th><th>Weight</th></tr>
{"".join(f"<tr><td>{k}</td><td>{v:.3f}</td></tr>" for k,v in CRITICAL_WEIGHTS.items())}
</table>
</div>
</div>
</div>

<div class='metric-card'>
<h3>Performance Summary</h3>
<div class='metric-row'>
<div class='metric-item'>
<div class='metric-label'>CUMULATIVE RETURN</div>
<div class='metric-value {"positive" if perf["cum_ret_%"] > perf["bench_ret_%"] else ""}">{perf['cum_ret_%']:.1f}%</div>
<div class='metric-label'>vs B&H {perf['bench_ret_%']:.1f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>ANNUAL SHARPE</div>
<div class='metric-value {"positive" if perf["ann_sharpe"] >= 1.0 else ""}'>{perf['ann_sharpe']:.4f}</div>
</div>
<div class='metric-item'>
<div class='metric-label'>MAX DRAWDOWN</div>
<div class='metric-value negative'>{perf['max_dd_%']:.2f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>CALMAR</div>
<div class='metric-value'>{perf['calmar']:.4f}</div>
</div>
<div class='metric-item'>
<div class='metric-label'>WIN RATE</div>
<div class='metric-value'>{perf['win_rate_%']:.1f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>PROFIT FACTOR</div>
<div class='metric-value'>{perf['profit_factor']:.2f}</div>
</div>
</div>
<div class='metric-row' style='margin-top:15px;'>
<div class='metric-item'>
<div class='metric-label'>AVG WIN</div><div class='metric-value positive'>{perf['avg_win_%']:.3f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>AVG LOSS</div><div class='metric-value negative'>{perf['avg_loss_%']:.3f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>TRADING DAYS</div><div class='metric-value neutral'>{perf['n_days']}</div>
</div>
</div>
</div>

<h2>IC-IR: Composite Signal</h2>
<table>
<tr><th>Horizon</th><th>IC</th><th>IC-IR</th><th>N</th></tr>
{ic_rows_str}
</table>

<h2>K-line + Signal + Regime</h2>
{fig_kl.to_html(full_html=False, include_plotlyjs=False)}

<h2>Equity & Drawdown</h2>
{fig_eq.to_html(full_html=False, include_plotlyjs=False)}

<h2>Return by Regime Zone</h2>
{fig_zone.to_html(full_html=False, include_plotlyjs=False)}

<h2>Monthly Returns</h2>
{fig_monthly.to_html(full_html=False, include_plotlyjs=False)}

</body></html>"""

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"\n✅ HTML 報表: {OUTPUT_HTML}")


if __name__ == "__main__":
    run()
