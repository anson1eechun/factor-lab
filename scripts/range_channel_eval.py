#!/usr/bin/env python3
"""SIM-018 震盪通道回歸評測:BTC/ETH × 15m/30m,扣成本+日聚合t+剔5%+IS/OOS+年度。
預登錄閘門:①淨10bps日聚合t≥2且年化Sh>0.5 ②剔最高5%交易毛利>0 ③IS/OOS同向且OOS>0
④BTC/ETH同向 ⑤Bonferroni N=4。參數零掃描。
跑: uv run --with "numpy>=2" --with pandas --with scipy python scripts/range_channel_eval.py"""
import sys
sys.path.insert(0, "/home/anson/factor-lab")
import numpy as np
import pandas as pd
from scipy import stats
from core.signals.FSIM_Range_Channel_Oscillation import position_series

OOS_SPLIT = pd.Timestamp("2024-07-01")
BPY = {"15m": 365 * 96, "30m": 365 * 48}


def load(asset, tf):
    df = pd.read_pickle(f"empirical_runs/{asset}_{tf}_long.pkl")
    df.index = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def run(asset, tf, cost_rt_list=(0, 4, 10)):
    df = load(asset, tf)
    pos = position_series(df).values
    O = df["open"].values
    # bar i 持有部位賺 open[i]→open[i+1];最後一根無下根,棄之
    o2o = np.empty(len(df)); o2o[:-1] = O[1:] / O[:-1] - 1; o2o[-1] = 0.0
    gross_bar = pos * o2o * 1e4                                   # bps
    side_chg = np.abs(np.diff(pos, prepend=0.0))                  # 每次換邊收單邊成本

    # 逐筆交易(供剔5%/每筆統計)
    trades = []
    i = 0
    while i < len(pos):
        if pos[i] != 0:
            j = i
            while j + 1 < len(pos) and pos[j + 1] == pos[i]:
                j += 1
            x = min(j + 1, len(df) - 1)                           # 出場 bar(open 平倉)
            r = (O[x] / O[i] - 1) * pos[i] * 1e4
            trades.append(dict(entry=df.index[i], bars=x - i, gross=r))
            i = x
        i += 1
    tr = pd.DataFrame(trades)

    out = dict(asset=asset, tf=tf, n_trades=len(tr),
               tim=float((pos != 0).mean()),
               med_hold=float(tr["bars"].median()) if len(tr) else np.nan,
               win=float((tr["gross"] > 0).mean()) if len(tr) else np.nan,
               gross_per_trade=float(tr["gross"].mean()) if len(tr) else np.nan)
    k = max(1, int(len(tr) * 0.05)) if len(tr) else 0
    out["extop5_gross"] = float(np.sort(tr["gross"].values)[:-k].mean()) if len(tr) else np.nan

    day = pd.Series(df.index.date, index=df.index)
    for cb in cost_rt_list:
        net_bar = gross_bar - side_chg * cb / 2
        daily = pd.Series(net_bar, index=df.index).groupby(day.values).sum()
        mu, sd = daily.mean(), daily.std(ddof=1)
        out[f"net{cb}_t"] = float(mu / (sd / np.sqrt(len(daily))))
        out[f"net{cb}_sh"] = float(mu / sd * np.sqrt(365))
        if cb == 10:
            eq = daily.cumsum()
            out["net10_maxdd_bps"] = float((eq - eq.cummax()).min())
            for lab, m in [("is", daily.index < OOS_SPLIT.date()), ("oos", daily.index >= OOS_SPLIT.date())]:
                d2 = daily[m]
                out[f"net10_{lab}_sh"] = float(d2.mean() / d2.std(ddof=1) * np.sqrt(365))
            out["yearly"] = {y: round(float(g.mean() / g.std(ddof=1) * np.sqrt(365)), 2)
                             for y, g in daily.groupby(pd.Index(daily.index).map(lambda d: d.year))}
        if cb == 0:
            out["gross_sh"] = out["net0_sh"]
    # benchmark:always-long 同期日 Sharpe
    bh = pd.Series(o2o * 1e4, index=df.index).groupby(day.values).sum()
    out["bh_sh"] = float(bh.mean() / bh.std(ddof=1) * np.sqrt(365))
    return out


def main():
    res = [run(a, tf) for a in ("btc", "eth") for tf in ("30m", "15m")]
    cols = ["asset", "tf", "n_trades", "tim", "win", "med_hold", "gross_per_trade", "extop5_gross",
            "gross_sh", "net4_sh", "net10_sh", "net10_t", "net10_is_sh", "net10_oos_sh",
            "net10_maxdd_bps", "bh_sh"]
    df = pd.DataFrame(res)
    pd.set_option("display.width", 200)
    print(df[cols].round(2).to_string(index=False))
    for r in res:
        print(f"  {r['asset']} {r['tf']} 年度淨10bps Sharpe: {r['yearly']}")
    # 閘門判定(主規格 = 30m;15m 為預登錄變體)
    print("\n== 預登錄閘門(N=4,Bonferroni 單次 p×4<0.05 ⇒ |t|>2.50)==")
    for r in res:
        g1 = r["net10_t"] >= 2.50 and r["net10_sh"] > 0.5
        g2 = r["extop5_gross"] > 0
        g3 = np.sign(r["net10_is_sh"]) == np.sign(r["net10_oos_sh"]) and r["net10_oos_sh"] > 0
        print(f"  {r['asset']} {r['tf']}: ①淨t/Sh {'過' if g1 else '敗'}({r['net10_t']:.2f}/{r['net10_sh']:.2f}) "
              f"②剔5% {'過' if g2 else '敗'}({r['extop5_gross']:.2f}) ③IS/OOS {'過' if g3 else '敗'}"
              f"({r['net10_is_sh']:.2f}/{r['net10_oos_sh']:.2f})")
    both_pos = all(r["net10_sh"] > 0 for r in res)
    print(f"  ④四組同向皆正: {'過' if both_pos else '敗'}")


if __name__ == "__main__":
    main()
