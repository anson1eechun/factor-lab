# Factor-Lab 股票延伸階段報告(EQ-SIM-001~004)
**期間** 2026-06-08 ｜ **狀態** 第一輪完成 ｜ **結果** 4 輪 / 1 validated(Small-Cap Value)/ meta:瓶頸是 universe

> crypto 四維度全證偽(見 `NEGATIVE_RESULTS_REPORT_2026-06-08.md`)後,延伸到**股票基本面**——
> crypto 沒有的全新軸。本報告記錄四輪、一個 validated 因子,以及最重要的方法論發現:
> **經典異象失靈往往是 universe 選錯,不是維度無效。**

---

## 1. 摘要

- 資料維度:美股**基本面**(SEC EDGAR,point-in-time;Yahoo 月線),全免帳戶、無前視。
- **弧線**:S&P500 大型股三輪全失靈 → 假設並證實**瓶頸是 universe** → 換小型股,**value 復活並通過完整 OOS** → 精修定位。
- **產出**:**1 個 validated 因子**(Small-Cap Value,微型股/等權/季頻,Sharpe 1.70 但容量限定)+ 三個 REJECT 的乾淨負面結果 + 一條關鍵方法論。

---

## 2. 範圍與方法

- **資料**:`SEC EDGAR companyfacts`(每筆帶 `filed` 申報日 → 正確 PIT)+ `Yahoo` 月線。universe = **S&P1500**(大503/中400/小603,`scripts/build_universe.py`)。
- **無前視**:harness 用 `merge_asof(filed ≤ rebalance date)` 嚴格對齊,財報超過 740 日視為失效。
- **流程**:v2(Proposer→Builder→Empiricist 標準套餐→Risk→Skeptic→獨立 Arbiter→Librarian)。
- **七道驗收規格**(沿用 crypto 階段淬煉,並新增第 8 條):IC-IR≥0.3 或 Sharpe≥1.0;非尾部集中(剔5%);扛成本;可套利/有容量;regime 穩 + **分段衰減檢驗**;PIT 可行動;多重比較校正。
- **harness**:`crosssec_equity_eval`、`eq_asset_growth_eval`、`eq_piotroski_eval`、`eq_universe_retest`(分層)、`eq_value_oos`、`eq_value_refine`。

---

## 3. 全結果表(EQ-SIM-001~004)

| Session | 因子 | universe | 結果 | 裁決 |
|---|---|---|---|---|
| EQ-001 | Value(E/P+B/P+S/P)行業中性 | S&P500 大型 | 全樣本 IC_t 2.78 但**近4年衰減到 0**(前置) | REWORK→降級 |
| EQ-001 | Quality(ROE) | S&P500 | IC≈0 無 edge | REJECT |
| EQ-002 | 資產成長異象(−成長) | S&P500 | IC_t **−1.98**(反轉:高成長股反而贏) | REJECT |
| EQ-003 | Piotroski F-score | S&P500 ex-fin | IC_t −0.21,各 tier 全無 edge | REJECT |
| **EQ-004** | **Small-Cap Value** | **S&P600 小型** | **IC_t 3.85 / LS 1.70 / OOS 1.97 / 過全部規格** | **VALIDATED** |

---

## 4. ★核心 meta:瓶頸是 universe 不是維度

EQ-001~003 在 S&P500 大型股**三個經典基本面因子全失靈**。EQ-004 用 S&P1500 大/中/小**分層重測**,真相揭曉:

| Value/tier | IC_t | LS Sharpe | 近36m | 結論 |
|---|---|---|---|---|
| large | 1.28 | 0.78 | 0.63 | 衰減 |
| mid | 1.85 | 0.32 | 0.20 | 弱 |
| **small** | **3.85** | **1.70** | **+1.39** | **強、未衰減** |

size 單調(小>大>中)、內部一致 → **value 只在小型股活著**。大型股太效率、被分析到透,經典異象被套利/衰減;放回**原生小型股 universe** 即復活。
→ **EQ-001~003 的「全失靈」是 universe 錯配,不是基本面維度無效。**

---

## 5. Validated 因子:Small-Cap Value(完整定性)

**機制**:小型股(S&P600)行業內便宜(E/P+B/P+S/P 高)者相對走強。月頻(精修後**季頻**)、行業中性、PIT。

