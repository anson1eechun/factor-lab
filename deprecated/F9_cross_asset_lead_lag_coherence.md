---
date: 2026-05-26
status: deprecated
rejection_date: 2026-05-27
rejection_session: f7-f9-debate-20260527
category: cross_asset
formula: "coherence_t = Pearson(BTC_ret[t-W:t], ETH_ret[t-W:t]); signal_t = sign(BTC_ret_t) × coherence_t × |BTC_ret_t|; active when |coherence_t| > 0.7; silent when |coherence_t| < 0.4 or |Δcoherence_t| > 0.3"
implementation: core/signals/F9_cross_asset_lead_lag_coherence.py
hypothesis: BTC 作為 crypto 市場 beta 錨點，其日級報酬對 ETH 次日報酬有非對稱資訊傳導；當 BTC↔ETH 滾動 coherence 高時，BTC_t 報酬可預測 ETH_{t+1}，提供截面 lead-lag alpha。
expected_effect: long
applicable_markets: [crypto]
derived_from: [[2605.11645-geomherd-ricci-flow, 2605.13407-prism-vq]]
complements: [[super_trend_10_3, anchored_mean_reversion_score]]
related_risks: [coherence regime 切換, BTC dominance 結構性下降]
soul_questions:
  Q1_structural_reason: "BTC 是 crypto market beta，機構與大戶先交易 BTC 再 rebalance ETH，產生 1-2 日延遲傳導。流動性集中於 BTC 而非 ETH。"
  Q2_data_quality: "需 BTC/ETH 日線 + USD 報酬；CryptoAdapter 已備；歷史 7+ 年；無倖存者偏誤。"
  Q3_parameter_freedom: "3 參數：coherence 視窗、lag 步長、coherence 門檻。均有經濟錨點。"
  Q4_extreme_behavior: "極端行情 BTC/ETH 同步崩盤、coherence 反而上升但 lead-lag 縮短至日內，日線因子失效。需 regime 過濾。"
  Q5_competition: "stat-arb 基金已挖掘 lead-lag，但日線級且帶 coherence 過濾的版本相對少見。"
  Q6_failure_conditions: "BTC dominance < 35% 或 ETH 主導 DeFi 形成獨立流動性循環，lead-lag 反轉。"
---

# cross_asset_lead_lag_coherence

## 假設 (hypothesis)
BTC 作為 crypto 市場的「市值與流動性錨」（BTC dominance 約 50-55%），具有**資訊先發優勢**：

1. 機構配置者（ETF、家族辦公室、CTA）首先在 BTC 建倉，因為 BTC 流動性最深、衍生品工具最完整、託管最成熟
2. 之後才 rebalance 至 ETH（因為 ETH 流動性次之、敘事彈性更強）
3. 此「先 BTC 後 ETH」的順序在 1-2 日尺度上**穩定可觀測**

**訊號設計**：
```
coherence_t = ρ(BTC_returns[t-60:t], ETH_returns[t-60:t])  # rolling 60d Pearson
lead_lag_signal_t = sign(BTC_return_t) × coherence_t × |BTC_return_t|
```

- 當 |coherence| > 0.7 且 BTC_t 為正：long ETH_{t+1}
- 當 |coherence| > 0.7 且 BTC_t 為負：short ETH_{t+1}（或平倉）
- 當 |coherence| < 0.4：ETH 進入「獨立 regime」（如 DeFi 季、L2 敘事），暫停訊號

**經濟直覺**：coherence 高 = 機構 beta 模式啟動 → BTC lead；coherence 低 = ETH 獨立敘事 → 訊號失效。這是 **state-conditional alpha**，符合論文 2605.13407 PRISM-VQ 「先驗因子 + 條件化 regime」設計思想。

## 預期方向與適用條件
- 適用市場：BTC（觀察）、ETH（交易）；後續可擴展至 SOL、BNB 等高 coherence 標的
- 預期效果：long ETH（多空雙向，但 long bias 因 crypto long-term drift）
- 適用時機：coherence 高 regime（約佔 60-70% 時間）
- **最低數據頻率需求：日線即可。若有 4H 數據可改良為 lead 步長更短**

