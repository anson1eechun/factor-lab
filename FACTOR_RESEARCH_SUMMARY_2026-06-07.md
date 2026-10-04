> ⛔ **已被取代 / SUPERSEDED**:本文為 06-07 階段快照,最終定稿見 `NEGATIVE_RESULTS_REPORT_2026-06-08.md`(狀態 CLOSED)。

---
title: 因子研究階段總結 — 多代理 v2 辯論 + 資料維度探索
date: 2026-06-07
scope: SIM-2026-06-07-001 ~ 008(8 場辯論 + 多輪 rework,13 個假設)
status: 階段收尾;無 validated robust alpha,但基礎設施與方法論完備、資料源打通
---

# 因子研究階段總結(2026-06-07)

## 0. 一句話結論
用多代理 v2 辯論流程嚴格篩了 **13 個因子假設**(8 場辯論),**沒有一個通過嚴謹門檻成為 robust alpha**;但**這是嚴謹的科學結論而非失敗**——流程成功攔下多個誘人的假陽性(最關鍵:funding 動能 Sharpe 1.03 被壓力測試揭穿是 5% 尾部日撐的),同時**打通了長期卡住的 funding 資料源**、建立完整橫截面/多時框/成本回測基礎設施,並蒸餾出明確的「真 alpha 規格」。

---

## 1. 所有嘗試(search ledger,13 假設)

| # | 因子 | 類型 | 機制 | net Sharpe | IC-IR | 裁決 |
|---|---|---|---|---|---|---|
| 1 | IIR | directional | Amihud 流動性反轉 | − | −0.08 | REJECT |
| 2 | VWTP | directional | 量能動能延續 | 0.60 | −0.22 | REWORK(long-bias overlay)|
| 3 | VoVT | directional | 波動二階矩擇時 | − | 0.10 | REJECT |
| 4 | F22 TSMOM | directional/多資產 | 時序動能趨勢 | 0.18 | − | REJECT(long-bias)|
| 5 | DVRP | directional | 下行半變異數 | − | 0.16 | REJECT(假設反向)|
| 6 | IOR | cross-sec | 特異超賣反轉 | −2.44 | 0.025 | REJECT |
| 6b| IOR-flip | cross-sec | 橫截面動能 | 0.39 | −0.025 | REJECT(成本吃光)|
| 7 | XLOT | cross-sec | lottery/MAX/skew | 1.12 | −0.068 | REJECT(Sharpe/IC矛盾、regime)|
| 7b| MAX-aversion | cross-sec | MAX lottery 排序 | 0.19 | **0.228** | REJECT(肥尾不可套利)|
| 8 | Funding Carry | cross-sec | 高 funding→空 | **0.78** | 0.081 | REWORK(最佳線索)|
| 8b| Funding Momentum | cross-sec | funding 上升→空 | **1.03** | 0.029 | REWORK(尾部事件型)|

(資產涵蓋:BTC/ETH/XAU/Oil + 80 幣 crypto universe;時框 5m–4h/1d/1w;全部扣交易成本。)

---

## 2. 方法論(v2 多代理辯論流程)
Skill:`~/.claude/skills/factor-lab-debate/SKILL.md`(v2.1)。7 角色:
**Proposer → Builder →(主代理)Empiricist 標準套餐 → Risk → Skeptic →(獨立子代理)Arbiter → Librarian**。

**鐵則**:不要假資料(主代理獨立重跑驗證);裁判與選手分離(Arbiter 獨立、不知主代理期望);多重比較必登錄(search ledger,Bonferroni deflate)。

**門檻(分兩套)**:
- 橫截面:`|IC|>0.02 · IC-IR>0.3 · Sharpe>0.5 · MaxDD<30% · t≥2 · Mono≥0.7`
- 方向型:`net Sharpe>0.5 · 對 Always-Long 超額>0 · MaxDD<30% · t≥2 · Mono≥0.7`
- **雙閘門**:Gate1 訊號品質 `IC-IR≥0.3` + Gate2 交易品質 `Sharpe≥1.0 或 Mono≥0.7`,兩閘都過才 VALIDATE。

**Empiricist 標準套餐**:基礎 IC → 非重疊 IC+t → 子期間/regime 分解 → 對 naive benchmark 超額 → 成本後淨值 → 多資產/多時框 → 登錄 ledger。

---

