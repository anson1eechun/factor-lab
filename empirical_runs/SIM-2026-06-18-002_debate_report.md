---
session: SIM-2026-06-18-002
kind: 辯論模擬
factor: FSIM_CalmStreak
type: cross-sectional
verdict: REJECT
date: 2026-06-18
---

# 因子辯論報告 — FSIM_CalmStreak(低波動 regime 持續度)

**Session** `SIM-2026-06-18-002` · **裁決 REJECT(換題)** · 80 幣加密 universe(2023-02~2026-06)
靈感:精讀 **"Volatility Forecasting and Return Prediction under Market Regimes"(arXiv 2606.09478)** —「報酬可預測性集中在低波動 regime」。

## 1. Proposer
- 假設:幣處於**穩定持續的低波動 regime** → 後續報酬訊號較不被噪音淹沒、溫和續漲。**Long 高分(calm 久且壓縮深)、short 剛離高波動者**。
- 自承失敗模式:可能只是 low-vol anomaly 代理 / size 代理 / 方向反轉(calm=拋售前死寂)。

## 2. Builder
- `core/signals/FSIM_CalmStreak.py`:vr=RV_5/RV_60,120d 百分位 <0.40 算 calm,raw=連續 calm 天數×(1+壓縮深度),shift(1)。逐幣可算。
- 防前視:去末列重算 byte-identical(diff 0)。

## 3. Empiricist(主代理親跑,稀疏訊號容錯 eval)

| 時框 | Rank IC | IC-IR | IC t | LS Sharpe(net) | LS t | Mono | 非重疊 IC t (n) | regime |
|---|---|---|---|---|---|---|---|---|
| **1d** | -0.0001 | -0.0009 | -0.028 | **-2.223** | -3.715 | **-0.9** | -0.324 (198) | 前 +0.0135 / 後 -0.001(變號),兩半 Sharpe 皆負 |
| **1w** | — | — | — | — | — | — | — | 暖機 180 週 > 可用 171 週 → 全 NaN 無法評估 |

- quintile_fwd(1d)= [0.00091(Q1 非calm), 0.00022, 0.00056, 0.00007, **-0.00005(Q5 最calm)**] → **calm 幣系統性跑輸,假設方向反了**。
- calm_frac 平均 0.393(非過度稀疏)。

### 對照組(關鍵診斷)
- **純 low-vol(-RV60)**:Rank IC +0.0568、IC-IR **0.2055**、IC t **6.93** — low-vol 異常的 IC 是真的;**但 LS Sharpe -0.203、Mono -0.2 → 不可 LS 變現**。
- 相關:CalmStreak vs 純low-vol **-0.142**、vs log成交額 0.052 → **既沒繼承 low-vol 的真 IC,也不是 size 代理,只是把弱訊號攪成噪音**。

## 4. Risk/Portfolio
單獨 net Sharpe -2.223、IC≈0、regime 變號 → 邊際 Sharpe ≤0;反向版=已知 1d 短期反轉(book 的 IOR 已涵蓋),無增量。

## 5. Skeptic
方向被 Mono -0.9 完全證偽;反向僅已知短期反轉且 regime 內變號;同源 low-vol 本就不可 LS 變現,CalmStreak 與它相關僅 -0.14=噪音放大;1w 暖機超長無法評估=構造問題。REJECT。

## 6. Arbiter(獨立子代理,未被告知期望)
**REJECT(換題,非 REWORK)。** 雙閘門兩道全滅(Gate1 IC-IR≈0 且符號錯、Gate2 Sharpe -2.22/Mono -0.9);|RankIC|/t≥2 deflation 前已純噪音;regime 變號;與母訊號既不繼承(corr -0.14)也不獨立;1w 構造性無法評估。問題在構造本身,非參數可修。

## 7. Librarian
報告本檔;因子筆記 `deprecated/FSIM_CalmStreak.md`;ledger +3(1d/對照/1w-N/A);index.db session+7 transcripts+arbiter round;factors→deprecated。

## 多重比較登錄(ledger N)
本 session 真實變體 1d(1w N/A、對照組為 comparator 非變體)。

## 教訓 / 可收割的線索
- **方向被乾淨證偽**:在 crypto 1d 橫截面,**剛離開高波動的幣前瞻報酬最好、最 calm 的最差** → 這是短期反轉(高波動後均值回復),非「calm premium」。
- **有價值的副產品**:純 low-vol 在此 universe 有**真實 IC(IC-IR 0.21、t 6.93)但無法 LS 變現**(Mono -0.2)。下次若要做 low-vol,應試 **long-only 低波動 tilt / 風險加權** 而非 quintile LS——LS 把不可做空的小幣噪音灌進來。這條線索值得另立新題,但 CalmStreak 這個「持續度×深度」構造到此為止。
