---
slug: F5_anchored_mean_reversion_score
title: "F5: Anchored Mean-Reversion Score (AMRS) — 錨定均值回歸因子"
author: Proposer
created: 2026-05-26
stage: stage_0
status: validated
direction: long_short
verdict: "PASS — 驗證通過。IC-IR 0.65-1.00 全 horizon 一致，累積 IC 穩步上升。與既有因子極低相關。但需解決 must-fix 項目後方可使用。"
target: BTC/USDT, ETH/USDT
timeframe: daily
factors: []
soul_score: 5
verdict_timestamp: "2026-05-26T15:30:00"
dedup_status: pending
category: value
formula: "signal = EMA( (vwap_20 - close) / ATR_14, halflife=5 ) where vwap_20 = SUM(tp*vol,20) / SUM(vol,20), tp = (high+low+close)/3"
implementation: core/signals/F5_Anchored_Mean_Reversion_Score.py
related:
  - "[[arXiv:2605.17299]] GBM intermittent entries — SuperTrend asymmetry 1.8 進出比"
  - "[[2605.13407]] PRISM-VQ 先驗因子 + 學習因子混合"
---

# Hypothesis

在任一時間點，市場存在一個隱含的「公允價格錨點」——以成交量加權平均價格 (VWAP) 近似。價格偏離 VWAP 越遠，均值回歸的引力越強。但不同於傳統布林帶或 RSI 的固定閾值，AMRS 以波動率歸一化偏離幅度，使信號在高低波動率體制下具有可比性。這是一個純價值/均值回歸因子，不依賴趨勢方向或市場協同程度。

# Soul Questions

## Q1 — 為什麼這個 alpha 現在會存在？

加密貨幣市場由散戶主導，其交易行為受錨定效應 (anchoring bias) 強烈影響。投資者傾向以「最近一段時間的平均成交價」作為心理參考點。當價格大幅低於此參考點時，散戶傾向惜售或抄底（供給減少、需求上升）；當價格大幅高於時，散戶傾向獲利了結（供給增加）。這種行為偏差在缺乏基本面估值的 crypto 市場中尤其明顯，且不會因市場成熟而消失（即便在美股中，VWAP 均值回歸效應也是公認的）。

## Q2 — 什麼會殺死它？

1. **強趨勢行情中的均值回歸陷阱**：若 BTC 進入持續數月的單邊上升趨勢（如 2020-2021 牛市），AMRS 會持續發出做空信號。需要與 regime filter（如 complexity_gap_regime）搭配使用以在趨勢市場中抑制信號。
2. **結構性質變（監管/ETF 改變市場參與者結構）**：若機構持倉占比超過 70%，VWAP 錨定效應可能被機構的均值-方差優化行為取代。
3. **極端波動率下的歸一化失效**：若 ATR 在極端行情中爆炸性增長，歸一化後的 AMRS 可能過度壓縮信號幅度，失去區分能力。

## Q3 — 對手方是誰？

**動量交易者 (Momentum Traders)** 和 **突破交易者 (Breakout Traders)**。當 AMRS 做多時（價格低於 VWAP、預期反彈），對手方是仍在拋售的止損單和追逐下跌趨勢的空頭。當 AMRS 做空時，對手方是仍在追高的動量買家。

## Q4 — 一句話描述

價格走得離市場平均成本太遠，終將被引力拉回。

## Q5 — 資料來源

Binance Public API `GET /api/v3/klines` (日線 OHLCV)，透過 `core/adapters/crypto.py` CryptoAdapter 取得。VWAP 使用典型價格 (H+L+C)/3 加權成交量計算。

## Q6 — Alpha 衰減速度

**years**。均值回歸效應是金融市場中最古老、最穩健的異常現象之一（自 Fama & French 以來不斷被驗證）。Crypto 市場的散戶結構使此效應更持久。預期 alpha 半衰期 > 2 年，但信號強度可能在極端趨勢行情中週期性衰減。

# Factor Formula

```
# 1. 典型價格（比收盤價更能代表「市場共識價格」）
typical_price_t = (high_t + low_t + close_t) / 3

# 2. 滾動成交量加權平均價格（20 日 VWAP）
vwap_t = SUM_{i=0}^{19}(typical_price_{t-i} * volume_{t-i}) / SUM_{i=0}^{19}(volume_{t-i})

# 3. 波動率歸一化偏離（核心）
# 正值 = 價格低於 VWAP（低估 → 做多）
# 負值 = 價格高於 VWAP（高估 → 做空）
raw_amrs_t = (vwap_t - close_t) / ATR_t(period=14)

# 4. 訊號平滑（減少噪音）
signal_t = EMA(raw_amrs_t, halflife=5)

# 5. 可選：體制過濾
# 僅在 complexity_gap Δ < 0.05（非趨勢市場）時啟動信號
# 避免在強趨勢行情中與趨勢對抗
```

**經濟機制**：
- 價格低於 VWAP 且偏離幅度大 → AMRS > 0（買入訊號）：市場平均持倉者處於虧損狀態，賣壓枯竭，反彈概率高
- 價格高於 VWAP 且偏離幅度大 → AMRS < 0（賣出訊號）：市場平均持倉者處於獲利狀態，獲利了結壓力累積
- 波動率歸一化確保：在波動率 2% 的盤整市場中，5% 偏離是大信號；在波動率 10% 的趨勢市場中，5% 偏離只是噪音

**與既有因子的相關性預期**：
- vs. SuperTrend (trend): 預期負相關。SuperTrend 在趨勢中做多，AMRS 在同一趨勢中（若價格偏離 VWAP 過遠）可能已開始做空。
- vs. Complexity Gap (regime): 低相關。Complexity Gap 測量全市場協同度，AMRS 測量單資產價格的相對估值。機理正交。
- vs. Volume Weighted Tilt (microstructure): 預期低相關。VWT 使用成交量加權方向，AMRS 使用 VWAP 作為定價錨。兩者都引用成交量但用於完全不同目的。

# Related Work (KB references)

- [[arXiv:2605.17299]] — SuperTrend asymmetry 1.8 進出比：均值回歸因子在出場決策上可借鑒不對稱設計（快速進場、緩慢出場以捕捉回歸的完整區間）。
- [[2605.13407]] — PRISM-VQ：先驗因子 + 學習因子混合架構啟發：AMRS 可作為「先驗因子」與 VQ 學習因子共同運作。
- [[2026-05-25_前沿量化论文-主题索引]] — 論文洞見總索引

# Graveyard References

- **volatility_roughness_filter**：淘汰原因為日線無法捕捉粗糙度。AMRS 不依賴 Hurst 指數或粗糙度特徵，因此在日線層級無相同問題。但淘汰教訓提醒：日線頻率對特定微觀結構現象有結構性限制，AMRS 的 VWAP 在日頻是合理的（不同於 5min 頻率的粗糙度需求）。

# Datasource Issues

- ✅ 日線 OHLCV 完全可得
