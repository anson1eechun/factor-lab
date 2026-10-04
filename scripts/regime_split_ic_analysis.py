#!/usr/bin/env python3
"""
Regime-Split Factor IC-IR Analysis
===================================
分析每個 validated 因子在「有序市」(ordered) vs「無序市」(disordered) 下的預測力差異，
為 regime-aware 因子組合提供實證基礎。

Regime 定義 (來自 F1_Complexity_Gap_Regime):
  - ordered:   delta >= 0.05 (趨勢/動能主導)
  - critical:  0.02 <= delta < 0.05 (臨界)
  - disordered: delta < 0.02 (均值回歸主導)

輸出：
  - 終端文字摘要
  - 互動 HTML 圖表 (Plotly 暗色主題)
"""

from __future__ import annotations
import sys, os, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from itertools import product
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ── Signal imports ──────────────────────────────────────────────────
from core.signals.F1_Complexity_Gap_Regime import compute as f1_compute
from core.signals.F2_Liquidity_Consumption_Tilt import compute as f2_compute
from core.signals.F4_Flow_Divergence_Ratio import compute as f4_compute
from core.signals.F5_Anchored_Mean_Reversion_Score import compute as f5_compute
from core.signals.F8_cubic_momentum_threshold_reversal import factor as f8_factor
from core.signals.F10_vol_adj_momentum import factor as f10_factor
from core.signals.F16_clv_momentum import factor as f16_factor

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
OUTPUT_HTML = "/home/anson/factor-lab/output/regime_split_ic_analysis.html"

# ── Data ─────────────────────────────────────────────────────────────
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
    """Convert pd.DataFrame to list[dict] for compute() interface."""
    return [
        {"ts": int(row.timestamp.timestamp() * 1000),
         "open": row.open, "high": row.high,
         "low": row.low, "close": row.close,
         "volume": row.volume}
        for row in df.itertuples()
    ]

# ── Rank-IC ──────────────────────────────────────────────────────────
def rank_ic(signal, fwd_ret):
    """Spearman rank correlation between signal and forward return."""
    valid = signal.notna() & (signal != 0.0) & fwd_ret.notna()
    s = signal[valid]
    r = fwd_ret[valid]
    if len(s) < 30:
        return None, None, 0
    ic, pval = spearmanr(s, r)
    # Rolling IC for IC-IR (use min 60-period rolling window)
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

