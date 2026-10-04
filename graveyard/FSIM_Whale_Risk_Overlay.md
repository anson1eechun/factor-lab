---
factor_id: FSIM_WRO
name: Whale-Ratio Risk Overlay (BTC de-risking)
session: SIM-2026-06-08-014
verdict: REJECT
date: 2026-06-08
kind: 辯論模擬
data_dim: on-chain overlay (exchange whale ratio)
status: graveyard
---

# Whale-Ratio Risk Overlay — REJECT(REWORK 收尾:延遲診斷後翻案)

## ★收尾結論(2026-06-08,延遲查證後)
**翻案 REWORK→REJECT。** 事件研究 + 資料延遲查證證明:lag=1 的優勢是**偷渡同日(T+0)資訊**,現實不可得。
- **資料延遲(實測)**:JSON `last_modified` 顯示 day-T 的 whale_ratio 在 **T+1 約 01:20 UTC**(收盤後 ~1.2h)才發布;
  且 CryptoQuant 官方定義為 **72h 滾動窗**。故 day-T 值在 day-T 收盤前**根本不存在**。
- **事件研究(z 穿破>1 後 BTC 報酬)**:**T+0 −0.369%/t−2.56(唯一顯著)**、T+1 −0.130%/t−0.83(不顯著)、
  T+2 −0.04、**T+3 +0.215%(反轉)**。→ 訊號與下跌**同時發生**(大戶在跌日充值,指標當天登錄),**非預測**。
- **∴ 可交易窗(T+1 起)無顯著 edge**;lag=1 回測 Sharpe1.17 是同日資訊洩漏,lag=2(現實)超額 Sharpe 轉負。
- **新失敗模式**:「資料延遲型 limits-to-arbitrage」——訊號有真資訊但為**同期**,等可行動時預測內容已成過去。

下方為當初 REWORK 時的記錄(保留供對照)。

---

# Whale-Ratio Risk Overlay — (原 REWORK 記錄)

**機制**:鯨魚往交易所充值比(`btc_exchange_whale_ratio`)z 分數飆高 = 大戶賣壓 →
**long-only 減碼**(降 BTC 曝險,絕不放空)。基準 = buy&hold BTC。資料 `data/onchain/`,harness `scripts/overlay_eval.py`。

## 為何是 REWORK(非 REJECT)— 首個正面訊號
公平窗 2023-02→2026-06(funding/whale 資料齊),10bps 成本,**lag=1**:

| | Sharpe | MaxDD | Calmar | 曝險 |
|---|---|---|---|---|
| buy&hold | 0.866 | −49.8% | 0.697 | 1.00 |
| thr1.0→0 | **0.934** | **−40.6%** | **0.904** | 0.83 |
| 持續 minhold=10 | **1.171** | **−33.8%** | — | 0.44 |

- **Sharpe 與回撤雙贏**(整個程式第一次)。
- 半樣本超額 Sharpe **+0.10 / +0.05**(符號一致)。
- 出場日 buy&hold 平均 **−0.13%** vs 在場日 **+0.16%** → 訊號**有真實資訊**,出場日確實較差。
- funding overlay 失敗、combo 被稀釋 → **whale 才是有效成分**。

## 卡關點(REWORK 的待修項)
1. **lag 致命脆弱**:lag=1 超額 Sharpe +0.15~+0.50;**lag=2 全變負**(0.57~0.76 < 0.866)。
   → **核心待驗**:whale_ratio 日值究竟何時真正可得?若 T+1 收盤前可靠拿到 → 可部署且為最佳結果;
   若需 T+2 → 只剩「降回撤但犧牲 Sharpe」(MaxDD 連 lag=2 都仍 −49.8%→−34.9%)。
2. **多重比較**:thr1.0/minhold=10 為 ~36 組態最佳,邊際 Sharpe 須 deflate。
3. **211 個單日閃動**(原始版)經持續性(minhold)收斂成 60–98 次連貫出場後更穩。
4. 2024 多頭年 overlay 反拖累 CAGR(−13pp)→ regime 依賴。

## 下一步
- 查 whale_ratio 真實資料延遲(CryptoQuant 結算時點);若 T+1 可行,正式進 validated 並擴到 ETH。
- 否則定位為**降回撤工具**(非 Sharpe 提升),搭配 buy&hold 長持。

relates: 同 SIM-008(funding)/SIM-013(鏈上)崩盤風險訊號族,但**首個轉成 overlay 後勝過基準**。
