# EQ-SIM-2026-06-08-002 — v2 辯論:資產成長異象(美股)

**裁決:REJECT(異象在此 universe/期間反轉)** ｜ 股票延伸第二輪。

## 背景
EQ-SIM-001 value 衰減後,轉「較不擁擠」的資產成長異象(Cooper-Gulen-Schill 2008:高總資產成長→後續弱)。
因子=−資產成長(做多低成長)。資料僅需 Assets(覆蓋全),PIT:YoY 由連續 10-K 算、按新報告 filed≤T 對齊。
harness `scripts/eq_asset_growth_eval.py`(月頻、行業中性、含分段衰減)。

## 角色
- **Proposer**:高資產成長(過度投資/擴張)→ 後續報酬弱。S&P500 橫截面月頻。
- **Builder**:annual Assets YoY,新報告 filed 日可得;signal=-growth;行業中性 z。
- **Empiricist(全真實 PIT,143 月)**:

| | IC | IC_t | LS Sharpe | LS_t | 剔5% | 多頭超額 Sh |
|---|---|---|---|---|---|---|
| 行業中性 -growth | −0.0071 | **−1.98** | −0.74 | −2.55 | −1.48 | −1.32 |
| 原始 -growth | −0.0074 | −1.77 | −0.51 | −1.78 | −1.14 | −0.73 |

分段(全部負,非前置):2014-18 IC_t−1.34/LS−0.46;中段 −1.5/−0.93;近段 −0.57/−0.75;近24m −1.5/−0.66。

- **Risk/Skeptic**:IC 顯著**為負** = 高資產成長股**跑贏**(2014-26 成長 regime;經典異象主在含中小型廣 universe 才強,大型股反轉)。
- **Arbiter(獨立)**:**REJECT**。資產成長異象在 S&P500 大型股 2014-26 不成立且反向。**拒絕翻號 claim「做多高成長」**——那是成長 regime 賭注、擁擠、易反轉,屬 sign-mining,違 ledger 紀律。

## 核心發現
1. **經典異象不保證跨 universe 轉移**:Cooper-Gulen-Schill 在廣(含中小型)universe 強,搬到 S&P500 大型股 + 2014-26 成長 regime 就反轉。
2. 與 EQ-SIM-001 合看:**價值族基本面因子(value、資產成長)在大型股近十年成長 regime 全失靈**——value 衰減、資產成長反轉。這是 regime 一致的結果。

## 歸檔
harness 可複用;ledger + index.db(EQ-SIM-002)。下一步:離開價值族,試**品質(Piotroski F-score 複合)**或**應計 accruals**——與價值族正交、regime 依賴較低。
