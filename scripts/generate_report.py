#!/usr/bin/env python3
"""產生暗色主題 Plotly HTML 互動報表。

用法:
    python scripts/generate_report.py --symbol BTC/USDT --output report_btc.html
    python scripts/generate_report.py --symbol ETH/USDT --output report_eth.html

產出:
    4-row 互動圖表（K 線 + 進出場 / 權益曲線 / 回撤 / Rolling Sharpe）
    暗色主題，可在瀏覽器中縮放/平移。
"""

from __future__ import annotations

import argparse
import math
import statistics as st
import subprocess
import sys
from pathlib import Path

import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Design tokens ──────────────────────────────────────────────────────────
PAPER_BG = "#0a0e14"
PLOT_BG = "#11161e"
FONT_COLOR = "#e6edf3"
GRID_COLOR = "#21262d"
TEMPLATE = "plotly_dark"
FEE_RATE = 0.0009  # 0.09% per side


# ── Helpers ────────────────────────────────────────────────────────────────

def compute_momentum(closes: list[float], period: int = 20) -> list[float]:
    """momentum_N = close / close.shift(N) - 1"""
    sig = []
    for i in range(len(closes)):
        if i < period:
            sig.append(0.0)
        else:
            sig.append(closes[i] / closes[i - period] - 1.0)
    return sig


def compute_fwd_returns(closes: list[float]) -> list[float]:
    """forward return = close.shift(-1) / close - 1 (避免前視偏差)"""
    n = len(closes)
    return [closes[i + 1] / closes[i] - 1.0 for i in range(n - 1)]


def equity_curve(
    signal: list[float],
    fwd_returns: list[float],
    fee_rate: float = FEE_RATE,
) -> list[float]:
    """模擬進出場：momentum > 0 做多，<= 0 平倉。

    每次進/出場各扣一次手續費。
    假設初始資金 = 1.0。
    """
    n = min(len(signal), len(fwd_returns))
    equity = [1.0]
    position = 0  # 0=空倉, 1=持倉

    for i in range(n):
        prev_eq = equity[-1]
        target = 1 if signal[i] > 0 else 0

        # 進場
        if position == 0 and target == 1:
            prev_eq *= (1.0 - fee_rate)
            position = 1
        # 出場
        elif position == 1 and target == 0:
            prev_eq *= (1.0 - fee_rate)
            position = 0

        # 持倉損益
        if position == 1:
            prev_eq *= (1.0 + fwd_returns[i])

        equity.append(prev_eq)

    return equity


def compute_drawdown(equity: list[float]) -> list[float]:
    """計算回撤序列（負值表示虧損比例，0 表示新高）。"""
    dd = []
    peak = equity[0]
    for v in equity:
        if v > peak:
            peak = v
        dd.append((v / peak - 1.0) if peak > 0 else 0.0)
    return dd


def compute_rolling_sharpe(
    fwd_returns: list[float],
    window: int = 90,
) -> list[float]:
    """Rolling annualized Sharpe ratio (window-day)。"""
    result = []
    for i in range(len(fwd_returns)):
        if i < window:
            result.append(float("nan"))
            continue
        window_rets = fwd_returns[i - window : i]
        clean = [x for x in window_rets if not math.isnan(x)]
        if len(clean) < 2:
            result.append(float("nan"))
            continue
        mu = st.fmean(clean)
        sd = st.pstdev(clean)
        if sd == 0:
            result.append(0.0)
        else:
            result.append((mu / sd) * math.sqrt(365))
    return result


# ── Plotting ───────────────────────────────────────────────────────────────