## 3. 核心發現(深刻教訓)
1. **純 OHLCV 因子幾乎都 IC≈0**:動能/反轉/波動/流動性/趨勢/半變異數,單日橫截面 IC 接近雜訊,薄 edge 被成本吃光。
2. **唯一強的 OHLCV 訊號(MAX lottery-aversion)不可套利**:ic_t −5.26 極顯著、IC-IR 隨 universe 擴大而升(0.153→0.228),但**排序層真、美元層假**——高 MAX 彩券幣肥右尾暴漲,放空大賠、做多錯過。limits-to-arbitrage 正是它能持續的原因。
3. **方向型因子多為 long-bias 偽裝**:必須對「Always-Long × vol-target」算超額才能識破(VWTP/F22 超額 ≤0)。
4. **訊號品質 ≠ 交易品質(IC≠PnL)反覆出現**:XLOT、funding-mom 都 Sharpe 漂亮但 IC-IR≈0 → 雙閘門專治此症。
5. **每日橫截面 rebalance 被成本殺**:降換手(持有期 5–10)能救回部分 net Sharpe,但救不了弱訊號。
6. **universe 廣度提升 IC-IR**:20→80 幣使 MAX-aversion IC-IR 0.153→0.228(方向正確,但非瓶頸)。
7. **換資料維度才是 alpha 真來源**:funding(非 OHLCV)立刻給出整段最高 Sharpe(0.78–1.03),驗證方向。
8. **但 funding edge 是尾部事件型**:funding 動能 Sharpe 1.03,剔除最高 5% 交易日 → −1.64;edge 集中在少數爆倉/funding 飆升日,非穩健 alpha。
9. **獨立 Arbiter + 壓力測試是流程的關鍵價值**:funding-mom drop-one-coin 穩、Sharpe 1.0、MaxDD 27%,差點被當成 validated;獨立 Arbiter 逼出時段壓測才揭穿。

---

## 4. 真 alpha 規格(本階段蒸餾)
一個可上線的因子必須**同時**滿足:
1. **base IC 真且穩**:IC-IR ≥ 0.3(非僅 ic_t 顯著);跨子期間同號。
2. **非尾部集中**:剔除最高 5% 交易日後 Sharpe 仍 > 0(block-bootstrap / 逐月分解)。
3. **扛成本**:net of 10bps/邊 後 Sharpe > 0.5;換手可控(持有期或平滑)。
4. **可套利**:dollar-PnL 與 rank-IC 同向(非 MAX 那種肥尾不可空)。
5. **regime-robust**:無單一年/單一時段獨撐;市場中性(非 long-bias)。
6. **對 book 有增量**:與既有因子低相關、邊際 Sharpe > 0;不依賴單一標的。
7. **多重比較校正後仍顯著**(search ledger Bonferroni)。

---

## 5. 基礎設施(本階段建置,可複用)
**資料**(`empirical_runs/`):
- `universe_1d.pkl` — 80 幣 USDT 日線(2023–2026)
- `funding_1d.pkl` — **79 幣 funding 全史(~1255 日)** ← 解開長期瓶頸
- `xau_1d.pkl` / `oil_1d.pkl` — 黃金/原油(yfinance)
- `{btc,eth}_{5m,15m,30m,45m,1h,3h,4h}.pkl` — crypto intraday

**Harness/腳本**(`scripts/`):
- `debate_sim_eval.py` — 單資產 IC/Sharpe/IC-IR/Mono/t
- `crosssec_eval.py` — 橫截面(IC-IR/Mono/LS/rank-weighted/成本/持有期 hold/freq)
- `multiasset_oos.py` — 多資產×多時框 OOS + 成本
- `backtest_timeseries.py` — 完整時序+逐筆交易+成本+多資產+多時框(控制台用)
- `fetch_universe.py` / `fetch_funding.py` / `fetch_intraday.py` — 資料抓取
- `funding_carry_eval.py` — funding 因子評估

**資料源結論**:funding ✅ 全史可抓(`/fapi/v1/fundingRate` + startTime 分頁;「67 天」是當初沒分頁的誤會)。OI ❌ 硬限 30 天。鏈上/訂單簿 ❌ 無免費歷史。

**控制台**(Balaena Quant,localhost:8900):Mission Control / Processes / **Backtest(多資產×7時框×成本×K線進出場×逐筆)** / KB Explorer;因子 17、辯論 10、洞見 242。

**知識庫**:`paper_insights` 3 → **242**(從 309 篇筆記批次抽取)。

