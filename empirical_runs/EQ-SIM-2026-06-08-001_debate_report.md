# EQ-SIM-2026-06-08-001 — v2 辯論:美股基本面 Value / Quality(股票延伸第一輪)

**裁決:REWORK(整個程式首個通過尾部壓測的訊號)** ｜ 新階段:股票(獨立於已 CLOSED 的 crypto)。

## 背景
crypto 四維度全證偽後,延伸到**股票基本面**(crypto 沒有的全新軸)。資料全免帳戶、point-in-time:
- 基本面:**SEC EDGAR** companyfacts(503 檔 S&P500,每筆帶 `filed` 申報日;`scripts/fetch_sec_fundamentals.py`)
- 價格:**Yahoo** 月線(`fetch_yahoo_prices.py`)
- harness:`scripts/crosssec_equity_eval.py`(月頻,`merge_asof` 嚴格 filed≤T 杜絕前視,多頭top分位超額 + LS + 剔5%月壓測 + 年度regime + 行業中性選項)

## 角色
- **Proposer**:價值(E/P+B/P+S/P)+品質(ROE),S&P500 橫截面月頻。便宜/高品質股相對走強。
- **Builder**:PIT 基本面(年度 flow filed≤T,>740日視為失效)× 月線市值;行業中性 z 合成。
- **Empiricist(標準套餐,全真實 PIT)**:

| 因子 | IC-IR | IC_t | 多頭超額 Sharpe | LS Sharpe | 剔最高5%月 | 月數 |
|---|---|---|---|---|---|---|
| Value(原始) | 0.146 | 1.34 | 0.71 | 0.42 | 長 +0.26 | 84 |
| **Value(行業中性)** | **0.232** | **2.78** | 0.47 | **0.93** | **LS +0.569** | 84 |
| Quality(ROE) | −0.01 | −0.15 | −0.24 | −0.08 | −0.88 | 143 |
| Combo | 0.045 | 0.42 | 0.48 | 0.39 | −0.14 | 84 |

- **Risk**:value 換手低(月頻、慢訊號)→ 成本友善,扣成本後仍正;long-only 超額溫和(Sharpe 0.47)。
- **Skeptic**:① IC-IR 0.232<0.30、long 超額 Sharpe 0.47<1.0(**未過嚴格門檻**)② 84 月樣本偏短 ③ **value 是最有名、最被套利的因子,可能已衰減** ④ 測 6 變體(輕度多重比較)。
- **Arbiter(獨立)**:**REWORK**。這是全程(crypto+股票)**第一個同時 (a) IC 顯著(行業中性 t2.78)且 (b) 通過剔最高5%壓測(ex_top5 +0.57 仍正)** 的訊號——**打破 crypto 的尾部集中魔咒**。但數值未過硬門檻、樣本短、屬擁擠因子 → 不足以 validated,列候選續修。

## 核心發現(meta)
1. **尾部鑑別器在股票價值上失效(好事)**:crypto 連殺 6 個假陽性的「剔5%」,在行業中性 value 上 ex_top5 仍 +0.57 → 價值超額**廣布非尾部**,結構性異於 crypto。
2. **價值必須行業中性**:原始 value 一半是行業賭注(IC-IR 0.146→0.232,t1.34→2.78)。
3. **ROE 品質無 edge**(已定價/太粗);需更細品質定義(毛利率/應計/Piotroski)。

## REWORK 待修
- **延長樣本**:value 僅 84 月(股數覆蓋限制起點)→ 補更長價格/股數史、或放寬市值來源。
- **衰減檢驗**:value 是否逐年走弱(by_year:2016 強、2017/2022 弱)→ 分段穩定性 + 近年是否仍活。
- **品質重做**:毛利率/GP-A(銀行除外)、Piotroski F-score 取代粗 ROE。
- **TTM**:flow 改用滾動四季而非年度(降低 staleness)。
- 通過則進 validated(會是全程首個);擴 universe / 加港股。

## 歸檔
候選 `candidates/EQ_Value_SectorNeutral.md`;harness + 三抓取器可複用;ledger + index.db(EQ-SIM 前綴)。
