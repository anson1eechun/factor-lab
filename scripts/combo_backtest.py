#!/usr/bin/env python
"""Multi-signal trade-level backtest — 1H BTCUSDT"""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
sys.path.insert(0, '/home/anson/factor-lab/core/signals')
import pandas as pd, numpy as np, json
from scipy import stats
from core.adapters.crypto import CryptoAdapter

adapter = CryptoAdapter()
raw = adapter.get_ohlcv("BTCUSDT", "1h", limit=5000)
raw['dt'] = pd.to_datetime(raw['timestamp'], unit='ms', utc=True)
df = raw.set_index('dt').sort_index()
print(f"1H: {len(df)} bars | {df.index[0]} → {df.index[-1]} | {(df.index[-1]-df.index[0]).days}d", flush=True)

hrs = df.index.hour.values
hi_liq = ((hrs>=0)&(hrs<4)) | ((hrs>=7)&(hrs<10)) | ((hrs>=12)&(hrs<16))
print(f"HighLiq: {hi_liq.sum()}/{len(hi_liq)} ({hi_liq.mean()*100:.1f}%)", flush=True)

# ======= SIGNALS =======
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
    # Find session starts: 23→0, 6→7, 11→12
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

# Generate
print("Generating signals...", flush=True)
fvg = fvg_signal(df); ls = ls_signal(df); vm = vm_signal(df); orb = orb_signal(df)
for n,s in [('FVG',fvg),('LS',ls),('VM',vm),('ORB',orb)]:
    a=((s.fillna(0)!=0)).sum(); print(f"  {n}: {a} ({a/len(s)*100:.1f}%)", flush=True)

# ======= COMBINERS =======
def and_sig(*sigs):
    a=np.column_stack([s.fillna(0).values for s in sigs])
    sn=np.sign(a); ok=np.all(sn==sn[:,0:1],axis=1)
    return pd.Series(np.where(ok,sn[:,0],0).astype(float),index=sigs[0].index)

def maj_sig(*sigs):
    a=np.column_stack([s.fillna(0).values for s in sigs])
    v=a.sum(axis=1)
    return pd.Series(np.where(np.abs(v)>=2, np.sign(v), 0).astype(float), index=sigs[0].index)

# ======= BACKTEST =======
BPD=24

def bt(sig_s, df, h, name, smask=None):
    s=sig_s.values; O=df["open"].values; n=len(df)
    tr=[]
    for i in range(n-h-1):
        if np.isnan(s[i]) or s[i]==0: continue
        if smask is not None and not smask[i]: continue
        d=s[i]; eb=i+1; xb=i+1+h
        if xb>=n: continue
        ep=O[eb]; xp=O[xb]
        r=(xp/ep-1)*10000 if d==1 else (1-xp/ep)*10000
        tr.append({'eb':int(eb),'xb':int(xb),'d':int(d),'r':float(r)})
    if len(tr)<5:
        return {'name':name,'err':f'n={len(tr)}'}
    R=np.array([t['r'] for t in tr])
    D=np.array([t['d'] for t in tr])
    nt=len(R); nw=(R>0).sum(); nl=(R<0).sum()
    wr=nw/nt; aw=R[R>0].mean() if nw>0 else 0; al=R[R<0].mean() if nl>0 else 0
    pf=abs(R[R>0].sum()/R[R<0].sum()) if nl>0 else 99
    mr=R.mean(); sr=R.std(); ts=mr/sr if sr>0 else 0
    tpy=nt/len(df)*365*BPD; ash=ts*np.sqrt(tpy) if tpy>0 else 0
    k=max(1,int(nt*0.05)); sr2=np.sort(R)
    t5=sr2[:-k].mean() if k>0 else mr
    b5=sr2[k:].mean() if k>0 else mr
    pd=((mr-t5)/abs(mr)*100) if mr!=0 else 0
    eq=np.cumsum(R); pk=np.maximum.accumulate(eq); mdd=(eq-pk).min()
    tip=nt*h/(n-h-1)*100
    LR=R[D==1]; SR=R[D==-1]
    lwr=(LR>0).mean() if len(LR)>0 else 0
    swr=(SR>0).mean() if len(SR)>0 else 0
    tstat=mr/(sr/np.sqrt(nt)) if sr>0 and nt>1 else 0
    pv=2*(1-stats.t.cdf(abs(tstat),nt-1)) if nt>1 and sr>0 else 1.0
    sc=0
    if wr>0.50: sc+=1
    if ash>0: sc+=1
    if t5>0: sc+=1
    if b5>0: sc+=1
    if pv<0.05: sc+=1
    if mdd>-500: sc+=1
    if isinstance(pf,(int,float)) and pf>1.3: sc+=1
    if aw>abs(al): sc+=1
    return {'name':name,'h':h,'nt':int(nt),'nL':int(len(LR)),'nS':int(len(SR)),
            'wr':float(wr),'aw':float(aw),'al':float(al),'mr':float(mr),
            'pf':float(pf) if isinstance(pf,(int,float)) else 99,'ash':float(ash),
            't5':float(t5),'b5':float(b5),'pd':float(pd),'mdd':float(mdd),'tip':float(tip),
            'lwr':float(lwr),'swr':float(swr),'t':float(tstat),'pv':float(pv),'sc':sc}

