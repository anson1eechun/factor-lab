#!/usr/bin/env python3
"""Generate HTML backtest report with Plotly charts"""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
sys.path.insert(0, '/home/anson/factor-lab/core/signals')
import pandas as pd, numpy as np, json
from core.adapters.crypto import CryptoAdapter

adapter = CryptoAdapter()
raw = adapter.get_ohlcv("BTCUSDT", "1h", limit=5000)
raw['dt'] = pd.to_datetime(raw['timestamp'], unit='ms', utc=True)
df = raw.set_index('dt').sort_index()

hrs = df.index.hour.values
hi_liq = ((hrs>=0)&(hrs<4)) | ((hrs>=7)&(hrs<10)) | ((hrs>=12)&(hrs<16))

# Re-use signal generation from combo_backtest.py
def fvg_signal(df, lb=20, gap=0.3):
    O=df["open"].values; H=df["high"].values; L=df["low"].values; C=df["close"].values
    n=len(df); sig=np.zeros(n); zones=[]
    for i in range(2,n):
        g=C[i]*gap/100.0
        if L[i-2]-H[i]>g: zones.append((i,H[i],L[i-2],+1))
        if L[i]-H[i-2]>g: zones.append((i,H[i-2],L[i],-1))
        zones=[z for z in zones if i-z[0]<=lb]
        bull=bear=0; unmit=[]
        for ii,bt,tp,d in zones:
            if d==+1:
                if L[i]<=tp and L[i]>=bt: bear-=1
                else: unmit.append((ii,bt,tp,d))
            else:
                if H[i]>=bt and H[i]<=tp: bull+=1
                else: unmit.append((ii,bt,tp,d))
        zones=unmit; net=bull+bear
        if net!=0: sig[i]=np.sign(net)
    sig[:lb+2]=np.nan; sig[-1]=0
    return pd.Series(sig,index=df.index)

def ls_signal(df, slb=20, conf=2):
    H=df["high"].values; L=df["low"].values; C=df["close"].values; n=len(df)
    sig=np.zeros(n); sh=[]; sl=[]
    for i in range(slb+2,n-conf):
        ws=i-slb; we=i; mid=i-slb//2
        if H[mid]>=np.max(H[ws:we+1]) and mid>ws+3 and mid<we-3: sh.append((mid,H[mid]))
        if L[mid]<=np.min(L[ws:we+1]) and mid>ws+3 and mid<we-3: sl.append((mid,L[mid]))
        co=i-3*slb; sh=[(j,p) for j,p in sh if j>co]; sl=[(j,p) for j,p in sl if j>co]
        for j,p in sh:
            if H[i]>p and C[i+conf]<p: sig[i+conf]=-1.0; sh=[(k,q) for k,q in sh if k!=j]; break
        for j,p in sl:
            if L[i]<p and C[i+conf]>p: sig[i+conf]=+1.0; sl=[(k,q) for k,q in sl if k!=j]; break
    sig[:slb+2+conf]=np.nan; sig[-1]=0
    return pd.Series(sig,index=df.index)

def vm_signal(df, vl=20, vt=0.8):
    O=df["open"].values; H=df["high"].values; L=df["low"].values
    C=df["close"].values; V=df["volume"].values; n=len(df)
    sig=np.zeros(n)
    for i in range(vl,n):
        rng=H[i]-L[i]
        if rng==0: continue
        br=(C[i]-O[i])/rng; d=np.sign(br)
        vw=V[i-vl:i]; vm=np.mean(vw); vs=np.std(vw)
        if vs==0: continue
        vz=(V[i]-vm)/vs
        if abs(vz)>vt and abs(br)>0.25: sig[i]=d
    sig[:vl]=np.nan; sig[-1]=0
    return pd.Series(sig,index=df.index)

