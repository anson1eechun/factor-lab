#!/usr/bin/env python3
"""驗證 FVG h12 Session(15M)——照 factor-lab 規格:扣成本 + IS/OOS + 剔5% + 日聚合t + Bonferroni。
FVG 信號與 DeepSeek 原版同參(lb=80,gap=0.2),蘋果對蘋果。"""
import sys; sys.path.insert(0, '/home/anson/factor-lab')
import pandas as pd, numpy as np, json
from scipy import stats
from core.adapters.crypto import CryptoAdapter

adapter = CryptoAdapter()
raw = adapter.get_ohlcv("BTCUSDT", "15m", limit=15000)
raw['dt'] = pd.to_datetime(raw['timestamp'], unit='ms', utc=True)
df = raw.set_index('dt').sort_index()
days = (df.index[-1] - df.index[0]).days
hrs = df.index.hour.values
hi_liq = ((hrs >= 0) & (hrs < 4)) | ((hrs >= 7) & (hrs < 10)) | ((hrs >= 12) & (hrs < 16))
print(f"15M {len(df)} bars | {df.index[0].date()}→{df.index[-1].date()} | {days}d", flush=True)


def fvg_signal(df, lb=80, gap=0.2):                       # 與 DeepSeek 原版逐字相同
    H = df["high"].values; L = df["low"].values; C = df["close"].values
    n = len(df); sig = np.zeros(n); zones = []
    for i in range(2, n):
        g = C[i] * gap / 100.0
        if L[i-2]-H[i] > g: zones.append((i, H[i], L[i-2], +1))
        if L[i]-H[i-2] > g: zones.append((i, H[i-2], L[i], -1))
        zones = [z for z in zones if i-z[0] <= lb]
        bull = bear = 0; unmit = []
        for ii, bt_, tp, d in zones:
            if d == +1:
                if L[i] <= tp and L[i] >= bt_: bear -= 1
                else: unmit.append((ii, bt_, tp, d))
            else:
                if H[i] >= bt_ and H[i] <= tp: bull += 1
                else: unmit.append((ii, bt_, tp, d))
        zones = unmit; net = bull+bear
        if net != 0: sig[i] = np.sign(net)
    sig[:lb+2] = np.nan; sig[-1] = 0
    return pd.Series(sig, index=df.index)


def trades(sig, df, h, smask, cost_bps):
    s = sig.values; O = df["open"].values; n = len(df); R = []; ENT = []
    for i in range(n-h-1):
        if np.isnan(s[i]) or s[i] == 0: continue
        if smask is not None and not smask[i]: continue
        d = s[i]; eb = i+1; xb = i+1+h
        if xb >= n: continue
        ep = O[eb]; xp = O[xb]
        r = (xp/ep-1)*10000 if d == 1 else (1-xp/ep)*10000
        R.append(r - cost_bps); ENT.append(df.index[eb])
    return np.array(R), pd.DatetimeIndex(ENT)


def stat(R):
    n = len(R); mr = R.mean(); sr = R.std(ddof=1)
    t = mr/(sr/np.sqrt(n)) if sr > 0 else 0
    p = 2*(1-stats.t.cdf(abs(t), n-1)) if n > 1 and sr > 0 else 1.0
    tpy = n/len(df)*365*96; ash = (mr/sr)*np.sqrt(tpy) if sr > 0 else 0   # 每筆年化(會被重疊高估)
    return n, mr, t, p, ash


fvg = fvg_signal(df, 80, 0.2)
print("\n=== A. 成本敏感度(全樣本,h=12,Session)===")
print(f"{'cost(來回bps)':>14}{'筆數':>6}{'每筆淨bps':>10}{'每筆t':>7}{'p':>8}{'年化Sh(高估)':>14}")
for cb in [0, 6, 10, 12]:
    R, ENT = trades(fvg, df, 12, hi_liq, cb)
    n, mr, t, p, ash = stat(R)
    print(f"{cb:>14}{n:>6}{mr:>10.2f}{t:>7.2f}{p:>8.3f}{ash:>14.2f}")

R10, ENT10 = trades(fvg, df, 12, hi_liq, 10)
print("\n=== B. 日聚合顯著性(治重疊持倉,較誠實)@10bps ===")
daily = pd.Series(R10, index=ENT10).groupby(ENT10.date).sum()
dn = len(daily); dt_ = daily.mean()/(daily.std(ddof=1)/np.sqrt(dn))
dp = 2*(1-stats.t.cdf(abs(dt_), dn-1))
dsh = daily.mean()/daily.std(ddof=1)*np.sqrt(365)
print(f"  交易日數={dn}  日均P&L={daily.mean():.2f}bps  日聚合t={dt_:.2f}  p={dp:.3f}  日Sharpe(年化)={dsh:.2f}")

print("\n=== C. IS/OOS 切半 @10bps ===")
mid = df.index[len(df)//2]
for lab, m in [("IS前半", ENT10 < mid), ("OOS後半", ENT10 >= mid)]:
    Rh = R10[m]
    if len(Rh) > 1:
        n, mr, t, p, ash = stat(Rh)
        print(f"  {lab}: 筆數={n} 每筆淨={mr:.2f}bps t={t:.2f} p={p:.3f} 年化Sh={ash:.2f}")

print("\n=== D. 剔最高5%交易壓測 @10bps ===")
k = max(1, int(len(R10)*0.05))
cut = np.sort(R10)[:-k]
n, mr, t, p, ash = stat(cut)
print(f"  剔掉最賺的{k}筆後: 筆數={n} 每筆淨={mr:.2f}bps t={t:.2f} 年化Sh={ash:.2f}")
print(f"  (原全樣本 {len(R10)} 筆每筆淨 {R10.mean():.2f}bps)")

print("\n=== E. 多重比較(Bonferroni,160 組)===")
from scipy.stats import t as tdist
bonf_t = tdist.ppf(1-0.05/160/2, len(R10)-1)
print(f"  全家族 5% 顯著需 per-trade t > {bonf_t:.2f}(160 次檢定)")
n, mr, t, p, ash = stat(R10)
print(f"  FVG h12 S 實際 per-trade t = {t:.2f} → {'通過' if t > bonf_t else '遠不達標'}")