**通過全部七道規格**
- IC-IR ≈ 0.32(IC_t 3.85)；**十分位單調 Spearman 0.95**(D1貴 +0.70% → D10便宜 +2.35%/月)。
- 非尾部:剔最高5%月仍 +1.46。
- 扛成本:LS Sharpe 10/30/50bps = 1.70/1.41/1.13。
- **時間 holdout 兩半都強**:IS(2014-20)IC_t 2.54/LS 1.83;OOS(2020-26)IC_t 2.90/LS 1.57。
- 抗 1 月執行延遲(LS 1.26);三成分各自顯著(ep/bp/sp IC_t 2.47/3.17/3.04);行業分散(最大 23%)。

**精修(降換手 + 流動性過濾)**
- **季頻 rebalance = 免費改善**(成本只在 rebal 收→次數 1/3):net Sharpe **月頻 1.30 → 季頻 1.70**,OOS 1.97。→ 預設實作。
- **流動性過濾打垮溢酬**:剔最小 30% 市值 → LS 0.60、剔 50% → 0.34;等權超額 1.49 vs **市值權 −0.04**。

**最終定位(誠實)**:現象真實且統計極穩健,但 **alpha 集中於最小、最不流動的微型股**。
- **可用形態**:小帳戶 / 微型股 / **等權** / **季頻**(吃 Sharpe 1.70)。
- **不可規模化**:可交易(流動)版僅 ~0.6;這也正是它持續存在的原因——**limits-to-arbitrage(已量化)**。
- 與學界小型股 value 文獻一致。

---

## 6. 沒成功的(乾淨負面結果)

- **大型股 Value**:全樣本顯著但近 4 年衰減到 0(擁擠)→ 教訓:**全樣本 t 值會被前置誤導,務必分段衰減檢驗**。
- **資產成長異象**:在 S&P500 大型股**反轉**(高成長股 2014-26 跑贏);**拒絕翻號 claim 做多高成長**(sign-mining)。
- **Piotroski / ROE 品質**:各 tier 全無 edge(大型股已定價;Piotroski 原為便宜/中小型股內部分辨設計)。

---

## 7. 方法論收穫(加入規格)

1. **universe-native 測試**:經典異象必須放回其 documented 的原生 universe(廣/中小型/價值傾斜)再判生死。
2. **size 分層**:大/中/小分層能一眼看出 universe 效應(本案 value 小>大>中)。
3. **分段衰減檢驗**(新增第 8 條規格):全樣本顯著不算數,須看近端是否仍活(大型股 value 即栽在此)。
4. **EW vs VW 容量檢驗**:等權≫市值權 = 溢酬集中小名字 = 容量受限;這是判斷「可規模化」的關鍵一刀。
5. **拒絕 sign-mining**:異象反向時不可翻號硬湊(資產成長案)。

---

## 8. 基礎設施(可複用)

- universe:`scripts/build_universe.py` → `data/equity/universe.csv`(S&P1500 含 tier)。
- 抓取(增量):`fetch_sec_fundamentals.py`(1502 檔 PIT 基本面 → `sec_facts.parquet`)、`fetch_yahoo_prices.py`(月線 → `prices_monthly.parquet`)。
- harness:`crosssec_equity_eval`、`eq_universe_retest`(分層)、`eq_value_oos`、`eq_value_refine`、`eq_asset_growth_eval`、`eq_piotroski_eval`。
- 全程 PIT(`merge_asof filed≤T`),全免帳戶資料源。

---

## 9. 結論與未走的路

**結論**:基本面維度在股票**有效,但效在對的 universe**。找到第一個 validated 因子(Small-Cap Value),雖容量限定但真實穩健。整套「怎麼證偽 + 怎麼定位容量」的紀律,比因子本身更有長期價值。

**未走的路**:
1. 小型股池試**其他經典異象**(動能/低波/應計)——現在知道該在這池測。
2. 擴 **Russell 2000 / 微型股** universe,對 value 做真正跨 universe 的 OOS。
3. **其他市場**(港股/A股)驗證 value——需非 SEC 的基本面源。

---
*相關*:crypto 階段 `NEGATIVE_RESULTS_REPORT_2026-06-08.md`;validated 因子 `validated/EQ_SmallCap_Value.md`;各場 `empirical_runs/EQ-SIM-*_debate_report.md`;登錄 `empirical_runs/search_ledger.jsonl`。