# ── Main Analysis ────────────────────────────────────────────────────
def run():
    print("=" * 60)
    print("Regime-Split Factor IC-IR Analysis")
    print("=" * 60)

    # 1. Fetch data
    print("\n[1/5] 載入 BTCUSDT 日線 ...")
    df = fetch_binance_daily("BTCUSDT", 1500)
    print(f"      取得 {len(df)} 筆, {df.timestamp.iloc[0].date()} ~ {df.timestamp.iloc[-1].date()}")

    # 2. Compute F1 (regime indicator) using compute() interface
    print("\n[2/5] 計算 F1 Complexity Gap Regime ...")
    ohlcv_list = df_to_ohlcv_list(df)
    f1_result = f1_compute(ohlcv_list)
    delta = pd.Series(f1_result["delta"], index=df.index)
    regime_label = pd.Series(f1_result["regime"], index=df.index)

    # F1 signal (for regime confirmation only — negate per validated direction)
    f1_signal = pd.Series(f1_result["signal"], index=df.index)

    regime_counts = pd.Series(regime_label).value_counts()
    print(f"      {regime_counts.to_dict()}")

    # 3. Compute all factors
    print("\n[3/5] 計算 7 個 validated 因子 ...")
    factors = {}

    # compute() interface: F2, F4, F5 (returns dict with 'signal')
    for name, fn, kwargs in [
        ("F2_VolumeWeightedTilt", f2_compute, {}),
        ("F4_FlowDivergence", f4_compute, {}),
        ("F5_AMRS", f5_compute, {}),
    ]:
        try:
            result = fn(ohlcv_list, **kwargs)
            factors[name] = pd.Series(result["signal"], index=df.index)
            print(f"      {name}: OK ({factors[name].notna().sum()} valid)")
        except Exception as e:
            print(f"      {name}: FAILED — {e}")
            factors[name] = pd.Series(np.nan, index=df.index)

    # factor() interface: F8, F10, F16 (returns pd.Series)
    for name, fn, kwargs in [
        ("F8_CubicMomRev", f8_factor, {}),
        ("F10_VolAdjMom", f10_factor, {}),
        ("F16_CLVMom", f16_factor, {}),
    ]:
        try:
            result = fn(df, **kwargs)
            factors[name] = pd.Series(result.values, index=df.index)
            print(f"      {name}: OK ({factors[name].notna().sum()} valid)")
        except Exception as e:
            print(f"      {name}: FAILED — {e}")
            factors[name] = pd.Series(np.nan, index=df.index)

    # Also add F1 (negated) as a factor for analysis
    factors["F1_ComplexityGap"] = -f1_signal  # negate per validated direction

    # 4. Forward returns at multiple horizons
    print("\n[4/5] 計算 forward returns (h=1,5,10,20) ...")
    horizons = [1, 5, 10, 20]
    fwd_returns = {}
    for h in horizons:
        fwd_returns[h] = df["close"].pct_change(h).shift(-h)
        print(f"      h={h:>2}d: {fwd_returns[h].notna().sum()} obs")

    # 5. Regime-split IC analysis
    print("\n[5/5] Regime-split IC-IR 分析 ...")
    regimes = {
        "ordered": regime_label == "ordered",
        "critical": regime_label == "critical",
        "disordered": regime_label == "disordered",
    }

    results = defaultdict(lambda: defaultdict(dict))

    for regime, mask in regimes.items():
        n_regime = mask.sum()
        if n_regime < 30:
            print(f"      {regime}: only {n_regime} obs, skipping")
            continue

        for fname in factors:
            sig = factors[fname][mask]
            for h in horizons:
                fwd = fwd_returns[h][mask]
                ic, ic_ir, n = rank_ic(sig, fwd)
                results[regime][fname][h] = {
                    "ic": ic, "ic_ir": ic_ir, "n": n
                }

    # ── Print Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS: Rank-IC / IC-IR by Regime × Factor × Horizon")
    print("=" * 60)

    for regime in ["ordered", "critical", "disordered"]:
        if regime not in results or not results[regime]:
            continue
        n = regime_counts.get(regime, 0)
        print(f"\n── {regime.upper()} ({n} obs) ──")
        print(f"    {'Factor':<25} {'h=1':>12} {'h=5':>12} {'h=10':>12} {'h=20':>12}")
        print(f"    {'─'*25} {'─'*12} {'─'*12} {'─'*12} {'─'*12}")

        for fname in sorted(results[regime].keys()):
            # Find best IC-IR across horizons
            best_h = None
            best_ir = -999
            row_parts = []
            for h in horizons:
                r = results[regime][fname].get(h, {})
                ic_ir = r.get("ic_ir")
                if ic_ir is not None and abs(ic_ir) > best_ir:
                    best_ir = abs(ic_ir)
                    best_h = h
                if ic_ir is not None:
                    row_parts.append(f"{ic_ir:+.3f}")
                else:
                    row_parts.append("N/A")
            marker = " ★" if best_ir >= 0.3 else ""
            print(f"    {fname:<25} {row_parts[0]:>12} {row_parts[1]:>12} {row_parts[2]:>12} {row_parts[3]:>12}{marker}")

    # ── Regime Differential ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("REGIME DIFFERENTIAL: Ordered IR − Disordered IR (h=5)")
    print("=" * 60)
    print(f"    {'Factor':<25} {'Ord IR':>10} {'Dis IR':>10} {'Diff':>10} {'Direction':>12}")

    for fname in sorted(factors.keys()):
        ord_ir = results.get("ordered", {}).get(fname, {}).get(5, {}).get("ic_ir")
        dis_ir = results.get("disordered", {}).get(fname, {}).get(5, {}).get("ic_ir")
        if ord_ir is not None and dis_ir is not None:
            diff = (ord_ir or 0) - (dis_ir or 0)
            direction = "momentum-fav" if diff > 0.05 else ("mean-rev-fav" if diff < -0.05 else "neutral")
            print(f"    {fname:<25} {ord_ir:>+10.3f} {dis_ir:>+10.3f} {diff:>+10.3f} {direction:>12}")

    # ── Generate HTML Report ─────────────────────────────────────────
    # Already computed in run()
    f1_delta_raw = f1_result["delta"]
    # F1 returns length-1 less because of log returns; pad with NaN
    f1_delta = pd.Series(f1_delta_raw, index=df.index)
    f1_delta = f1_delta.dropna()

    generate_html(results, regime_counts, factors, fwd_returns, horizons, df, regime_label, f1_delta)

    return results, regime_counts


