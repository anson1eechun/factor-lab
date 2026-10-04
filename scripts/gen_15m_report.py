#!/usr/bin/env python3
"""Generate HTML report for 15M FVG h=12 Session"""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
import pandas as pd, numpy as np, json, plotly.graph_objects as go
from plotly.subplots import make_subplots
from core.adapters.crypto import CryptoAdapter

adapter = CryptoAdapter()
raw = adapter.get_ohlcv("BTCUSDT", "15m", limit=15000)
raw['dt'] = pd.to_datetime(raw['timestamp'], unit='ms', utc=True)
df = raw.set_index('dt').sort_index()

# Signal: FVG
def fvg_signal(df, lb=80, gap=0.2):
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

fvg = fvg_signal(df)
hrs = df.index.hour.values
hi_liq = ((hrs>=0)&(hrs<4)) | ((hrs>=7)&(hrs<10)) | ((hrs>=12)&(hrs<16))

def simulate(sig_s, df, h, mask):
    s=sig_s.values; O=df["open"].values; C=df["close"].values
    H=df["high"].values; L=df["low"].values; n=len(df)
    tr=[]
    for i in range(n-h-1):
        if np.isnan(s[i]) or s[i]==0: continue
        if not mask[i]: continue
        d=s[i]; eb=int(i+1); xb=int(i+1+h)
        if xb>=n: continue
        ep=O[eb]; xp=O[xb]
        r=(xp/ep-1)*10000 if d>0 else (1-xp/ep)*10000
        tr.append({'entry_i':eb,'exit_i':xb,'entry_p':float(ep),'exit_p':float(xp),
                    'dir':int(d),'r':float(r),'entry_t':str(df.index[eb]),
                    'exit_t':str(df.index[xb])})
    return tr

trades = simulate(fvg, df, h=12, mask=hi_liq)
R = np.array([t['r'] for t in trades])
eq = np.cumsum(R)
pk = np.maximum.accumulate(eq)
dd = eq - pk
nw = int((R>0).sum()); nl = int((R<0).sum())
wr = nw/len(R) if len(R)>0 else 0
aw = R[R>0].mean() if nw>0 else 0; al = R[R<0].mean() if nl>0 else 0
pf = abs(R[R>0].sum()/R[R<0].sum()) if nl>0 and R[R<0].sum()!=0 else 99
mr = R.mean(); sr = R.std(ddof=1)
ash = mr/sr*np.sqrt(len(R)/(len(df)*15/60/24/365)) if sr>0 else 0
mdd = dd.min()

# Plot
disp_start = max(0, trades[0]['entry_i']-200)
disp_end = min(len(df), trades[-1]['exit_i']+50)
dfp = df.iloc[disp_start:disp_end].copy()
idx = dfp.index

fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.55,0.25,0.20],
    vertical_spacing=0.05,
    subplot_titles=('BTCUSDT 15M + FVG h=12 Session Entries', 'Equity Curve (bps)', 'Drawdown (bps)'))

candlestick = go.Candlestick(x=idx, open=dfp.open, high=dfp.high, low=dfp.low, close=dfp.close,
    name='BTC', increasing_line_color='#26a69a', decreasing_line_color='#ef5350')
fig.add_trace(candlestick, row=1, col=1)

# Entry/exit markers
tr_disp = [t for t in trades if disp_start <= t['entry_i'] <= disp_end]
longs = [t for t in tr_disp if t['dir']>0]
shorts = [t for t in tr_disp if t['dir']<0]
if longs:
    fig.add_trace(go.Scatter(x=[df.index[t['entry_i']] for t in longs],
        y=[t['entry_p'] for t in longs], mode='markers', name='Long Entry',
        marker=dict(symbol='triangle-up',size=12,color='#00e676',line=dict(width=1,color='white'))), row=1,col=1)
    fig.add_trace(go.Scatter(x=[df.index[t['exit_i']] for t in longs],
        y=[t['exit_p'] for t in longs], mode='markers', name='Long Exit',
        marker=dict(symbol='circle',size=7,color='#00e676')), row=1,col=1)
if shorts:
    fig.add_trace(go.Scatter(x=[df.index[t['entry_i']] for t in shorts],
        y=[t['entry_p'] for t in shorts], mode='markers', name='Short Entry',
        marker=dict(symbol='triangle-down',size=12,color='#ff1744',line=dict(width=1,color='white'))), row=1,col=1)
    fig.add_trace(go.Scatter(x=[df.index[t['exit_i']] for t in shorts],
        y=[t['exit_p'] for t in shorts], mode='markers', name='Short Exit',
        marker=dict(symbol='circle',size=7,color='#ff1744')), row=1,col=1)

# Equity
eqx = [df.index[min(len(df)-1,trades[0]['entry_i'])]] + [df.index[min(len(df)-1,t['exit_i'])] for t in trades]
eqy = [0.0] + list(eq)
fig.add_trace(go.Scatter(x=eqx, y=eqy, mode='lines', name='Equity',
    line=dict(color='#42a5f5',width=2), fill='tozeroy', fillcolor='rgba(66,165,245,0.1)'), row=2,col=1)
fig.add_hline(y=0, line_dash='dash', line_color='gray', row=2, col=1)

# Drawdown
ddx = eqx; ddy = [0.0] + list(dd)
fig.add_trace(go.Scatter(x=ddx, y=ddy, mode='lines', name='Drawdown',
    line=dict(color='#ef5350',width=2), fill='tozeroy', fillcolor='rgba(239,83,80,0.15)'), row=3,col=1)
