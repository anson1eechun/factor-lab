---
session_id: SIM-2026-06-07-004
title: 多資產 × 多時框 OOS — Time-Series Momentum (F22 TSMOM)
date: 2026-06-07
kind: 辯論模擬 / 正式 OOS 研究
factor: F22_Time_Series_Momentum
verdict: REJECT (作為 alpha;具防禦 overlay 價值)
assets: BTC, ETH, XAU(黃金), Oil(WTI)
timeframes: 1d, 1w
harness: scripts/multiasset_oos.py
---

# 多資產 TSMOM 正式 OOS 報告(F22)

> 目標:找一個「真能過門檻」的因子,多資產 + 多時框正式 OOS。
> 結論:**沒有過。** 連最穩健的跨資產因子 TSMOM 都被誠實證偽為 long-bias/防禦 overlay。

## 資料(真實)
BTC(Binance 1500)、ETH(Binance 1000)、XAU=GC=F、Oil=CL=F(yfinance,各 ~1500 日線,2020-06~2026-06)。時框:1d、1w(由日線 resample)。

## 因子:F22 TSMOM(多 lookback 混合,波動正規化)
`sig = mean_L( log(C/C_{-L}) / (vol·√L) ).shift(1)`;部位 = sign(sig);波動目標化(只去槓桿);四資產等權組合。日線 L∈{20,60,120,250},週線 {4,12,26,52}。

## 回測(真實)
| | Sharpe | MaxDD | t | IC-IR |
|---|---|---|---|---|
| 日線組合 全期 | 0.07 | −54% | 0.16 | 負 |
| 日線組合 OOS | 0.66 | −28% | 1.03 | 負 |
| 週線組合 全期 | 0.59 | −12.8% | 1.40 | 負 |
| 週線組合 OOS(2024+) | 1.41 | −7.1% | 2.20 | 負 |

乍看週線 OOS 過(Sharpe/MaxDD/t),但——

## 決定性證偽:TSMOM vs Always-Long(同波動目標化)
| 週線組合 | 全期 Sharpe | 2022 熊市 | 2023-26 |
|---|---|---|---|
| TSMOM(擇時)| 0.59 | 0.58(MaxDD −5.7%)| 0.87 |
| **Always-Long(純做多)** | **1.00** | 0.16(MaxDD −14%)| **1.32** |
| 超額(TSMOM − Long) | **−0.43** | — | — |

**TSMOM 全期淨輸給單純做多(超額 Sharpe −0.43)。** 它在 2022 熊市保護下檔(0.58 vs 0.16),但在多頭放棄更多上檔,淨值是負貢獻。OOS 的 1.41 是 2024-25 黃金/BTC 多頭 beta,buy-and-hold 賺更多。

## Skeptic 關鍵批判(成立)
- 多重比較(2 時框 × 多 lookback)選出週線 = data snooping;校正後 t≪2。
- OOS 126 週、資產高相關 → 有效樣本遠小,t=2.2 假精度;全期 t=1.40 才誠實。
- IC≈0、**IC-IR 負 = 直接違反硬門檻**;用 strategy Sharpe 取代是搬龍門。
- edge 是 long-bias × 波動目標化,非擇時 alpha(決定性測試證實)。

## Arbiter 裁決:**REJECT(作為 alpha 因子)**
依 factor-lab 門檻(含 IC-IR>0.3)F22 未過;決定性測試顯示其方向擇時相對 buy-and-hold 為**負超額**。它有「2022 熊市防禦 overlay」價值,但那不是 alpha。

## 對未來研究的價值(重要基準)
**任何宣稱有 alpha 的多資產因子,必須先打贏「Always-Long × 波動目標化」(週線全期 Sharpe ≈ 1.0、MaxDD −14%)這個基準的超額。** 這是本輪最有用的產出:一個誠實的高標竿。

## 三+一輪總結
| 輪 | 因子 | 裁決 |
|---|---|---|
| 1 IIR | 流動性反轉 | REJECT |
| 2 VWTP | 量能動能 | REWORK(borderline)|
| 3 VoVT | 波動二階矩 | REJECT |
| 4 F22 TSMOM | 多資產趨勢 | REJECT(long-bias,非 alpha)|
**目前仍無 validated alpha 因子。** 這是誠實的科學結果,非失敗。
