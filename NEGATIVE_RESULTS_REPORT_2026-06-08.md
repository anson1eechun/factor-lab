# Factor-Lab 因子研究 — 負面結果總報告
**期間** 2026-06-05 → 2026-06-08 ｜ **狀態** ✅ CLOSED(2026-06-08 正式收尾)｜ **結果** 0 validated alpha / 4 資料維度全證偽

> **階段正式關閉**:17 場辯論、23 條假設、四維度、三族死法、七道驗收交叉驗證後,
> 接受「免費資料 + 單因子/組合方法無可收割連續 alpha」之結論。基礎設施與規格保留,
> 待未來付費資料(Coinglass/Tardis/多幣鏈上橫截面)進場時即用。

> 這是一份**負面結果報告**。它的價值不在於找到 alpha,而在於用誠實、可重現的流程,
> 證明「在免費可得的資料上、用單因子/規則型方法」這條搜尋樹已被探盡,並把**為什麼失敗**
> 拆解成可複用的鑑別工具與失敗模式分類學,供未來省去重走冤枉路。

---

## 1. 摘要

- **17 場辯論 / 23 條登錄假設,validated = 0。** 每一個看似有望的候選最終都被攔下。
- **測過四個資料維度**:① 價量 OHLCV(單資產/橫截面/日內)② Funding rate ③ 訂單流(taker 失衡/CVD)④ 鏈上(交易所淨流/清算/whale/miner)。**全部證偽。**
- 真訊號**確實存在**(多個 t>2~3),但無一是**可收割的連續 alpha**。失敗集中在三種結構性原因(見 §4)。
- **方法論收穫**:v2 流程(獨立 Arbiter + 標準套餐 + search ledger)+ 三把鑑別器,連續攔下 7 個假陽性。這套「怎麼證偽」本身是可複用資產。

---

## 2. 範圍與方法

**流程(v2)**:Proposer → Builder → Empiricist(標準套餐)→ Risk → Skeptic → **獨立 Arbiter** → Librarian。
獨立 Arbiter 只看數字+門檻+ledger、不知主代理偏好,治「裁判兼選手」。

**雙門檻(不可搬龍門)**
- 橫截面型:Gate1 IC-IR ≥ 0.30
- 方向/overlay 型:Gate2 扣成本 Sharpe ≥ 1.0(或 vs 基準雙贏)
- 共同:非尾部集中(剔最高5%日仍正)+ 扛 10bps + 可套利(dollar 與 rank-IC 同向)+ regime 穩 + 多重比較校正後仍顯著。

**全真實回測**(無前視、扣成本)。系統無 pandas,一律 `uv run --with "numpy>=2" --with pandas --with scipy`。

---

## 3. 全結果表(17 場 / 23 假設)