def generate_html(results, regime_counts, factors, fwd_returns, horizons, df, regime_label, f1_delta):
    """Generate interactive Plotly HTML report."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio

    pio.templates.default = "plotly_dark"

    factor_names = sorted(factors.keys())
    regime_names = [r for r in ["ordered", "critical", "disordered"] if r in results and results[r]]

    # ── Heatmap: IC-IR by Factor × Regime (using best horizon) ──
    best_horizon_ir = {}
    for rname in regime_names:
        best_horizon_ir[rname] = {}
        for fname in factor_names:
            best_ir = None
            for h in horizons:
                ir = results[rname].get(fname, {}).get(h, {}).get("ic_ir")
                if ir is not None and (best_ir is None or abs(ir) > abs(best_ir)):
                    best_ir = ir
            best_horizon_ir[rname][fname] = best_ir if best_ir is not None else 0.0

    z_data = [[best_horizon_ir[r][f] for f in factor_names] for r in regime_names]
    z_text = [[f"{v:+.3f}" if v != 0 else "N/A" for v in row] for row in z_data]

    fig_heatmap = go.Figure(
        data=go.Heatmap(
            z=z_data,
            x=factor_names,
            y=regime_names,
            text=z_text,
            texttemplate="%{text}",
            textfont={"size": 12},
            colorscale="RdBu_r",
            zmid=0,
            colorbar=dict(title="IC-IR"),
        )
    )
    fig_heatmap.update_layout(
        title="Best-Horizon IC-IR by Factor × Regime",
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
    )

    # ── Grouped bar: Ordered vs Disordered IC-IR at h=5 ──
    h5_data = {}
    for fname in factor_names:
        ord_ir = results.get("ordered", {}).get(fname, {}).get(5, {}).get("ic_ir") or 0
        dis_ir = results.get("disordered", {}).get(fname, {}).get(5, {}).get("ic_ir") or 0
        h5_data[fname] = {"ordered": ord_ir, "disordered": dis_ir}

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=factor_names,
        y=[h5_data[f]["ordered"] for f in factor_names],
        name="Ordered (趨勢)",
        marker_color="#00cc96",
    ))
    fig_bar.add_trace(go.Bar(
        x=factor_names,
        y=[h5_data[f]["disordered"] for f in factor_names],
        name="Disordered (震盪)",
        marker_color="#ef553b",
    ))
    fig_bar.update_layout(
        title="IC-IR at Horizon=5: Ordered vs Disordered",
        barmode="group",
        yaxis_title="IC-IR",
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        yaxis=dict(zeroline=True, zerolinecolor="gray"),
    )

    # ── Regime timeline ──
    fig_timeline = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.3, 0.7],
        vertical_spacing=0.05,
        subplot_titles=["Regime Classification", "BTC Close Price"]
    )

    # Regime scatter
    for rname, color in [("ordered", "#00cc96"), ("critical", "#ffa15a"), ("disordered", "#ef553b")]:
        mask = regime_label == rname
        fig_timeline.add_trace(
            go.Scatter(
                x=df.loc[mask, "timestamp"],
                y=[1]*mask.sum(),
                mode="markers",
                marker=dict(color=color, size=3, symbol="square"),
                name=rname,
                showlegend=True,
            ),
            row=1, col=1,
        )

    # BTC close
    fig_timeline.add_trace(
        go.Scatter(
            x=df["timestamp"], y=df["close"],
            mode="lines", name="BTC",
            line=dict(color="white", width=1),
        ),
        row=2, col=1,
    )

    fig_timeline.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig_timeline.update_yaxes(title_text="Phase", row=1, col=1)
    fig_timeline.update_yaxes(title_text="Price (USDT)", row=2, col=1)

    # ── Compile full HTML ──
    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        "<title>Regime-Split IC-IR Analysis</title>",
        "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>",
        "<style>",
        "body{background:#111;color:#eee;font-family:monospace;margin:20px;}",
        "h1{color:#00cc96;}",
        "h2{color:#ffa15a;margin-top:40px;}",
        "table{border-collapse:collapse;margin:10px 0;width:100%;}",
        "th,td{border:1px solid #333;padding:6px 12px;text-align:right;}",
        "th{background:#222;color:#00cc96;}",
        "td{font-family:monospace;}",
        ".positive{color:#00cc96;}",
        ".negative{color:#ef553b;}",
        ".section{margin:20px 0;}",
        ".summary{background:#1a1a1a;padding:15px;border-left:3px solid #00cc96;margin:20px 0;}",
        "</style></head><body>",
        f"<h1>🔬 Regime-Split Factor IC-IR Analysis</h1>",
        f"<p>Generated: {NOW} | Symbol: BTCUSDT | Data: {len(df)} daily candles</p>",

        # Summary box
        f"<div class='summary'>",
        f"<strong>Regime Distribution:</strong><br>",
        f"Ordered (趨勢): {regime_counts.get('ordered',0)} obs ({regime_counts.get('ordered',0)/len(df)*100:.1f}%)<br>",
        f"Critical (臨界): {regime_counts.get('critical',0)} obs<br>",
        f"Disordered (震盪): {regime_counts.get('disordered',0)} obs ({regime_counts.get('disordered',0)/len(df)*100:.1f}%)<br>",
        f"</div>",

        # Detail tables
        f"<h2>IC-IR Detail by Regime</h2>",
    ]

    for rname in regime_names:
        n = regime_counts.get(rname, 0)
        html_parts.append(f"<h3>{rname.upper()} (n={n})</h3>")
        html_parts.append("<table><tr><th>Factor</th>")
        for h in horizons:
            html_parts.append(f"<th>h={h} IC</th><th>h={h} IR</th>")
        html_parts.append("</tr>")

        for fname in factor_names:
            html_parts.append(f"<tr><td>{fname}</td>")
            for h in horizons:
                r = results[rname].get(fname, {}).get(h, {})
                ic = r.get("ic")
                ic_ir = r.get("ic_ir")
                ic_class = "positive" if (ic or 0) > 0 else "negative"
                ir_class = "positive" if (ic_ir or 0) >= 0.3 else ("negative" if (ic_ir or 0) <= -0.3 else "")
                html_parts.append(f"<td class='{ic_class}'>{ic if ic is not None else 'N/A'}</td>")
                html_parts.append(f"<td class='{ir_class}'>{ic_ir if ic_ir is not None else 'N/A'}</td>")
            html_parts.append("</tr>")
        html_parts.append("</table>")

    html_parts.append("<h2>Visualizations</h2>")
    html_parts.append(fig_heatmap.to_html(full_html=False, include_plotlyjs=False))
    html_parts.append(fig_bar.to_html(full_html=False, include_plotlyjs=False))
    html_parts.append(fig_timeline.to_html(full_html=False, include_plotlyjs=False))

    html_parts.append("</body></html>")

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w") as f:
        f.write("\n".join(html_parts))
    print(f"\n✅ HTML 報表: {OUTPUT_HTML}")

if __name__ == "__main__":
    run()