def orb_signal(df, orb_bars=2):
    H=df["high"].values; L=df["low"].values; C=df["close"].values
    hrs=df.index.hour.values; n=len(df)
    sig=np.zeros(n)
    starts=[]
    for i in range(1,n):
        if (hrs[i-1]==23 and hrs[i]==0) or (hrs[i-1]==6 and hrs[i]==7) or (hrs[i-1]==11 and hrs[i]==12):
            starts.append(i)
    starts.append(n)
    for k in range(len(starts)-1):
        s0=starts[k]; s1=starts[k+1]
        oe=min(s0+orb_bars, s1)
        if oe-s0 < orb_bars: continue
        rh=np.max(H[s0:oe]); rl=np.min(L[s0:oe])
        for j in range(oe, s1):
            if C[j] > rh: sig[j]=+1.0
            elif C[j] < rl: sig[j]=-1.0
    sig[:orb_bars+1]=np.nan; sig[-1]=0
    return pd.Series(sig,index=df.index)

def maj_sig(*sigs):
    a=np.column_stack([s.fillna(0).values for s in sigs])
    v=a.sum(axis=1)
    return pd.Series(np.where(np.abs(v)>=2, np.sign(v), 0).astype(float), index=sigs[0].index)

fvg = fvg_signal(df); ls = ls_signal(df); vm = vm_signal(df); orb = orb_signal(df)

# Top 3 configs to chart
configs = [
    ('FVG+LS+VM MAJ h3 (Session)', maj_sig(fvg, ls, vm), 3, hi_liq, True),
    ('FVG+LS+VM MAJ h6 (Session)', maj_sig(fvg, ls, vm), 6, hi_liq, True),
    ('LS+VM MAJ h6 (Session)', maj_sig(ls, vm), 6, hi_liq, True),
]

def get_trades(sig_s, df, h, smask=None):
    s=sig_s.values; O=df["open"].values; n=len(df)
    trades=[]
    for i in range(n-h-1):
        if np.isnan(s[i]) or s[i]==0: continue
        if smask is not None and not smask[i]: continue
        d=s[i]; eb=i+1; xb=i+1+h
        if xb>=n: continue
        ep=O[eb]; xp=O[xb]
        r=(xp/ep-1)*10000 if d==1 else (1-xp/ep)*10000
        trades.append({
            'entry_bar': int(eb), 'exit_bar': int(xb), 'direction': int(d),
            'ret_bps': float(r), 'entry_price': float(ep), 'exit_price': float(xp),
            'entry_time': str(df.index[eb]), 'exit_time': str(df.index[xb])
        })
    return trades

# Collect trade data for all configs
all_trade_data = {}
for name, sig, h, smask, _ in configs:
    all_trade_data[name] = get_trades(sig, df, h, smask)

# ======= BUILD HTML WITH PLOTLY =======
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Summary table data
summary_rows = [
    ('FVG+LS+VM MAJ h3 S', 16, 0.6875, 61.5, -40.6, 2.447, -110, 7),
    ('FVG+LS+VM MAJ h6 S', 16, 0.6875, 98.3, -67.5, 2.181, -201, 7),
    ('LS+VM MAJ h6 S', 12, 0.6667, 74.3, -58.8, 1.638, -235, 7),
    ('FVG+VM AND h3 R', 7, 0.8571, 39.8, -3.7, 3.947, -4, 8),
    ('LS+VM AND h6 S', 12, 0.6667, 74.3, -58.8, 1.638, -235, 7),
    ('ORB h2 S', 450, 0.4667, 64.4, -42.6, 2.627, -1529, 5),
    ('VM h1 S', 711, 0.5035, 43.1, -37.8, 1.715, -1024, 4),
    ('FVG h6 R', 139, 0.5324, 77.0, -80.4, 0.472, -1090, 3),
]

