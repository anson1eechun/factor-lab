#!/usr/bin/env python3
"""
Regime-Aware Factor Combination Backtest
=========================================
二元加權組合策略:
  Ordered regime  (delta >= 0.05): F10 (+) + F16×(−1) + F1×(−1)
  Critical regime (delta <  0.05): F2  (+) + F4×(−1) + F5×(−1) + F1×(−1)

連續權重內插: w = clip((delta - 0.02) / 0.03, 0, 1)
  composite = w × ordered_signal + (1−w) × critical_signal

輸出:
  - Long-only 策略權益曲線 (composite > 0 做多, < 0 空倉)
  - IC-IR × 4 horizons
  - 互動 HTML 報表 (K線 + 進出場 + 權益曲線 + 回撤曲線)
"""

from __future__ import annotations
import sys, os, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

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
OUTPUT_HTML = "/home/anson/factor-lab/output/regime_combo_backtest.html"


# ══════════════════════════════════════════════════════════════════════
# Data
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


# ══════════════════════════════════════════════════════════════════════
# Metrics
# ══════════════════════════════════════════════════════════════════════

def rank_ic(signal, fwd_ret):
    """Spearman rank correlation with IC-IR."""
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


def compute_performance(strat_ret: pd.Series, benchmark_ret: pd.Series) -> dict:
    """Compute standard performance metrics."""
    clean = strat_ret.dropna()
    bench = benchmark_ret.dropna()
    N = len(clean)
    if N < 2:
        return {"n_trades": 0}

    # Annualized Sharpe (assume daily, ~365 trading days)
    mu = clean.mean()
    sd = clean.std()
    ann_sharpe = (mu / sd) * np.sqrt(365) if sd > 0 else 0.0

    # Cumulative returns
    cum_ret = (1 + clean).prod() - 1
    bench_cum = (1 + bench).prod() - 1

    # Max drawdown
    equity = (1 + clean).cumprod()
    peak = equity.expanding().max()
    drawdown = (equity / peak - 1)
    max_dd = drawdown.min()

    # Win rate
    wins = (clean > 0).sum()
    win_rate = wins / N

    # Calmar ratio (annual return / abs(max_dd))
    calmar = (ann_sharpe * sd / np.sqrt(365)) / abs(max_dd) if max_dd != 0 else 0.0

    # Avg win / avg loss
    avg_win = clean[clean > 0].mean() if (clean > 0).any() else 0
    avg_loss = clean[clean < 0].mean() if (clean < 0).any() else 0
    profit_factor = abs(avg_win * wins) / abs(avg_loss * (N - wins)) if (N - wins) > 0 and avg_loss != 0 else float('inf')

    return {
        "n_days": N,
        "cum_ret_%": round(cum_ret * 100, 2),
        "bench_ret_%": round(bench_cum * 100, 2),
        "ann_sharpe": round(ann_sharpe, 4),
        "max_dd_%": round(max_dd * 100, 2),
        "calmar": round(calmar, 4),
        "win_rate_%": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_daily_ret_%": round(mu * 100, 4),
        "avg_win_%": round(avg_win * 100, 3),
        "avg_loss_%": round(avg_loss * 100, 3),
        "equity": equity,
        "drawdown": drawdown,
    }


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def run():
    print("=" * 70)
    print("Regime-Aware Combo Backtest: Ordered(CG>0.05) vs Critical(CG<0.05)")
    print("=" * 70)

    # ── 1. Data ──
    print("\n[1/6] 載入 BTCUSDT 日線 ...")
    df = fetch_binance_daily("BTCUSDT", 1500)
    print(f"      {len(df)} 筆, {df.timestamp.iloc[0].date()} ~ {df.timestamp.iloc[-1].date()}")

    # ── 2. Factors ──
    print("\n[2/6] 計算 6 個因子 ...")
    ohlcv_list = df_to_ohlcv_list(df)

    # F1: regime indicator
    f1 = f1_compute(ohlcv_list)
    delta = pd.Series(f1["delta"], index=df.index)
    f1_signal = pd.Series(-f1["signal"], index=df.index)  # negate per validated direction
    print(f"      F1 ComplexityGap: {f1_signal.notna().sum()} valid")

    # Ordered regime factors
    f2_raw = f2_compute(ohlcv_list)
    f2_signal = pd.Series(f2_raw["signal"], index=df.index)
    print(f"      F2 VolWeightedTilt: {f2_signal.notna().sum()} valid")

    f4_raw = f4_compute(ohlcv_list)
    f4_signal = pd.Series(-f4_raw["signal"], index=df.index)  # negate: ordered IC-IR ≈ 0, critical IC-IR negative
    print(f"      F4 FlowDivergence (negated): {f4_signal.notna().sum()} valid")

    f5_raw = f5_compute(ohlcv_list)
    f5_signal = pd.Series(-f5_raw["signal"], index=df.index)  # negate: IC-IR negative in critical
    print(f"      F5 AMRS (negated): {f5_signal.notna().sum()} valid")

    f10_signal = pd.Series(f10_factor(df).values, index=df.index)
    print(f"      F10 VolAdjMom: {f10_signal.notna().sum()} valid")

    f16_signal = pd.Series(-f16_factor(df).values, index=df.index)  # negate: IC-IR negative
    print(f"      F16 CLVMom (negated): {f16_signal.notna().sum()} valid")

    # ── 3. Regime weight ──
    print("\n[3/6] 計算 regime weight (delta-based continuous blend) ...")
    # w=0 純 critical, w=1 純 ordered, linear interpolation in [0.02, 0.05]
    regime_w = pd.Series(np.clip((delta.values - 0.02) / 0.03, 0.0, 1.0), index=df.index)
    n_ord = (regime_w > 0.5).sum()
    n_crit = (regime_w <= 0.5).sum()
    print(f"      Ordered days (w>0.5): {n_ord}, Critical days (w<=0.5): {n_crit}")

    # ── 4. Composite signal ──
    print("\n[4/6] 合成二元加權信號 ...")
    # Ordered composite: avg(F10 + F16_neg + F1_neg)
    ordered_composite = (f10_signal + f16_signal + f1_signal) / 3.0

    # Critical composite: avg(F2 + F4_neg + F5_neg + F1_neg)
    critical_composite = (f2_signal + f4_signal + f5_signal + f1_signal) / 4.0

    # Blend
    composite = regime_w * ordered_composite + (1 - regime_w) * critical_composite

    # Final z-score normalization (expanding window, no lookahead)
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
    print(f"      Signal range: [{composite_zs.min():.2f}, {composite_zs.max():.2f}], "
          f"pos: {(composite_zs > 0).sum()}, neg: {(composite_zs < 0).sum()}")

    # ── 5. Backtest ──
    print("\n[5/6] Long-only 策略回測 ...")
    # Long-only: signal > 0 → hold, signal <= 0 → flat
    daily_ret = df["close"].pct_change()
    strategy_ret = pd.Series(0.0, index=df.index)
    position = composite_zs.shift(1) > 0  # enter next day, no lookahead
    strategy_ret[position] = daily_ret[position]

    # Benchmark: buy & hold
    bench_ret = daily_ret.copy()

    perf = compute_performance(strategy_ret, bench_ret)
    print(f"      CumRet: {perf['cum_ret_%']:.1f}% vs B&H {perf['bench_ret_%']:.1f}%")
    print(f"      Sharpe: {perf['ann_sharpe']:.4f}")
    print(f"      MaxDD:  {perf['max_dd_%']:.2f}%")
    print(f"      WinRate: {perf['win_rate_%']:.1f}%")
    print(f"      Calmar: {perf['calmar']:.4f}")

    # ── 6. IC-IR ──
    print("\n[6/6] IC-IR 分析 ...")
    horizons = [1, 5, 10, 20]
    ic_results = {}
    for h in horizons:
        fwd_ret = df["close"].pct_change(h).shift(-h)
        ic, ic_ir, n = rank_ic(composite_zs, fwd_ret)
        ic_results[h] = {"ic": ic, "ic_ir": ic_ir, "n": n}
        print(f"      h={h:>2}d: IC={ic}, IC-IR={ic_ir}, n={n}")

    # ── Generate HTML ──
    generate_html(df, composite_zs, regime_w, delta, ordered_composite,
                  critical_composite, perf, ic_results, horizons, strategy_ret)

    return perf, ic_results