def build_report(
    timestamps: list,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    signal: list[float],
    equity: list[float],
    drawdown: list[float],
    rolling_sharpe: list[float],
    symbol: str,
) -> go.Figure:
    """建立 4-row 暗色主題 Plotly 圖表。"""

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.40, 0.25, 0.20, 0.15],
        subplot_titles=(
            f"{symbol} — K-line + Entry/Exit",
            "Equity Curve (log scale)",
            "Drawdown",
            "Rolling Sharpe (90-day)",
        ),
    )

    # ── Row 1: K-line + entry/exit markers ──
    fig.add_trace(
        go.Candlestick(
            x=timestamps,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="K-line",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    # Entry markers (signal crosses from <=0 to >0)
    entry_x, entry_y = [], []
    # Exit markers (signal crosses from >0 to <=0)
    exit_x, exit_y = [], []
    for i in range(1, len(signal)):
        if signal[i] > 0 and signal[i - 1] <= 0:
            entry_x.append(timestamps[i] if i < len(timestamps) else timestamps[-1])
            entry_y.append(lows[i] * 0.995 if i < len(lows) else lows[-1] * 0.995)
        elif signal[i] <= 0 and signal[i - 1] > 0:
            exit_x.append(timestamps[i] if i < len(timestamps) else timestamps[-1])
            exit_y.append(highs[i] * 1.005 if i < len(highs) else highs[-1] * 1.005)

    if entry_x:
        fig.add_trace(
            go.Scatter(
                x=entry_x,
                y=entry_y,
                mode="markers",
                marker=dict(symbol="triangle-up", size=10, color="#00ff88"),
                name="Entry (Long)",
            ),
            row=1,
            col=1,
        )
    if exit_x:
        fig.add_trace(
            go.Scatter(
                x=exit_x,
                y=exit_y,
                mode="markers",
                marker=dict(symbol="triangle-down", size=10, color="#ff4444"),
                name="Exit (Flat)",
            ),
            row=1,
            col=1,
        )

    # ── Row 2: Equity curve (log scale) ──
    # Align equity with timestamps: equity length = len(signal)+1 (starts at 1.0)
    eq_x = timestamps[: len(equity)]
    fig.add_trace(
        go.Scatter(
            x=eq_x,
            y=equity,
            mode="lines",
            line=dict(color="#58a6ff", width=2),
            name="Equity",
            fill="tozeroy",
            fillcolor="rgba(88,166,255,0.08)",
        ),
        row=2,
        col=1,
    )

    # ── Row 3: Drawdown ──
    dd_x = timestamps[: len(drawdown)]
    fig.add_trace(
        go.Scatter(
            x=dd_x,
            y=drawdown,
            mode="lines",
            line=dict(color="#ef5350", width=1.5),
            name="Drawdown",
            fill="tozeroy",
            fillcolor="rgba(239,83,80,0.15)",
        ),
        row=3,
        col=1,
    )

    # ── Row 4: Rolling Sharpe ──
    rs_x = timestamps[: len(rolling_sharpe)]
    fig.add_trace(
        go.Scatter(
            x=rs_x,
            y=rolling_sharpe,
            mode="lines",
            line=dict(color="#d2a8ff", width=1.5),
            name="Rolling Sharpe",
        ),
        row=4,
        col=1,
    )

    # ── Layout: dark theme ──
    fig.update_layout(
        template=TEMPLATE,
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR, size=12),
        title=dict(
            text=f"<b>{symbol} Factor Lab Report</b><br><sup>Momentum(20) — Fee {FEE_RATE*100:.2f}%/side</sup>",
            font=dict(size=18),
        ),
        height=1100,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(10,14,20,0.8)",
        ),
        xaxis4=dict(title="Date"),
    )

    # Row-specific axes
    fig.update_yaxes(title_text="Price", type="log", row=1, col=1)
    fig.update_yaxes(title_text="Equity", type="log", row=2, col=1)
    fig.update_yaxes(title_text="Drawdown %", tickformat=".0%", row=3, col=1)
    fig.update_yaxes(title_text="Sharpe (ann.)", row=4, col=1)

    # Grid styling
    fig.update_xaxes(
        gridcolor=GRID_COLOR,
        zeroline=False,
        showgrid=True,
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        zeroline=False,
        showgrid=True,
    )

    return fig