# Create figures for each top config
figures = []
for cfg_name, trades in all_trade_data.items():
    trades_sorted = sorted(trades, key=lambda x: x['entry_bar'])
    
    # Get price data subset (last 500 bars for readability)
    start_bar = max(0, trades_sorted[0]['entry_bar'] - 100) if trades_sorted else len(df)-500
    end_bar = min(len(df), (trades_sorted[-1]['exit_bar'] + 50) if trades_sorted else len(df))
    
    dplot = df.iloc[start_bar:end_bar]
    times = dplot.index
    
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=(f'{cfg_name} — Price & Trades', 'Equity Curve (bps)', 'Drawdown (bps)')
    )
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=times, open=dplot['open'], high=dplot['high'],
        low=dplot['low'], close=dplot['close'],
        name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)
    
    # Entry/Exit markers
    long_entries = [(t['entry_bar'], t['entry_price']) for t in trades_sorted if t['direction']==1 and t['entry_bar']>=start_bar and t['entry_bar']<end_bar]
    short_entries = [(t['entry_bar'], t['entry_price']) for t in trades_sorted if t['direction']==-1 and t['entry_bar']>=start_bar and t['entry_bar']<end_bar]
    long_exits = [(t['exit_bar'], t['exit_price']) for t in trades_sorted if t['direction']==1 and t['exit_bar']>=start_bar and t['exit_bar']<end_bar]
    short_exits = [(t['exit_bar'], t['exit_price']) for t in trades_sorted if t['direction']==-1 and t['exit_bar']>=start_bar and t['exit_bar']<end_bar]
    
    if long_entries:
        le_bars = [df.index[e[0]] for e in long_entries]
        le_prices = [e[1] for e in long_entries]
        fig.add_trace(go.Scatter(x=le_bars, y=le_prices, mode='markers',
            marker=dict(symbol='triangle-up', size=12, color='lime', line=dict(width=1, color='white')),
            name='Long Entry'), row=1, col=1)
    if short_entries:
        se_bars = [df.index[e[0]] for e in short_entries]
        se_prices = [e[1] for e in short_entries]
        fig.add_trace(go.Scatter(x=se_bars, y=se_prices, mode='markers',
            marker=dict(symbol='triangle-down', size=12, color='red', line=dict(width=1, color='white')),
            name='Short Entry'), row=1, col=1)
    if long_exits:
        lx_bars = [df.index[e[0]] for e in long_exits]
        lx_prices = [e[1] for e in long_exits]
        fig.add_trace(go.Scatter(x=lx_bars, y=lx_prices, mode='markers',
            marker=dict(symbol='x', size=8, color='cyan'),
            name='Long Exit'), row=1, col=1)
    if short_exits:
        sx_bars = [df.index[e[0]] for e in short_exits]
        sx_prices = [e[1] for e in short_exits]
        fig.add_trace(go.Scatter(x=sx_bars, y=sx_prices, mode='markers',
            marker=dict(symbol='x', size=8, color='magenta'),
            name='Short Exit'), row=1, col=1)
    
    # Equity curve (full)
    rets = [t['ret_bps'] for t in trades_sorted]
    equity = np.cumsum(rets)
    entry_times = [t['entry_time'] for t in trades_sorted]
    fig.add_trace(go.Scatter(x=entry_times, y=equity, mode='lines+markers',
        line=dict(color='gold', width=2), marker=dict(size=5),
        name='Equity'), row=2, col=1)
    fig.add_hline(y=0, line_dash='dash', line_color='gray', row=2, col=1)
    
    # Drawdown
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    fig.add_trace(go.Scatter(x=entry_times, y=dd, mode='lines',
        fill='tozeroy', line=dict(color='red', width=1),
        fillcolor='rgba(255,0,0,0.15)', name='Drawdown'), row=3, col=1)
    
    # Dark theme
    fig.update_layout(
        template='plotly_dark',
        height=900,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=60, r=60, t=80, b=60),
    )
    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text='Price', row=1, col=1)
    fig.update_yaxes(title_text='Equity (bps)', row=2, col=1)
    fig.update_yaxes(title_text='DD (bps)', row=3, col=1)
    
    figures.append(fig)

