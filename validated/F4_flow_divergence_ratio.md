---
slug: F4_flow_divergence_ratio
title: "F4: Flow Divergence Ratio (FDR) — 流量發散因子"
author: Proposer
created: 2026-05-26
stage: stage_0
status: conditionally_validated
direction: long_short
target: BTC/USDT, ETH/USDT
timeframe: daily
factors: []
soul_score: 5
verdict_timestamp: "2026-05-26T15:30:00"
dedup_status: pending
category: flow
formula: "signal = -EMA( price_mom_z * vol_mom_z, halflife=10 ) where price_mom_z = rolling_zscore( EMA(Δclose,5), 60 ), vol_mom_z = rolling_zscore( EMA(Δvolume,5), 60 )"
implementation: core/signals/F4_Flow_Divergence_Ratio.py
related:
  - "[[2605.12977]] 暫態統計因子 / 流量概念移植"
  - "[[2605.11423]] 缺口維度與成交量互補"
---

# Hypothesis

永續的價格趨勢需要持續增長的資金流入來支撐。當價格持續上升（或下降）但成交量反而萎縮時，表示推動趨勢的資金流正在枯竭 —— 這是一種「趨勢燃料不足」的訊號，預示趨勢衰竭與潛在反轉。FDR 透過捕捉價格動量與成交量動量之間的**協同衰減 (co-decay)** 來量化此效應，不依賴價格絕對水平或趨勢方向。

# Soul Questions

## Q1 — 為什麼這個 alpha 現在會存在？

加密貨幣市場缺乏造市商強制報價義務，流動性具有高度週期性。當投機資金集中流入（如 ETF 新聞驅動）時，價格快速推升但市場深度未同步擴張，導致價格-成交量協同關係在極端行情下系統性斷裂。FDR 捕捉的是微觀結構層面的流動性/資金流衰減，這在傳統股票市場（有正式造市商）中較不明顯，因此是 crypto 特有的結構性 alpha。

## Q2 — 什麼會殺死它？

1. **交易所引進強制造市商制度**：若 Binance 等主要交易所要求所有交易對配備正式做市商，流動性週期性將大幅減弱。
2. **全市場成交量操縱**：若清洗交易 (wash trading) 氾濫到使成交量失去資訊含量，FDR 的成交量輸入將完全變成噪音。
3. **極端事件期間的同步崩潰**：如 3·12、5·19 等級別的全市場恐慌拋售中，價格和成交量會同時暴跌（非背離），FDR 信號可能滯後。

## Q3 — 對手方是誰？

**高頻做市商 (HFT Market Makers)** 和 **趨勢跟隨 CTAs**。當 FDR 做空（趨勢衰竭訊號）時，對手方是仍持有多頭部位的趨勢追隨者（他們在價格見頂時仍在買入）；當 FDR 做多（資金流回暖訊號）時，對手方是過早平倉的空頭。

## Q4 — 一句話描述

當價格持續走高但成交量悄悄退潮，趨勢即將擱淺。

## Q5 — 資料來源

Binance Public API `GET /api/v3/klines` (日線 OHLCV)，透過 `core/adapters/crypto.py` CryptoAdapter 取得。無需外部資料源。

## Q6 — Alpha 衰減速度

**months**。流動性週期衰減是市場微結構的結構性特徵，不會因少數交易者利用而消失。但若大型做市商（如 Jump、Wintermute）針對此信號調整做市行為，可能導致成交量-價格領先關係偏移，預期 alpha 半衰期約 6-12 個月。

# Factor Formula

```
# 1. 價格動量（短期指數加權回報）
price_mom_t = EMA(close_t - close_{t-1}, halflife=5)