| Session | 因子 | 維度 | 關鍵數字 | 裁決 | 死因族 |
|---|---|---|---|---|---|
| DEB-001 | F1–F3 | 價量 | — | REJECT×2 | 無訊號 |
| DEB-f6f7f10 | F6/F7/F10 K線結構 | 價量 | — | REJECT | 無訊號 |
| SIM-001 | Illiquidity-Impact Reversal | 價量 | IC≈0 | REJECT | 無訊號 |
| SIM-002 | Volume-Weighted Trend Persist | 價量 | 邊際 | REWORK→棄 | 無訊號 |
| SIM-003 | Vol-of-Vol Timing | 價量 | IC≈0 | REJECT | 無訊號 |
| SIM-004 | Time-Series Momentum (F22) | 多資產 | OOS 無效 | REJECT | 無訊號 |
| SIM-005 | Downside Vol Risk Premium | 價量 | 弱 | REJECT | 無訊號 |
| SIM-006 | Idiosyncratic Oversold Rev | 橫截面 | IC≈0;翻號亦敗 | REJECT | 無訊號 |
| SIM-007 | Cross-Sectional Lottery / MAX | 橫截面 | **真排序異象**但樂透不可套利;擴80幣敗 | REJECT | 反轉/不可套利 |
| SIM-008 | Funding Carry / Momentum | Funding | net Sharpe 0.78~1.03 但**剔5%日→−1.64** | REWORK→棄 | 事件/尾部 |
| SIM-009 | Residual Momentum / Reversal | 橫截面 | 殘差反轉 Sharpe0.29,**剔5%日−2.80** | REJECT | 反轉+尾部 |
| SIM-010 | Overnight-Session Drift Rev | 日內 | 兩方向扣成本皆負 | REJECT | 無訊號 |
| SIM-011 | Order-Flow Imbalance Reversal | 訂單流 | IC+0.0128/**t3.42**;IC-IR0.10;**打平0.86bps**;剔5%−2.13 | REJECT | 反轉+成本 |
| SIM-012 | Intraday CVD / TFI reversal | 訂單流 | CVD動量無edge;TFI反轉毛+6.5但**剔5%−23**=bid-ask bounce | REJECT | 反轉+微結構 |
| SIM-013 | On-chain Supply / Liquidations | 鏈上 | 清算無edge;whale **t−2.31**最強但多重比較+剔5%−2.66 | REJECT | 事件/尾部 |
| SIM-014 | Whale-Ratio Risk Overlay | 鏈上overlay | lag=1似雙贏(Sh1.17)但**事件研究僅T+0顯著**=同期非預測 | REWORK→**REJECT** | **資料延遲** |
| SIM-015 | Multi-factor Combo(反轉+事件) | 橫截面組合 | 正交佳;STR+MAX **IC-IR0.31過Gate1**但**毛Sharpe−0.79** | REJECT | IC-IR/PnL 脫鉤 |

**最接近的兩個**:SIM-008 Funding Momentum(整段最佳 net Sharpe,死於尾部)、SIM-014 Whale Overlay(唯一一度勝基準,死於資料延遲)。

---

## 4. 失敗模式分類學(本研究的核心產出)

四維度全敗,但**死法分三族**——這是比「沒找到 alpha」更有用的結論:

### 族 A — 無訊號(IC ≈ 0)
多數純 OHLCV 因子(IIR/VoVT/TSMOM/DVRP/IOR/OSDR…)。crypto 日線價量的多數「異象」在無前視、扣成本下 IC 不顯著。**直接淘汰。**

### 族 B — 反轉族:真訊號,但換手 × 成本碾壓
MAX-lottery(007)、殘差反轉(009)、訂單流反轉(011)、日內 CVD/TFI(012)。
- 共同特徵:IC 顯著(t 3~甚至毛 Sharpe 6.5)、方向一致為**反轉**、越細時框越強。
- 共同死因:訊號只活 1 bar → **換手接近滿倉**,**打平成本 < 1bp**(實際 5~10bps)。012 的 TFI 反轉毛 Sharpe +6.5 其實是 **bid-ask bounce**(close 同時用於訊號與報酬),剔最高 5% bar → −23。
- 教訓:**crypto 價量/流量維度的真訊號幾乎都是不可套利的反轉。**

### 族 C — 事件族:換手低成本可活,但尾部 / regime / 多重比較
Funding 動能(008)、鏈上 whale/miner(013)。
- 共同特徵:換手低(打平 14~22bps,**不被成本殺**),但正 Sharpe **全靠少數崩盤日**。
- 共同死因:**剔最高 5% 日 → 由正轉深負**(008 −1.64、009 −2.80、013 −2.66);年度符號亂跳;多重比較(22 假設,Bonferroni t≈2.9)下不顯著。
- 教訓:這些是**崩盤風險訊號,不是連續 alpha**。

### 族 D — 資料延遲族:真資訊,但同期/落後,行動時已過期 ★新發現
Whale Overlay(014)。
- lag=1 回測 Sharpe 1.17、看似雙贏,但**事件研究**揭露:z 穿破 >1 後**唯一顯著的負報酬在 T+0(同日,t−2.56)**,T+1 已不顯著、T+3 反轉。
- whale_ratio 是 day-T 收盤後 ~1.2h(T+1 01:20 UTC)才發布、且 72h 滾動窗 → **可行動時(T+1)那個同期 edge 已成過去**。
- 教訓:**任何外部/鏈上資料訊號,必先做「資料可得時點 + 事件研究 T+1 起是否仍顯著」檢驗**,否則 lag=1 回測會偷渡同期資訊。

---

## 5. 有效的鑑別器(方法論資產)

| 鑑別器 | 攔下了 | 說明 |
|---|---|---|
| **剔最高 5% 日壓測** | 007/008/009/011/012/013(6 個) | 單一最有效武器;肥尾集中的假陽性一壓即現形 |
| **成本/換手打平分析** | 011/012 + 反轉族 | 毛利再漂亮,打平 < 1bp 即不可套利 |
| **事件研究 + 資料延遲查證** | 014 | 區分「同期」與「預測」;治 lag=1 資訊洩漏 |
| **search ledger + Bonferroni** | 007/013 | 22 假設,t 門檻抬到 ≈2.9,治 data-snooping |
| **獨立 Arbiter** | 008(主代理一度認為過關) | 治裁判兼選手 |
| **多資產 OOS / 擴 universe** | 004 / 007(擴 80 幣崩) | 治單一樣本過擬合 |

---

## 6. 「真 alpha 規格」(本研究淬煉的驗收標準)

未來任何候選須**同時**滿足:
1. IC-IR ≥ 0.3(橫截面)或扣成本 Sharpe ≥ 1.0 / vs 基準雙贏(方向)
2. **非尾部集中**:剔最高 5% 日仍正
3. **扛成本**:打平成本 ≥ 實際成本(5~10bps)
4. **可套利**:dollar-PnL 與 rank-IC 同向(非樂透/微結構)
5. **regime 穩**:年度符號不亂跳
6. **可行動**:資料在交易時點前可得;事件研究 T+1 起仍顯著(非同期)
7. **多重比較校正後**仍顯著(Bonferroni / ledger deflate)

---

## 7. 建置的基礎設施(可複用,不隨本報告作廢)

**回測 harness**(`scripts/`):`debate_sim_eval`(單資產 IC/Sharpe)、`crosssec_eval`(橫截面)、`crosssec_flow_eval`(訂單流橫截面)、`multiasset_oos`(多資產 OOS)、`backtest_timeseries`(控制台用)、`intraday_strategy_eval`(日內規則型)、`funding_carry_eval`、`onchain_eval`(鏈上時序)、`overlay_eval`(風控 overlay)。

**資料**(`empirical_runs/` + `data/onchain/`):BTC/ETH/XAU/Oil 日線;80 幣 universe(`universe_1d`)+ 79 幣 funding 全史(`funding_1d`);BTC/ETH 7 個 intraday 時框;訂單流(`universe_flow_1d` + `{btc,eth}_flow_{15m,1h,4h}`);13 個 BTC 鏈上指標(`data/onchain/`)。

**抓取器**:`fetch_universe` / `fetch_funding` / `fetch_intraday` / `fetch_orderflow`(+ 鏈上 inline)。

**知識庫**:`search_ledger.jsonl`(23 假設)、`index.db`(17 sessions / rounds / transcripts,Balaena 控制台即時可視)、v2 skill(`~/.claude/skills/factor-lab-debate/`)。

**資料源情報**:免費 = data.binance.vision(K線含 taker_buy、futures metrics OI 全史)、`ErcinDedeoglu/crypto-market-data`(BTC 鏈上 JSON);付費 = Coinglass(聚合清算/OI 全史)、Tardis(L2/L3 訂單簿)、CryptoQuant/Glassnode(多幣鏈上)。

---

## 8. 結論與未測路徑

**結論**:在**免費可得資料 + 單因子/規則型方法**的範圍內,可收割的連續 alpha 已搜尋到誠實盡頭。
這不是「沒努力找」,而是**四維度、三族死法、七道驗收**交叉驗證後的負面結論。crypto 市場的真訊號要嘛不存在、要嘛是不可套利的反轉、要嘛是行動時已過期的崩盤風險訊號。

**未測路徑**(皆超出「再換個免費因子」):
1. **付費資料 + 新方法**:Coinglass 聚合清算/OI 全史、Tardis 訂單簿(L2/L3)、多幣鏈上做**橫截面**(避開 BTC-only 時序的單樣本問題)。
2. ~~**組合/多因子**~~ — **已測(SIM-015)→ REJECT**(見附錄 A):正交性佳、IC-IR 疊到 0.31 過 Gate1,但毛 PnL 為負(IC-IR 與可交易 PnL 脫鉤),風險加權無效。
3. **接受結論**(✅ 本階段採此):把基礎設施與這份規格留作未來新資料進來時的即用評估框架。
4. **付費資料 + 新方法**(留待未來):Coinglass 聚合清算/OI 全史、Tardis 訂單簿、多幣鏈上做橫截面。

---
*相關文件*:各場 `empirical_runs/SIM-*_debate_report.md`、墓誌 `graveyard/*.md`、前一版階段總結 `FACTOR_RESEARCH_SUMMARY_2026-06-07.md`、登錄 `empirical_runs/search_ledger.jsonl`。

---

## 附錄 A — 多因子組合測試(SIM-015,2026-06-08 補)

未測路徑 #2「弱但正交訊號組合」**已測 → REJECT**。

- 因子:STR(5日反轉)+ MAX(樂透趨避)+ OFR(訂單流反轉)+ FUND(funding carry);whale 為 BTC-only 時序,無法入橫截面投組。
- **正交性極佳**(兩兩相關 −0.08~−0.01),IC-IR 確實疊加:STR+MAX → **IC-IR 0.31(過 Gate1)**。
- **但毛 LS Sharpe −0.79**(未扣成本即虧)。根因:**IC-IR 與可交易 PnL 脫鉤**——STR/MAX rank-IC 正但極端分位毛 LS 負(反轉在分布中段成立、尾端反成動能);毛利為正的 FUND/OFR IC-IR 低,組合後互相抵消。淨 Sharpe@10bps 全 −1.6~−2.6。
- **方法論補強**:此案驗證雙門檻設計的必要性——**IC-IR 須與「毛 LS Sharpe > 0」並用**,不可單獨作為通過依據(否則 STR+MAX 會假過關)。

更新後計數:**17 sessions / 23 假設 / 0 validated**。剩餘未測路徑僅 #1(付費資料)、#3(接受結論)。
