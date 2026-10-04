# SIM-2026-06-08-011 — v2 辯論:訂單流失衡反轉(Order-Flow Imbalance Reversal)

**裁決:REJECT** ｜ 第一個「新資料維度」(訂單流)實測，仍落入同一陷阱。

## 背景
純 OHLCV/funding 已搜尋到誠實盡頭(10+ 輪)。本輪換**資料維度**:用 Binance K 線第 9 欄
`takerBuyBaseVolume`(免費、免 key)建 **taker 主動買賣失衡** TFI=(buy−sell)/vol，
80 幣日線面板(`empirical_runs/universe_flow_1d.pkl`，`scripts/fetch_orderflow.py`)。

## 角色
- **Proposer**:追高的主動買盤會被收割 → 高 TFI 幣次日相對走弱(橫截面**反轉**)。新維度、零售難套利。
- **Builder**:`core.signals.FSIM_Order_Flow_Imbalance_Reversal`，factor=−z₂₀(TFI)。harness=`scripts/crosssec_flow_eval.py`(剔最高5%日壓測+年度regime)。
- **Empiricist(標準套餐,全真實回測)**:

| 指標 | 數值 | 門檻 | |
|---|---|---|---|
| Rank IC | **+0.0128** | — | 訊號真實 |
| IC t | **+3.42** | — | 統計顯著(1180 日) |
| IC-IR | **0.10** | ≥0.30 | ❌ Gate1 fail |
| 毛利 LS Sharpe(0 成本) | **+0.37** | — | t=0.66 不顯著 |
| **剔最高5%日 LS Sharpe** | **−2.13** | >0 | ❌ 肥尾集中 |
| 淨 LS Sharpe(10bps) | **−3.90** | ≥1.0 | ❌ Gate2 fail |
| 日均換手 | **2.96** | — | 滿倉 2.0 → 雙腿狂churn |
| 日均毛利 | **2.56 bps** | — | |
| **打平成本上限** | **0.86 bps/邊** | — | 實際 5–10bps → 必虧 |
| 年度淨 Sharpe | −3.1/−4.0/−3.6/−6.2 | — | 四年皆深負 |

- **Risk**:換手 2.96/日 → 容量≈0、成本主導;與既有殘差反轉(SIM-009)同源,邊際 Sharpe 扣成本為負,對 book 無增量。
- **Skeptic**:訊號只活在 1 日(ma5 IC→−0.003、hold=5 Sharpe→−0.65),且毛利全靠尾部 5% 日 → 典型 **limits-to-arbitrage**:訊號之所以存在，正因無法被收割。
- **Arbiter(獨立)**:**REJECT**。Gate1(IC-IR 0.10<0.3)、Gate2(淨 Sharpe −3.9)、尾部壓測(−2.13)三項皆敗;打平成本 0.86bps/邊不切實際。ledger 已 ~19 假設,Bonferroni 下 IC t 亦縮水,但**PnL 才是約束點**。

## 核心發現(meta)
**第一個新資料維度(訂單流)在日線仍重現同一結構**:真實反轉訊號、IC-IR≈0.1(<0.3)、毛利尾部集中、換手×成本碾壓薄邊。
→ 與 SIM-007(MAX)、SIM-009(殘差反轉)同一族:**crypto 日線的真訊號幾乎都是反轉型且不可收割**。

**下一步建議**:訂單流 alpha 真正的棲地是**日內微結構**,不是日線。已備 `btc/eth_flow_{15m,1h,4h}.pkl`,
可改做**日內訂單流**(CVD 動量/背離、時段化),那裡 flow 的資訊衰減更慢、成本相對毛利占比更低。
鏈上/清算維度(Coinglass、ErcinDedeoglu/crypto-market-data 免費 BTC 集)為另一條未測路徑。

## 歸檔
- 因子:`core/signals/FSIM_Order_Flow_Imbalance_Reversal.py`(deprecated)
- 墓誌:`graveyard/FSIM_Order_Flow_Imbalance_Reversal.md`
- ledger:`empirical_runs/search_ledger.jsonl` +1
- index.db:debate_sessions / rounds / transcripts +1