# ══════════════════════════════════════════════════════════════════════
# HTML Report
# ══════════════════════════════════════════════════════════════════════

def generate_html(df, composite_zs, regime_w, delta, ord_comp, crit_comp,
                  perf, ic_results, horizons, strategy_ret):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # ── K-line + signal ──
    fig_kl = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.05,
        subplot_titles=["BTCUSDT K-line + Position", "Composite Signal & Regime Weight"]
    )

    # Candlestick
    fig_kl.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="BTCUSDT",
            increasing_line_color="#00cc96",
            decreasing_line_color="#ef553b",
        ),
        row=1, col=1,
    )

    # Position markers (scatter on close when long)
    pos_mask = composite_zs.shift(1) > 0
    pos_mask = pos_mask & pos_mask.notna()
    if pos_mask.sum() > 0:
        fig_kl.add_trace(
            go.Scatter(
                x=df.loc[pos_mask, "timestamp"],
                y=df.loc[pos_mask, "close"],
                mode="markers",
                marker=dict(color="#00cc96", size=3, symbol="triangle-up"),
                name="Long",
            ),
            row=1, col=1,
        )

    # Signal
    fig_kl.add_trace(
        go.Scatter(
            x=df["timestamp"], y=composite_zs,
            mode="lines", name="Composite Z",
            line=dict(color="#ffa15a", width=1),
        ),
        row=2, col=1,
    )

    # Regime weight
    fig_kl.add_trace(
        go.Scatter(
            x=df["timestamp"], y=regime_w,
            mode="lines", name="Regime W",
            line=dict(color="cyan", width=0.8, dash="dot"),
        ),
        row=2, col=1,
    )

    # Zero line
    fig_kl.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)

    fig_kl.update_layout(
        title="Regime-Aware Combo Strategy: BTCUSDT Daily",
        height=700,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=60, b=20),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
    )
    fig_kl.update_yaxes(title_text="Price (USDT)", row=1, col=1)
    fig_kl.update_yaxes(title_text="Z-score / Weight", row=2, col=1)

    # ── Equity + Drawdown ──
    eq = perf["equity"]
    dd = perf["drawdown"]

    # Benchmark equity
    bench_ret = df["close"].pct_change()
    bench_eq = (1 + bench_ret).cumprod()

    fig_eq = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.05,
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
        height=500,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=60, b=20),
        template="plotly_dark",
    )
    fig_eq.update_yaxes(title_text="Equity (x)", row=1, col=1, type="log")
    fig_eq.update_yaxes(title_text="DD %", row=2, col=1)

    # ── IC-IR bar chart ──
    fig_ic = go.Figure()
    ic_vals = [ic_results[h]["ic_ir"] or 0 for h in horizons]
    colors = ["#00cc96" if v >= 0.3 else ("#ef553b" if v < 0 else "#ffa15a") for v in ic_vals]
    fig_ic.add_trace(go.Bar(
        x=[f"h={h}" for h in horizons],
        y=ic_vals,
        marker_color=colors,
        text=[f"{v:+.3f}" for v in ic_vals],
        textposition="outside",
    ))
    fig_ic.add_hline(y=0.3, line_dash="dash", line_color="white", opacity=0.5,
                      annotation_text="IC-IR ≥ 0.3")
    fig_ic.update_layout(
        title="Composite Signal IC-IR by Horizon",
        height=350,
        template="plotly_dark",
        yaxis_title="IC-IR",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    # ── HTML assembly ──
    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'>
<title>Regime-Aware Combo Backtest</title>
<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>
<style>
body{{background:#111;color:#eee;font-family:monospace;margin:20px;}}
h1{{color:#00cc96;}}
h2{{color:#ffa15a;margin-top:40px;}}
table{{border-collapse:collapse;margin:10px 0;width:100%;max-width:800px;}}
th,td{{border:1px solid #333;padding:8px 14px;text-align:right;}}
th{{background:#222;color:#00cc96;}}
.positive{{color:#00cc96;}}
.negative{{color:#ef553b;}}
.metric-card{{background:#1a1a1a;padding:20px;border-left:3px solid #00cc96;margin:20px 0;}}
.metric-row{{display:flex;flex-wrap:wrap;gap:20px;}}
.metric-item{{flex:1;min-width:120px;}}
.metric-value{{font-size:1.4em;font-weight:bold;}}
.metric-label{{font-size:0.75em;color:#888;}}
</style></head><body>

<h1>📊 Regime-Aware Factor Combination — Backtest Report</h1>
<p>Generated: {NOW} | Symbol: BTCUSDT | {len(df)} daily candles | Strategy: Long-only (composite > 0)</p>

<div class='metric-card'>
<h3>Performance Summary</h3>
<div class='metric-row'>
<div class='metric-item'>
<div class='metric-label'>CUMULATIVE RETURN</div>
<div class='metric-value positive'>{perf['cum_ret_%']:.1f}%</div>
<div class='metric-label'>vs B&H {perf['bench_ret_%']:.1f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>ANNUAL SHARPE</div>
<div class='metric-value {'positive' if perf['ann_sharpe'] >= 1.0 else ''}">{perf['ann_sharpe']:.4f}</div>
</div>
<div class='metric-item'>
<div class='metric-label'>MAX DRAWDOWN</div>
<div class='metric-value negative'>{perf['max_dd_%']:.2f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>CALMAR RATIO</div>
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
<div class='metric-label'>AVG WIN</div>
<div class='metric-value positive'>{perf['avg_win_%']:.3f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>AVG LOSS</div>
<div class='metric-value negative'>{perf['avg_loss_%']:.3f}%</div>
</div>
<div class='metric-item'>
<div class='metric-label'>TRADING DAYS</div>
<div class='metric-value' style='color:#ffa15a;'>{perf['n_days']}</div>
</div>
</div>
</div>

<h2>Composite Strategy Design</h2>
<table>
<tr><th>Regime</th><th>Condition</th><th>Factors</th><th>Weight</th></tr>
<tr><td>Ordered (趨勢)</td><td>delta ≥ 0.05</td><td>F10 (+) + F16×(−1) + F1×(−1)</td><td>avg 1/3 each</td></tr>
<tr><td>Critical (臨界)</td><td>delta < 0.05</td><td>F2 (+) + F4×(−1) + F5×(−1) + F1×(−1)</td><td>avg 1/4 each</td></tr>
<tr><td colspan="3">Blend</td><td>w = clip((delta-0.02)/0.03, 0, 1)</td></tr>
</table>

<h2>IC-IR Analysis</h2>
<table>
<tr><th>Horizon</th><th>Rank-IC</th><th>IC-IR</th><th>N</th></tr>
{"".join(f"<tr><td>h={h}d</td><td class='{'positive' if (ic_results[h]['ic'] or 0)>0 else 'negative'}'>{ic_results[h]['ic']}</td><td class='{'positive' if (ic_results[h]['ic_ir'] or 0)>=0.3 else ''}'>{ic_results[h]['ic_ir']}</td><td>{ic_results[h]['n']}</td></tr>" for h in horizons)}
</table>

<h2>K-line + Signal</h2>
{fig_kl.to_html(full_html=False, include_plotlyjs=False)}

<h2>Equity & Drawdown</h2>
{fig_eq.to_html(full_html=False, include_plotlyjs=False)}

<h2>IC-IR by Horizon</h2>
{fig_ic.to_html(full_html=False, include_plotlyjs=False)}

</body></html>"""

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"\n✅ HTML 報表: {OUTPUT_HTML}")


if __name__ == "__main__":
    run()
