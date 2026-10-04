---
session_id: SIM-2026-06-07-006
title: v2 橫截面辯論 — Idiosyncratic Oversold Reversal (IOR)
date: 2026-06-07
kind: 辯論模擬 (v2, cross-sectional)
factor: FSIM_Idiosyncratic_Oversold_Reversal
verdict: REJECT
universe: 20 USDT coins (BTC..TRX), 1d, 2023-02~2026-06
harness: scripts/crosssec_eval.py
---
# v2 橫截面辯論報告 — IOR
首個橫截面 v2 辯論。IC/IC-IR/Mono 門檻在此真正適用。
## Proposer
IOR = 自身波動標準化短期反轉 + 放量恐慌 + 下影吸籌,加性 z-score 合成(避乘法翻號)。
## Empiricist(crosssec 標準套餐,真實)
| 版本 | IC | IC-IR | ic_t | LS Sharpe gross | net(10bps) | Mono |
|---|---|---|---|---|---|---|
| 原版 | 0.0066 | 0.025 | 0.83 | −1.22 | −2.44 | −0.70 |
| 翻號 | −0.0066 | −0.025 | −0.83 | +1.22 | **−0.011** | +0.70 |
- 原版反轉假設證偽(Mono −0.7,quintile 報酬遞減,超賣幣續弱)。
- 翻號=橫截面動能(已知弱);gross 1.22 → **net 歸零**(每日換手成本全吃)。
## Skeptic / Risk
IC 太弱(0.0066<0.02)兩方向皆然;翻號=事後挑方向(ledger 第6假設);首個橫截面無同類 book,翻號版機制等同已知動能無增量。
## 獨立 Arbiter 裁決:REJECT
Gate1 全敗;假設證偽;翻號扣成本歸零。
## 核心教訓(重要)
**每日橫截面 rebalance 的 crypto 因子,薄 gross edge 會被交易成本全吃**(IOR 翻號 gross 1.22 → net −0.01)。真橫截面 alpha 需要:更強 IC(>0.02)、更低換手、或更長持有期。

---
## 持有期 rework(2026-06-07,新增 hold 參數)
測同一 IOR 訊號、降換手(每 H 天才 rebalance):
| H | 翻號(XS動能) net Sharpe | 原版 net Sharpe |
|---|---|---|
| 1 | −0.011 | −2.44 |
| 5 | **0.384** | −1.40 |
| 10 | **0.387** | −0.89 |
| 20 | 0.195 | −0.45 |
**發現**:降換手把翻號版 net Sharpe 從 ~0 救到 ~0.39(成本確為主要拖累)。**但 Gate1 仍失敗**(IC-IR −0.025、|IC| 0.0066≈0),且 0.39<0.5。
**結論(維持 REJECT)**:降低換手是**必要但不充分**——底層橫截面訊號(IC≈0)太弱;Mono 0.7 只是 quintile 極端的微弱單調,daily cross-sectional rank 是雜訊。
**下一步真正需要**:更強的 base IC(>0.02)的橫截面訊號,再配低換手。harness 已支援 `hold` 參數供後續用。