mdp = dd.argmin()
fig.add_annotation(x=ddx[mdp+1] if mdp+1 < len(ddx) else ddx[-1], y=ddy[mdp+1] if mdp+1 < len(ddy) else ddy[-1],
    text=f'MaxDD: {mdd:.0f}bps', showarrow=True, arrowhead=2, font=dict(color='#ef5350',size=11),
    row=3, col=1)

fig.update_layout(
    template='plotly_dark',
    height=1000,
    title=dict(text=f'<b>BTCUSDT 15M — FVG h=12 Session</b><br><sub>{len(trades)} trades · {wr:.1%} WR · W/L={aw:+.0f}/{al:+.0f} · PF={pf:.2f} · AnnSharpe={ash:.2f} · MaxDD={mdd:.0f}bps · {df.index[0].date()} → {df.index[-1].date()}</sub>',
               font=dict(size=14)),
    hovermode='x unified',
    margin=dict(l=40,r=20,t=80,b=40),
)
fig.update_xaxes(rangeslider_visible=False, row=1,col=1)
fig.update_yaxes(title_text='Price', row=1,col=1)
fig.update_yaxes(title_text='Equity (bps)', row=2,col=1)
fig.update_yaxes(title_text='DD (bps)', row=3,col=1)

path = '/home/anson/factor-lab/reports/combo_backtest_15m_fvg_h12_S.html'
fig.write_html(path)
print(f"Wrote {path}")

# Also generate the best MAJ combo report
trades2 = simulate(fvg, df, h=4, mask=hi_liq)  # FVG h=4 session (close to FVG+VM_MAJ but simpler)
R2 = np.array([t['r'] for t in trades2])
eq2 = np.cumsum(R2); dd2 = eq2 - np.maximum.accumulate(eq2)
nw2 = int((R2>0).sum()); nl2 = int((R2<0).sum())
wr2 = nw2/len(R2) if len(R2)>0 else 0
pf2 = abs(R2[R2>0].sum()/R2[R2<0].sum()) if nl2>0 and R2[R2<0].sum()!=0 else 99
mr2 = R2.mean(); sr2 = R2.std(ddof=1)
ash2 = mr2/sr2*np.sqrt(len(R2)/(len(df)*15/60/24/365)) if sr2>0 else 0
mdd2 = dd2.min()

disp_start2 = max(0, trades2[0]['entry_i']-200)
disp_end2 = min(len(df), trades2[-1]['exit_i']+50)
dfp2 = df.iloc[disp_start2:disp_end2].copy()
idx2 = dfp2.index

fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True,
    row_heights=[0.55,0.25,0.20], vertical_spacing=0.05,
    subplot_titles=('BTCUSDT 15M + FVG h=4 Session Entries', 'Equity Curve (bps)', 'Drawdown (bps)'))
fig2.add_trace(go.Candlestick(x=idx2, open=dfp2.open, high=dfp2.high, low=dfp2.low, close=dfp2.close,
    name='BTC', increasing_line_color='#26a69a', decreasing_line_color='#ef5350'), row=1,col=1)
tr2_disp = [t for t in trades2 if disp_start2 <= t['entry_i'] <= disp_end2]
longs2 = [t for t in tr2_disp if t['dir']>0]; shorts2 = [t for t in tr2_disp if t['dir']<0]
if longs2:
    fig2.add_trace(go.Scatter(x=[df.index[t['entry_i']] for t in longs2], y=[t['entry_p'] for t in longs2],
        mode='markers',name='Long',marker=dict(symbol='triangle-up',size=10,color='#00e676')), row=1,col=1)
if shorts2:
    fig2.add_trace(go.Scatter(x=[df.index[t['entry_i']] for t in shorts2], y=[t['entry_p'] for t in shorts2],
        mode='markers',name='Short',marker=dict(symbol='triangle-down',size=10,color='#ff1744')), row=1,col=1)
eqx2 = [df.index[min(len(df)-1,trades2[0]['entry_i'])]] + [df.index[min(len(df)-1,t['exit_i'])] for t in trades2]
fig2.add_trace(go.Scatter(x=eqx2, y=[0.0]+list(eq2), mode='lines',name='Equity',
    line=dict(color='#42a5f5',width=2),fill='tozeroy',fillcolor='rgba(66,165,245,0.1)'), row=2,col=1)
fig2.add_hline(y=0, line_dash='dash', line_color='gray', row=2, col=1)
ddx2 = eqx2
fig2.add_trace(go.Scatter(x=ddx2, y=[0.0]+list(dd2), mode='lines',name='DD',
    line=dict(color='#ef5350',width=2),fill='tozeroy',fillcolor='rgba(239,83,80,0.15)'), row=3,col=1)
fig2.update_layout(
    template='plotly_dark', height=1000,
    title=dict(text=f'<b>BTCUSDT 15M — FVG h=4 Session</b><br><sub>{len(trades2)} trades · {wr2:.1%} WR · PF={pf2:.2f} · AnnSharpe={ash2:.2f} · MaxDD={mdd2:.0f}bps</sub>',
               font=dict(size=14)),
    hovermode='x unified', margin=dict(l=40,r=20,t=80,b=40),
)
fig2.update_xaxes(rangeslider_visible=False, row=1,col=1)
path2 = '/home/anson/factor-lab/reports/combo_backtest_15m_fvg_h4_S.html'
fig2.write_html(path2)
print(f"Wrote {path2}")
