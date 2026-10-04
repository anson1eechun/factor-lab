---
session_id: SIM-2026-06-07-008
title: 換資料維度 — Funding Rate Carry(資料源解決 + 首個新維度因子)
date: 2026-06-07
kind: 資料維度探索 (v2)
factor: Funding Carry (FSIM_FUNDCARRY)
verdict: REWORK (最佳線索;新資料維度有真 alpha)
universe: 79 幣 funding + 80 幣 spot, 2023~2026
data: empirical_runs/funding_1d.pkl (scripts/fetch_funding.py)
---
# 換資料維度 — Funding Rate Carry
## 資料源解決(關鍵)
**駁回「funding 僅 67 天」**:那是當初沒帶 startTime(預設只回 ~200 筆≈67天)。`/fapi/v1/fundingRate` 帶 startTime 分頁可回溯至 2019 上市。已抓 **79 幣 funding 全史(~1255 日,2022-12~2026-06)** → `funding_1d.pkl`。factor-lab 長期資料瓶頸解除。
- OI:`openInterestHist` 確為硬限 30 天,難回測。鏈上/訂單簿:需付費/即時,無免費歷史。
## Funding Carry 因子(放空高 funding 幣 = signal -funding)
cross-sectional,經濟先驗明確(高 funding=多頭擁擠/付費→偏空)。
| 變體 | IC-IR | ic_t | net Sharpe(H10,10bps) |
|---|---|---|---|
| -funding raw | 0.066 | 2.29 | 0.81 |
| **-funding 7d mean** | 0.081 | 2.80 | **0.78(rank-w)** |
| -funding 30d | 0.053 | 1.85 | −0.04 |
成本:0/5/10/20bps → Sharpe 1.08/0.93/0.78/0.48(扛得住成本)。
## 穩定性
兩半都正(前 0.42 / 後 0.85);但分三段 2024 −1.0、2025-26 +2.25(regime 依賴)。
## 裁決:REWORK(最佳線索)
**整段(8輪 OHLCV + 此輪)唯一 net Sharpe>0.5 市場中性、扛成本、兩半皆正的因子**,且在**全新資料維度**。但未乾淨過門檻:IC-IR 0.081<0.3、t 1.42<2、MaxDD 44%>30%、2024 為負。
## REWORK 路線
1. 波動目標化壓 44% 回撤;2. 結合 funding **變化/動能**(非僅 level)分散 regime;3. 加 OI/basis 維度;4. 更長史 + 更多幣提 IC-IR、t。
## 結論
**「換資料維度」假設成立**:funding 比任何 OHLCV 因子強。新維度是對的方向。

---
## REWORK(vol-target + funding 動能,2026-06-07,真實)
- **funding 動能**(signal=-(funding 3d−21d),rising→short)+ 只去槓桿 vol-target:
  Sharpe **1.03**、MaxDD **−0.27**(過)、t 1.87(借線)、三段 −0.22/+1.94/+1.48(修掉 level 版的 −1.0 災難)、**drop-one-coin 穩(最低 0.87)**、對 OHLCV 因子正交。
- **獨立 Arbiter 裁 REWORK**:Gate1 IC-IR 0.029 仍掛、t<2;要求時段穩定壓力測試。
- **壓力測試(決定性)**:剔除報酬最高 **5% 交易日 → Sharpe −1.64**(60 天扛全部 edge);剔 1% → 0.32。
  → **edge 集中在 ~5% 大事件日**,與 IC-IR≈0 自洽:**funding 動能是尾部/事件型策略(funding 飆升/爆倉日暴賺),非穩健橫截面 alpha**。
## 最終裁決:REWORK(不可作為穩健 alpha;為事件型 edge)

> **[2026-07-04 加註,SIM-2026-07-04-002 Arbiter 裁定]** best-lead 證據強度正式下修:本報告 net 0.971/0.78 的窗口 = 舊 universe_1d tail(1200) 恰起於 2023-02-24 之窗口運氣(躲過 2023 年 1-2 月);自然窗(2023-01-01 起)net 0.455 / ls_t 0.85,2023 全年 net −0.55。backward-OOS(2020-10-19~2022-12-31)證偽:剔尾後 body 日均 −28bps 與收租相悖、空腿年化 −0.92。**funding-level XS carry 已列 do-not-revisit(家族關線)**,詳見 [[SIM-2026-07-04-002_debate_report]] 與 `deprecated/FSIM_FundingCarry.md`。本加註不翻案(當時資訊下程序有效),僅下修證據強度。
## 整段最終結論
換資料維度(funding)確實比 OHLCV 有更多訊號,但嚴格壓力測試後**仍無 robust validated alpha**:
- OHLCV:多數 IC≈0;唯一強訊號(MAX-lottery)肥尾不可套利。
- Funding:carry/動能 Sharpe 看似 0.8–1.0,但 IC-IR≈0 + edge 尾部集中(5% 日)。
**v2 流程(獨立 Arbiter + 壓力測試)成功攔下這個 Sharpe 1.0 的假陽性**——最強的流程驗證。