# ======= BUILD COMBOS =======
combos = {}
for k,v in [('FVG',fvg),('LS',ls),('VM',vm),('ORB',orb)]:
    combos[k]=[v]
# Pairs
combos['FVG+LS_AND']=[fvg,ls]; combos['FVG+VM_AND']=[fvg,vm]
combos['LS+VM_AND']=[ls,vm]
combos['FVG+LS_MAJ']=[fvg,ls]; combos['FVG+VM_MAJ']=[fvg,vm]
combos['LS+VM_MAJ']=[ls,vm]
# Triples
combos['FVG+LS+VM_AND']=[fvg,ls,vm]; combos['FVG+LS+VM_MAJ']=[fvg,ls,vm]
combos['FVG+VM+ORB_MAJ']=[fvg,vm,orb]; combos['LS+VM+ORB_MAJ']=[ls,vm,orb]
# All
combos['ALL_MAJ']=[fvg,ls,vm,orb]; combos['ALL_AND']=[fvg,ls,vm,orb]

H=[1,2,3,6,12]
results=[]
for cname,slist in combos.items():
    if cname.endswith('_AND'):
        sig=and_sig(*slist)
    elif cname.endswith('_MAJ'):
        sig=maj_sig(*slist)
    else:
        sig=slist[0]
    na=((sig.fillna(0)!=0)).sum()
    for h in H:
        rraw=bt(sig,df,h,f'{cname}_h{h}_R',None)
        rses=bt(sig,df,h,f'{cname}_h{h}_S',hi_liq)
        for r in [rraw,rses]:
            if 'err' not in r:
                r['na']=int(na)
                results.append(r)

results.sort(key=lambda x:x['sc'],reverse=True)

# Print
print(f"\n{'='*155}")
print(f"TRADE-LEVEL MULTI-SIGNAL — 1H BTCUSDT ({len(df)} bars, {(df.index[-1]-df.index[0]).days}d)")
print(f"{'='*155}")
print(f"{'Config':<30s} h  Tr   WinRate  AvgW   AvgL   Mean   PF   AnnSh T5drop  MaxDD  T%  Sc")
print(f"{'-'*155}")
for r in results[:45]:
    print(f"{r['name']:<30s} {r['h']:>2d} {r['nt']:>4d} {r['wr']:>8.4f} {r['aw']:>+7.1f} {r['al']:>+6.1f} {r['mr']:>+8.2f} {r['pf']:>5.2f} {r['ash']:>+7.3f} {r['pd']:>+7.1f}% {r['mdd']:>+7.0f} {r['tip']:>4.1f}% {r['sc']:>2d}")

best=results[0]
print(f"\n--- BEST: {best['name']} ---")
print(f"Trades={best['nt']}({best['nL']}L/{best['nS']}S) WR={best['wr']:.2%} LWR={best['lwr']:.2%} SWR={best['swr']:.2%}")
print(f"AvgW={best['aw']:+.1f}bps AvgL={best['al']:+.1f}bps PF={best['pf']:.2f}")
print(f"AnnSharpe={best['ash']:.3f} Top5Drop={best['pd']:+.1f}% MaxDD={best['mdd']:.0f}bps")
print(f"t={best['t']:.3f} p={best['pv']:.4f} Score={best['sc']}/8")

# Save results
with open('/tmp/combo_results.json','w') as f:
    json.dump([{k:v for k,v in r.items() if k!='err'} for r in results], f, default=str)
print("\nSaved /tmp/combo_results.json")