# ── Stats summary block (embedded in HTML) ─────────────────────────────────

def compute_stats(
    equity: list[float],
    fwd_returns: list[float],
    signal: list[float],
    drawdown: list[float],
    rolling_sharpe: list[float],
) -> str:
    """計算摘要指標並產生 HTML 區塊。"""

    n = min(len(fwd_returns), len(signal))
    # Filter to periods where position = long
    strat_rets = []
    position = 0
    for i in range(n):
        target = 1 if signal[i] > 0 else 0
        if position == 0 and target == 1:
            position = 1
        elif position == 1 and target == 0:
            position = 0
        if position == 1:
            strat_rets.append(fwd_returns[i])

    total_return = (equity[-1] - 1.0) * 100

    if len(strat_rets) < 2:
        sharpe = 0.0
    else:
        mu = st.fmean(strat_rets)
        sd = st.pstdev(strat_rets)
        sharpe = (mu / sd) * math.sqrt(365) if sd else 0.0

    max_dd = min(drawdown) * 100
    trade_count = sum(
        1
        for i in range(1, len(signal))
        if (signal[i] > 0 and signal[i - 1] <= 0)
    )

    # Win rate
    strat_rets_clean = [r for r in strat_rets if not math.isnan(r)]
    win_rate = (
        sum(1 for r in strat_rets_clean if r > 0) / len(strat_rets_clean) * 100
        if strat_rets_clean
        else 0
    )

    # Average rolling Sharpe
    valid_rs = [x for x in rolling_sharpe if not math.isnan(x)]
    avg_rolling_sharpe = st.fmean(valid_rs) if valid_rs else 0.0

    return f"""
    <div style="
        display: flex; flex-wrap: wrap; gap: 12px; justify-content: center;
        padding: 16px 8px;
        font-family: 'Segoe UI', system-ui, sans-serif;
    ">
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Total Return</div>
            <div style="color:{'#26a69a' if total_return >= 0 else '#ef5350'}; font-size:22px; font-weight:700;">{total_return:+.2f}%</div>
        </div>
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Ann. Sharpe</div>
            <div style="color:{'#26a69a' if sharpe >= 0 else '#ef5350'}; font-size:22px; font-weight:700;">{sharpe:.2f}</div>
        </div>
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Max DD</div>
            <div style="color:#ef5350; font-size:22px; font-weight:700;">{max_dd:.2f}%</div>
        </div>
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Win Rate</div>
            <div style="color:{'#26a69a' if win_rate >= 50 else '#e6edf3'}; font-size:22px; font-weight:700;">{win_rate:.1f}%</div>
        </div>
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Trades</div>
            <div style="color:#d2a8ff; font-size:22px; font-weight:700;">{trade_count}</div>
        </div>
        <div class="stat-box" style="background:#11161e; border-radius:8px; padding:10px 18px; text-align:center; min-width:100px;">
            <div style="color:#8b949e; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Avg Roll. Sharpe</div>
            <div style="color:{'#26a69a' if avg_rolling_sharpe >= 0 else '#ef5350'}; font-size:22px; font-weight:700;">{avg_rolling_sharpe:.2f}</div>
        </div>
    </div>
    """


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate dark-themed Plotly HTML interactive report"
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML path (default: report_<symbol_lower>.html)",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=FEE_RATE,
        help=f"Fee rate per side (default: {FEE_RATE})",
    )
    parser.add_argument(
        "--momentum-period",
        type=int,
        default=20,
        help="Momentum lookback period (default: 20)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Skip opening browser",
    )

    args = parser.parse_args()

    # Resolve symbol → parquet filename
    symbol_map = {
        "BTC/USDT": "btcusdt_1d.parquet",
        "ETH/USDT": "ethusdt_1d.parquet",
        "btcusdt": "btcusdt_1d.parquet",
        "ethusdt": "ethusdt_1d.parquet",
    }
    fname = symbol_map.get(args.symbol, symbol_map.get(args.symbol.upper(), None))
    if fname is None:
        # Try lowercase conversion
        fname = f"{args.symbol.replace('/', '').lower()}_1d.parquet"

    data_path = Path(__file__).parent.parent / "data" / fname
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}")
        sys.exit(1)

    output_path = args.output or f"report_{args.symbol.replace('/', '_').lower()}.html"
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    # ── Load data ──
    print(f"Loading: {data_path}")
    df = pl.read_parquet(data_path)

    # Convert timestamp (i64 ms) → datetime for Plotly
    if "timestamp" in df.columns:
        from datetime import datetime as dt

        ts_list = df["timestamp"].to_list()
        timestamps = [dt.fromtimestamp(t / 1000.0) for t in ts_list]
    else:
        timestamps = list(range(len(df)))

    opens = df["open"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    volumes = df["volume"].to_list()

    # ── Compute factor & signals ──
    print(f"Computing momentum({args.momentum_period}) factor...")
    signal = compute_momentum(closes, period=args.momentum_period)

    # ── Forward returns ──
    fwd_returns = compute_fwd_returns(closes)

    # ── Equity curve ──
    print("Simulating equity curve...")
    equity = equity_curve(signal, fwd_returns, fee_rate=args.fee)

    # ── Drawdown ──
    print("Computing drawdown...")
    drawdown = compute_drawdown(equity)

    # ── Rolling Sharpe ──
    print("Computing rolling Sharpe (90-day)...")
    rolling_sharpe = compute_rolling_sharpe(fwd_returns, window=90)

    # ── Align lengths ──
    # equity has one extra element (starts at 1.0), prepend a dummy timestamp
    # For plotting, we use equity[1:] aligned with timestamps, or just use as-is
    # equity = [1.0, e1, e2, ..., eN] where N = len(signal)
    # timestamps = [t0, t1, ..., tN-1]
    # We'll plot equity starting from timestamps[0] for equity[1]
    eq_for_plot = equity[1:]  # drop initial 1.0

    # ── Build report ──
    print("Building Plotly report...")
    fig = build_report(
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        signal=signal,
        equity=eq_for_plot,
        drawdown=drawdown,
        rolling_sharpe=rolling_sharpe,
        symbol=args.symbol,
    )

    # ── Stats summary ──
    stats_html = compute_stats(
        equity=equity,
        fwd_returns=fwd_returns,
        signal=signal,
        drawdown=drawdown,
        rolling_sharpe=rolling_sharpe,
    )

    # ── Assemble HTML ──
    chart_div = fig.to_html(full_html=False, include_plotlyjs="cdn")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{args.symbol} — Factor Lab Report</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    background-color: {PAPER_BG};
    color: {FONT_COLOR};
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
}}
.container {{ max-width:1400px; margin:0 auto; padding:20px 24px; }}
h1 {{
    text-align:center;
    font-size:24px;
    font-weight:700;
    margin-bottom:4px;
    color: #58a6ff;
}}
h2 {{
    text-align:center;
    font-size:14px;
    font-weight:400;
    color: #8b949e;
    margin-bottom:16px;
}}
</style>
</head>
<body>
<div class="container">
<h1>{args.symbol} Factor Lab Report</h1>
<h2>Momentum({args.momentum_period}) — Fee Rate: {args.fee*100:.2f}%/side — Generated on {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</h2>
{stats_html}
{chart_div}
</div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    print(f"Report saved: {output_path} ({len(html):,} bytes)")

    # ── Open browser ──
    if not args.no_open:
        try:
            subprocess.run(
                ["google-chrome", "--new-window", str(output_path)],
                check=False,
                timeout=5,
            )
            print(f"Opened in Chrome: {output_path}")
        except FileNotFoundError:
            print(f"Chrome not found. Open manually: {output_path}")
        except Exception as e:
            print(f"Could not open browser: {e}")


if __name__ == "__main__":
    main()
