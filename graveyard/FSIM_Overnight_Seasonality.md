---
factor_id: FSIM_Overnight_Seasonality
name: BTC/ETH Overnight/Weekend 時段季節性
session: SIM-2026-06-10-017
verdict: REJECT
date: 2026-06-10
kind: 辯論模擬
data_dim: crypto intraday seasonality (30m 全史 2017-2026, NYSE 真實日曆)
status: rejected
---

# Overnight/Weekend 時段季節性 — 墓誌

**主張**(外部文獻:Quantpedia/Falkenstein/Bespoke/NGHT ETF):BTC/ETH 報酬集中於美股盤外,
只持盤外可勝 HODL。

**死因**(預登錄判準,confirmatory 兩窗口不掃格):
1. **族C 尾部集中(致命)**:剔最高 5% 盤外日後連零成本 Sharpe 都崩(BTC −1.31 / ETH −1.25);
   全部溢酬由 111/2,218 天扛起。「均值顯著(t≈2.8)」是少數暴漲夜的算術。
2. regime 翻覆:2018/2022/2026 年度淨均值皆負 = 牛市 beta 集中在夜裡,非連續溢酬。
3. BTC maker 2bps 情境淨 Sh 0.76 < HODL 0.82;ETF 後子樣本 t≈1.07 不顯著。
4. 週末窗(t 1.78/2.09)不過 Bonferroni 2.50。

**教訓**:外部「異象」宣稱多為全樣本均值;先問「剔尾部還剩什麼+年度符號穩不穩」。
本場收官 crypto 日內:價量反轉/ICT/訂單流/衍生品定位/季節性全滅,
剩餘路徑僅付費 L2/清算資料 + maker 基礎設施。

詳見 `empirical_runs/SIM-2026-06-10-017_debate_report.md`;資料 `{btc,eth}_30m_full.parquet` 可複用。