---

## 6. 最佳線索 + 下一步
**最佳線索**:funding 維度(carry/動能)——整段唯一 Sharpe 接近 1、市場中性、新資料維度。
**但**:funding 動能是**尾部事件型**(5% 日撐全部 edge),不是穩健橫截面 alpha。

**建議方向(擇一)**:
1. **funding 當事件型策略 / 風控**:用 funding 動能預測爆倉/連環清算日(它本來就在那賺),做事件型或 tail-risk overlay,而非常態橫截面因子。
2. **funding × basis / OI(近 30 天)多維**:組合期現價差、OI 變化,找非尾部的穩態 carry。
3. **更廣 universe + 更長 funding 史** 重驗 funding carry 的 IC-IR(目前 0.081,擴幣或許上 0.3)。
4. **收束**:接受純量價/funding 在此資料下無 robust alpha,基礎設施已備,轉做組合/執行工程或等待新資料維度(鏈上 API)。

---

## 7. 誠實的底線
- **沒有找到可上線的 robust alpha。**
- 但**流程是對的、嚴謹的**:13 個假設無一蒙混過關,每個 REJECT/REWORK 都有真實數據與明確理由,假陽性(尤其 funding-mom Sharpe 1.0)被獨立 Arbiter + 壓力測試精準攔下。
- **真正的產出是能力**:可重用的多資產/多時框/含成本/橫截面回測基礎設施 + 嚴謹的 v2 辯論方法論 + 打通的 funding 資料源 + 242 條洞見 + 一份明確的「真 alpha 規格」。
- 下次有新資料維度(funding 已開、鏈上待開)或新機制時,這套基礎設施能讓評估又快又誠實。

— 歸檔者:主代理(Claude Code)+ Proposer/Builder/Skeptic/Arbiter 子代理

---
## 補充(2026-06-08,SIM-009 + 殘差反轉低換手)
- SIM-009 RMC 殘差動能:假設證偽(crypto 特異報酬均值回歸);翻號殘差反轉 IC-IR +0.111 顯著穩定(第二強),低換手(H=60)net Sharpe 轉正 +0.29,**但剔最高5%日→−2.80(尾部集中)、末段負** → REJECT。
- **強化的 meta-結論**:跨 9 輪 + 多 rework,**所有顯示正 Sharpe 的 crypto 價量/funding 橫截面訊號,剔除最高 5% 交易日後都崩**(funding-mom 1.03→−1.64、殘差反轉 0.29→−2.80)。真訊號(IC-IR 0.1–0.23)存在但**PnL 一律由少數尾部日撐**,非廣布穩健 alpha。「剔5%日壓測」是最一致的判別器。
- **結論定調**:純價量/funding + 此資料,無 robust broad alpha。要突破必須換資料維度(鏈上/訂單簿,需付費 API)或改目標(事件型策略/風控/組合執行)。

---
## 補充(2026-06-08,尾部訊號→事件/風控 overlay 測試)
試把尾部訊號轉成風控 overlay(aggregate funding 極端時減碼):
- **失敗**:EW 市場 buy-hold Sharpe 0.25 → overlay −0.2;BTC 0.87 → 0.70–0.75(皆變差)。
- **預測力反向**:高 aggregate funding(z>1)後 5 日 EW 報酬 **+1.82%**(續漲)、低 funding −0.01% → **高 funding 是 risk-on/續漲訊號,非崩盤預兆**;減碼=砍掉牛市。
- 結論:funding 尾部 edge 是**橫截面/特定幣特定日**的,**無法轉成乾淨的市場擇時/風控 overlay**。

## 最終定調(階段結束)
9 場辯論 + 多輪 rework + 風控 overlay 測試:
- **無 robust broad alpha**(純價量/funding + 此資料)。
- **無可用的常態風控 overlay**(aggregate funding 擇時反向失敗)。
- 真訊號(IC-IR 0.1–0.23、ic_t 顯著)**存在但不可收割**:或肥尾不可套利(MAX)、或尾部日集中(funding-mom/殘差反轉)、或被成本吃(動能/反轉)。
- **「剔最高 5% 交易日」壓測**是貫穿全程最一致的判別器,擋下所有假陽性。
**要突破唯有換資料維度(鏈上/訂單簿,需付費 API)。** 本階段正式收束;基礎設施、方法論、資料源、結論全部歸檔可複用。
status: CLOSED(2026-06-08)