# Build complete HTML
html_parts = [
'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Multi-Signal Combination Backtest — 1H BTCUSDT</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body { background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; }
  h1 { color: #58a6ff; border-bottom: 2px solid #30363d; padding-bottom: 10px; }
  h2 { color: #f0883e; margin-top: 30px; }
  .stats { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin: 20px 0; }
  table { width: 100%; border-collapse: collapse; margin: 15px 0; }
  th { background: #21262d; color: #58a6ff; padding: 10px; text-align: left; border: 1px solid #30363d; }
  td { padding: 8px 10px; border: 1px solid #30363d; font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 13px; }
  tr:hover { background: #1c2128; }
  .good { color: #3fb950; font-weight: bold; }
  .warn { color: #d29922; }
  .bad { color: #f85149; }
  .highlight { background: #1a2332; }
  .metric-box { display: inline-block; background: #21262d; border-radius: 6px; padding: 12px 16px; margin: 6px; min-width: 100px; text-align: center; }
  .metric-box .label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
  .metric-box .value { font-size: 22px; font-weight: bold; }
  .chart-container { margin: 30px 0; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
</style>
</head>
<body>
<h1>Multi-Signal Combination Backtest</h1>
<div class="stats">
  <p><strong>Symbol:</strong> BTCUSDT | <strong>Timeframe:</strong> 1H | <strong>Period:</strong> 2025-11-12 → 2026-06-09 (208 days)</p>
  <p><strong>Signals:</strong> FVG (Fair Value Gap) + LS (Liquidity Sweep) + VM (Volume Momentum) + ORB (Opening Range Breakout)</p>
  <p><strong>Combination:</strong> MAJORITY (≥2 signals agree) | <strong>Session Filter:</strong> Asia Open + London Open + NY Open (high liquidity only)</p>
</div>

<h2>Summary Rankings (Trade-Level)</h2>
<table>
  <tr><th>Config</th><th>Trades</th><th>Win Rate</th><th>Avg Win</th><th>Avg Loss</th><th>Ann Sharpe</th><th>MaxDD</th><th>Score</th></tr>'''
]

for row in summary_rows:
    name, nt, wr, aw, al, ash, mdd, sc = row
    wr_class = 'good' if wr>=0.60 else ('warn' if wr>=0.50 else 'bad')
    ash_class = 'good' if ash>=1.5 else ('warn' if ash>=0.5 else 'bad')
    sc_class = 'good' if sc>=7 else ('warn' if sc>=5 else '')
    html_parts.append(
        f'  <tr class="{"highlight" if sc>=7 else ""}">'
        f'<td><strong>{name}</strong></td><td>{nt}</td>'
        f'<td class="{wr_class}">{wr:.1%}</td>'
        f'<td>+{aw:.1f}</td><td>{al:.1f}</td>'
        f'<td class="{ash_class}">{ash:.3f}</td>'
        f'<td class="{"bad" if mdd<-500 else "warn"}">{mdd:.0f}</td>'
        f'<td class="{sc_class}">{sc}/8</td></tr>'
    )

html_parts.append('</table>')
html_parts.append('<h2>Key Findings</h2>')
html_parts.append('<div class="stats"><ul>')
html_parts.append('<li><strong class="good">FVG+LS+VM_MAJ h3 Session</strong> — 16 trades, 68.8% WR, Sharpe 2.45, MaxDD -110bps. Best balance of frequency, edge, and risk control.</li>')
html_parts.append('<li><strong>Session filter is essential</strong> — removing it increases MaxDD 2-3x and cuts Sharpe by 40-60%.</li>')
html_parts.append('<li><strong>FVG+VM alone</strong> has highest score (8/8) but only 7 trades in 208 days — statistically unreliable.</li>')
html_parts.append('<li><strong>ORB generates many trades</strong> (450) but tail-dependent and sub-50% win rate — needs confirmation filter.</li>')
html_parts.append('<li><strong>VM alone is random</strong> — 1500+ trades, Sharpe near 0, huge drawdowns.</li>')
html_parts.append('</ul></div>')

html_parts.append('<h2>Price Charts with Trade Markers</h2>')

# Add each figure
for i, fig in enumerate(figures):
    cfg_name, _, _, _, _ = configs[i]
    html_parts.append(f'<div class="chart-container" id="chart{i}"></div>')
    fig_json = fig.to_json()
    html_parts.append(f'<script>Plotly.newPlot("chart{i}", {fig_json}, {{responsive: true}});</script>')

html_parts.append('''
</body>
</html>''')

html_content = '\n'.join(html_parts)
outpath = '/home/anson/factor-lab/reports/combo_backtest_1h_v1.html'
import os
os.makedirs(os.path.dirname(outpath), exist_ok=True)
with open(outpath, 'w') as f:
    f.write(html_content)
print(f"Report saved: {outpath}")
