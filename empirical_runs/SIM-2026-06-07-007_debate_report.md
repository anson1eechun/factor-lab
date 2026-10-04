---
session_id: SIM-2026-06-07-007
title: v2 橫截面 — Cross-Sectional Lottery (XLOT)
date: 2026-06-07
kind: 辯論模擬 (v2, cross-sectional, 洞見庫驅動)
factor: FSIM_Cross_Sectional_Lottery_Aversion
verdict: REJECT (但為目前最佳線索)
universe: 20 USDT coins 1d
harness: scripts/crosssec_eval.py (hold 持有期)
---
# v2 橫截面辯論 — XLOT(lottery/skew,洞見庫驅動)
## 來源
從 242 條洞見挖出 lottery/heavy-tail 機制(Bali MAX 效應 + crypto 橫截面論文 OOS 1.55)。
## Proposer
XLOT=-(z(MAX21)+z(RSKEW60)+z(IRANGE21)),加性,預期 lottery-aversion 正 IC。
## Empiricist(crosssec + hold,真實)
| 方向 | hold | net Sharpe | IC-IR | ic_t | Mono |
|---|---|---|---|---|---|
| aversion(原版) | 1/10 | −1.56/−1.41 | +0.068 | **+2.18** | −0.6 |
| lottery-demand(翻號) | 5/10/20 | 1.03/1.12/1.16 | −0.068 | −2.18 | +0.6 |
子期間(翻號 hold10):前半 2.17 → 後半 0.34(集中前半)。
## 關鍵
- aversion 假設**證偽**(crypto 彩券幣 outperform,與股市相反)。
- 翻號=lottery-demand:市場中性 net Sharpe ~1.1(非 long-bias),**但 Gate1 IC-IR 失敗 + Sharpe正/IC負矛盾(極端撐、非單調)+ 事後翻號 + 子期間不穩**。
- **唯一 base IC 顯著(ic_t 2.18)的因子** → lottery 是目前最佳機制線索。
## 獨立 Arbiter:REJECT
Gate1 全敗;翻號多重比較;Sharpe-IC 矛盾;regime 集中。
## REWORK 方向(若續做)
乾淨單調的 lottery 建構、降極端依賴、regime-robust、非重疊驗證 + 多重比較校正。

---
## REWORK(單調化 + regime 驗證,2026-06-07,真實)
拆解 XLOT 三子項(lottery-demand 方向),各自 IC 都顯著為負 → **aversion 才對**:
| 子項 | ic_t | 解讀 |
|---|---|---|
| MAX | −5.26 | 高 MAX→未來弱(極顯著)|
| IRANGE | −5.78 | 高振幅→未來弱 |
| SKEW | −2.96 | 右偏→未來弱(較雜)|
蒸餾成 **MAX-aversion**(signal=−MAX):
- IC-IR **+0.153**、ic_t **+5.26**;**子期間 前半 +0.149 / 後半 +0.157(regime-stable!)**
- 但 net LS Sharpe 最佳 0.19、Mono −0.7 → 廣義 rank IC 正但 quintile 極端反向(尾部雜訊)
**REWORK 複判:仍未 VALIDATE**(IC-IR 0.153<0.3、Sharpe<0.5、Mono 敗)。
**但這是 8 輪來最真實、最穩健的橫截面訊號**(crypto MAX lottery-aversion 確實存在且跨期穩定);失敗在「真訊號太弱(IC-IR<0.3)+ LS 極端無法乾淨收割」。保留 `FSIM_MAX_Lottery_Aversion` 為候選最佳線索。

---
## REWORK (1) rank-weighted 收割(2026-06-07,真實)
用全體幣橫截面 rank 線性加權(市場中性)取代 quintile 極端多空:
| H | net Sharpe |
|---|---|
| 1 | −0.63 |
| 5 | −0.22 |
| 10 | −0.05 |
| 20 | +0.19 |
子期間(H10):前半 −0.13 / 後半 +0.58(非兩半皆正)。
**結論:收割方法不是瓶頸。** 即使 H=20(最低換手)也僅 +0.19;ic_t 5.26 是長期累積顯著,但**單日 IC 0.0187 經濟量太薄**,quintile 與 rank-weighted 在 20 幣 + 成本下都榨不出 Sharpe>0.5。IC 穩定但 PnL 被尾部主導(IC≠PnL)。
**真正的槓桿 = universe 廣度**(20→50+ 幣,同樣 IC 可收割更多、IC-IR 通常上升),而非收割法。維持 REWORK。

---
## 擴 universe(80 幣)+ 最終診斷(2026-06-07,真實)
universe 20 → **80 幣**(Binance,66 滿 1200bar)。重測 MAX-aversion:
- **IC-IR 0.153 → 0.228**(ic_t 7.84;前半 0.273/後半 0.219)→ **breadth 確實拉高 IC-IR(方向正確)**。
- **但 LS/rank-weighted PnL 仍全負**(quintile −0.28~−1.0、rank-w −0.36~−0.81)。
- 只做多低 MAX vs 等權全市場:**超額 Sharpe −0.5**(避開彩券幣反而輸)。

### 致命且深刻的診斷:IC≠dollar-PnL(肥右尾)
- rank IC 正(高 MAX 幣**多數**排名偏低)但 dollar PnL 負,因為高 MAX 彩券幣**會暴漲(肥右尾)**:放空它們 → 暴漲時大賠;只做多低 MAX → 錯過暴漲者也輸。
- 兩邊自洽:這是「排序層真異象、美元層不可收割」。**lottery 溢酬能持續正因為它不可套利(limits-to-arbitrage)。**

### 最終裁決:REJECT(不可交易),但機制完全釐清
MAX lottery-aversion 是 8 輪來唯一**真實、顯著、regime-stable 且 breadth 會增強**的訊號,但**結構上不可用 long-short / long-only 收割**。breadth 槓桿對 IC-IR 有效(0.153→0.228),但救不了 dollar-PnL 的肥尾問題。
### 收穫
確認:(1) 擴 universe 確實提升 IC-IR(基礎設施升級到 80 幣,對未來所有橫截面因子有用);(2) 真正瓶頸是 lottery 的不可套利性,非收割法、非 universe 大小。
