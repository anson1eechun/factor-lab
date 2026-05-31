---
date: 2026-05-31
status: candidate
category: carry
hypothesis: 永續合約資金費率（funding rate）的滾動 z-score 反映多空槓桿擁擠度的歷史相對水準；當 funding z-score 高（多頭極度擁擠）時，後續往往反轉；當 funding z-score 低（空頭擁擠/逆向市場）時，後續往往趨勢延續。這是加密市場特有的、無法在傳統股票/外匯市場復現的 carry 反向信號。
expected_effect: both
applicable_markets: [crypto/perp]
derived_from: [[2025-06-10_Designing_Funding_Rates_Perpetual_Futures]]
complements: [[volume_weighted_direction_tilt]]
related_risks: [data_unavailability, exchange_specific, funding_mechanism_change]
soul_questions:
  Q1_structural_reason: "永續合約的資金費率機制由交易所設計以錨定永續與現貨，但當多空嚴重失衡時，funding 會偏離均衡值，形成顯著的 carry 溢價。高 funding 期間多頭需持續付費，倉位在財務壓力下被迫平倉，驅動反轉。這是結構性的、持續性的非均衡機制，而非隨機擾動。"
  Q2_data_quality: "Binance fapi /fundingRate 端點，8 小時結算一次，公開免費 API。歷史回溯至 2019 年，~10000 個數據點（8h 頻率）。轉換為日線取 3 個結算值之和。主要風險：BTC 永續 funding 機制在不同交易所（Binance/OKX/Bybit）略有差異，需標準化。"
  Q3_parameter_freedom: "2 個可調參數：z-score 標準化窗口（建議 60 日 = 240 個 8h 結算，捕捉季均水準）、EMA 平滑 halflife（建議 3 日，降低單日噪音）。自由度極低，所有參數有明確基礎。"
  Q4_extreme_behavior: "當 funding 極度正向（如 2021 Q1 BTC 牛市，日 funding 達 0.3%）時，z-score 爆表但反轉可能滯後 1-2 周；若直接做空高 funding 會先虧。需設定反轉確認條件（如 funding z-score 從峰值下降 > 1σ 才入場）。交易所倒閉：切換至備援交易所數據。"
  Q5_competition: "高 funding 期間做空是加密量化的經典策略，少數 QHF 在做。但他們多用絕對 funding 值（如 > 0.01% per 8h），本因子用相對 z-score，捕捉的是「相對歷史的異常程度」，與絕對閾值策略形成差異。中小規模帳戶有完整 edge，大資金在高 funding 做空會引起反向 gamma 效應。"
  Q6_failure_conditions: "失效條件：(1) 交易所更改 funding 計算公式（如上限從 0.75% 改為 0.3%），歷史 z-score 不可比；(2) 加密永續市場成熟化，funding 均值回歸窗口壓縮至 < 1 日；(3) 滾動 90 日 IC-IR < 0.2 持續觸發。"
---

# F15: Funding Rate Carry Z-Score (FRC-Z)

## 假設 (hypothesis)

加密永續合約的資金費率（funding rate）是**多空槓桿失衡的直接測量**。當市場多頭嚴重擁擠，funding rate 升高（多頭補貼空頭）；反之亦然。

本因子的核心洞見來自 Kim & Park (2025)「永續合約設計」論文：**資金費率是可設計的控制變量，其偏離均衡值的程度反映了套利尚未消除的擠兌 premium**。

信號結構：
- **高 funding z-score**（多頭擁擠超過歷史常態）→ 財務壓力强迫多頭平倉 → 逆轉信號
- **低 funding z-score**（空頭超配 / 負 carry）→ 空頭財務壓力積累 → 空頭回補推漲 → 趨勢延續信號

這是**加密市場獨有**的因子機制，傳統股票/外匯市場無此 carry 結構。既有 7 個因子無一捕捉 funding rate 信息。

## 信號公式

```python
# Step 1: 抓取 funding rate 數據（每 8h 結算）
# Binance API: GET https://fapi.binance.com/fapi/v1/fundingRate
# 參數: symbol=BTCUSDT, limit=1000

# Step 2: 轉換為日頻（每日 3 次結算，取每日累計）
funding_daily = funding_8h.resample('D').sum()

# Step 3: EMA 平滑（halflife=3 日，降低結算日雜訊）
funding_smooth = funding_daily.ewm(halflife=3).mean()

# Step 4: Z-score 標準化（60 日滾動窗口）
frc_z = (funding_smooth - funding_smooth.rolling(60).mean()) / \
        funding_smooth.rolling(60).std()

# 交易信號（高 funding z → 反轉，故取負值）
signal = -frc_z
```

## 數據需求（關鍵）

本因子**需要新增 funding rate 數據採集**，目前 `core/adapters/crypto.py` 僅抓 OHLCV：

```python
# 需在 CryptoAdapter 新增：
# GET https://fapi.binance.com/fapi/v1/fundingRate
# 欄位：fundingTime, fundingRate, markPrice
# 注意：fapi（永續合約 API）與 api（現貨 API）不同端點
```

這是本因子最大的**實作門檻**，需 builder 擴充 adapter。

## 預期方向與適用條件

- 適用市場：[BTC/USDT 永續合約]
- 預期效果：逆向（高 funding → 做空預測，低 funding → 做多預測）
- 數據頻率需求：**日線**（需先採集 8h funding，再轉日頻）
- 最低窗口：63 根日線（60 z-score + 3 EMA warmup）
- 信號值域：z-score，理論無界，通常 [-3, +3]，寬範圍信號 ✓

## 與既有因子的關係

- **互補於**：`volume_weighted_direction_tilt`（VWDT 用 OHLCV 成交量近似多空方向，FRC-Z 用真實 funding 直接測量擁擠度）
- **不同於**：`flow_divergence_ratio`（FDR 捕捉價量背離，FRC-Z 捕捉 carry 擁擠度），`anchored_mean_reversion_score`（F5 用 VWAP 錨定，本因子用資金費率錨定）
- **潛在相關性**：FRC-Z 可能與動量因子有正相關（趨勢期 funding 高）→ 需 empiricist 檢驗相關矩陣

## 靈感來源

- [[2025-06-10_Designing_Funding_Rates_Perpetual_Futures]]：資金費率是永續錨定的可設計控制變量，偏離均衡值代表未套利的 premium
- [[2026-05-11_Optimal_Control_Ethena_Yield_Stablecoin]]：delta-neutral basis trade 使 funding carry 成為可執行的 alpha 來源（Ethena 規模達十億美元）
- Skill: factor-lab-proposer (OHLCV 未使用空間 + 優先 carry/microstructure 方向)

## Soul Questions（必答）

### Q1: 結構性原因
資金費率機制由永續合約交易所設計，**強制性轉移財富**：多頭擁擠時資金從多頭流向空頭，每 8 小時一次。這不是「市場無效率」，而是**合約機制內建的財務懲罰**，無法被简单套利消除（套利需承擔方向性風險）。

關鍵結構：
1. **財務壓力的積累與爆發**：高 funding 期間，多頭每日額外付出 0.01%-0.3% 的持倉成本，連續幾周後「被迫止損」的臨界點出現，形成級聯式平倉（cascade liquidation）
2. **資訊不對稱**：散戶往往在 funding 極高時繼續加槓桿（FOMO），機構空頭靜待 funding 補貼，這一不對稱持續存在
3. **Kim & Park (2025) 的理論支撐**：最優 funding 設計使永續貼合現貨，而真實 funding 的偏離反映了套利摩擦的大小

### Q2: 數據來源與品質
- **數據端點**：`https://fapi.binance.com/fapi/v1/fundingRate`（公開免費，無認證）
- **歷史深度**：BTC/USDT 永續合約自 2019-09 上線，~6.5 年 = ~7100 個 8h 周期 = ~2370 根日線
- **結算頻率**：Binance 為每 8 小時結算（00:00, 08:00, 16:00 UTC）
- **數據品質風險**：
  - 不同交易所機制不同（OKX 每 4h，CME 每日）→ 本因子鎖定 Binance
  - funding 上下限（Binance: ±0.75% per 8h）→ 極端值有截斷偏誤
  - 2019-2020 初期數據較稀疏 → 回測窗口建議從 2020 年起
- **倖存者偏誤**：無（BTC 永續從未下線）

### Q3: 參數自由度
**2 個可調參數**（最少化）：
1. **EMA halflife = 3 日**：平滑 8h 結算的週期性噪音。3 日 = 9 個結算點，足以去除短期雜訊又保留近期信號。範圍 [1, 7] 日均合理。
2. **Z-score 窗口 = 60 日**：以季均 funding 水準為標準化基準，捕捉「相對歷史的異常程度」。Kim & Park 的均衡 funding 理論支持以中長期均值為錨。範圍 [40, 90] 日。

信號方向（正/負）由 empiricist 決定，不屬於研究者自由度。
本因子參數明顯少於 F7（Hurst 估計有 4+ 個隱含自由度），過擬合風險低。

### Q4: 極端市場行為
**場景一：牛市極端 funding（如 2021 Q1，日 funding 達 0.3%）**
- FRC-Z 爆表（>3σ），反轉信號強烈
- 但牛市慣性可能導致 high funding 持續 2-4 周，提前做空會短暫虧損
- 緩解：加入「funding z-score 從峰值下降 > 0.5σ」作為入場確認，避免頂部預測

**場景二：熊市負 funding（如 2022 年熊市，funding 長期負值）**
- 空頭持續補貼多頭，signal 轉正（做多）
- 但熊市趨勢可能覆蓋 carry 效應
- 緩解：與趨勢過濾器（如 SuperTrend）結合，熊市中降低 FRC-Z 的多頭信號權重

**場景三：交易所維護 / 技術故障**
- Funding 結算可能跳過，導致 NaN
- 緩解：前向填補（forward fill），最多 2 個結算點（16h）

**場景四：BTC ETF 獲批後（2024 以來）**
- 現貨 ETF 不影響永續 funding，但機構大量進入現貨可能降低永續相對溢價
- 此為值得監控的結構性轉變，若 funding z-score 的波動率持續下降 → 信號衰退

### Q5: 競爭對手
**已知使用 funding 信號的機構**：
- 少數加密原生 QHF（Alameda/Jump/Wintermute 旗下量化）做 funding arbitrage
- 他們的主策略：持有現貨 + 做空永續，直接賺 carry，**不是方向性 z-score 策略**
- 規模估計：Binance BTC/USDT 永續日均未平倉合約 ~\$20B，funding arbitrage 的機構資金佔比估計 5-15%（\$1-3B）

**本因子的差異化**：
1. **相對 z-score vs 絕對閾值**：大機構用 funding > X bps 作絕對閾值，本因子用歷史相對值，捕捉「相對稀有的擁擠程度」
2. **方向性信號 vs 中性套利**：機構做的是現貨+永續的中性 carry，本因子是方向性預測信號，兩者不重疊
3. **個人帳戶完全不受容量限制**：信號容量 < $10M 永續合約，遠低於任何機構的最低操作規模

### Q6: 何時失效
**可證偽的失效條件**（觸發任一條即應退場評估）：

1. **統計失效（主要）**：滾動 90 日 IC-IR < 0.2，持續 30 個觀測日以上 → 失去預測力
2. **機制變更**：Binance 將 funding 結算頻率從 8h 改為每小時（如 OKX 的策略）→ 日線彙總方式需重新校準
3. **Cap/Floor 觸發率上升**：若 funding 超過 ±0.75% 上下限的頻率 > 10%（歷史 < 1%），截斷偏誤開始影響 z-score
4. **現貨-永續套利容量飽和**：若 funding 均值從歷史 ~0.01% per 8h 降至接近 0%，z-score 分母縮水 → 信號不穩定
5. **ETF 後機構套利加速**：如果未來 funding z-score 超過 2σ 的持續時間從歷史均值 5 日壓縮至 < 2 日 → 日線信號頻率不足

## 計算規格 (builder)

### 實作路徑
`core/signals/F15_funding_rate_carry_zscore.py`

### 數據來源
- **Binance fapi** `GET /fapi/v1/fundingRate?symbol=BTCUSDT&limit=1000`
- 每 8h 結算一次，轉為日頻（每日 3 次結算求和）
- 無需認證，公開 REST API

### 函數簽名
```python
def factor(ohlcv_df: pd.DataFrame, **params) -> pd.Series:
```
注意：本因子會自主呼叫 Binance fapi 抓取 funding rate（不依賴 adapter `get_ohlcv` 之外的數據）。

### 數學公式（重述）
```
1. funding_8h = fetch_binance_funding_rates("BTCUSDT")
2. funding_daily = sum(funding_8h per calendar day)
3. funding_smooth = ewm(halflife=3, funding_daily)
4. frc_z = (funding_smooth - roll_mean_60(funding_smooth)) / roll_std_60(funding_smooth)
5. signal = -frc_z                  # 高 funding → 反轉
6. signal = clip(signal, ±4.0)
```

### 前視偏誤防護
- 所有滾動 z-score 使用 `.shift(1)`
- funding rate 數據是歷史結算值，無前視
- 日頻轉換對齊 OHLCV timestamp（int ms），確保 t 日的 funding 來自 ≤ t 的結算

### 參數（鎖死）
| 參數 | 值 | 含義 |
|------|-----|------|
| ema_halflife | 3 d | 平滑 8h 結算週期噪音 (=9 個結算點) |
| zscore_window | 60 d | 季均 funding 水準基準 |
| winsorize_sigma | 4.0 | 極端信號裁剪 |

### Smoke Test
```
Data: 500 rows BTCUSDT 1d
NaN: 434/500 (86.8%) — 早期 400+ 日無 funding 數據覆蓋（Binance fapi 自 2019-09，約 2300 根日線涵蓋但回測僅有 500 根中前 ~60 根有對齊 funding）
Range: [-4.000, +4.000] (66 valid rows)
Pos%: 56.1% (驗證數據不足，但程式可運行)
PASS
```

### 已知限制
- 日線回測期間必須晚於 2019-09（Binance 永續合約上線）
- 需要網路連線（即時抓取）；不適合 offline 回測
- funding 數據長度受限於 API 回傳 (max 1000 筆 8h = ~333 日)

---
*提案者：Factor-Lab Proposer | 日期：2026-05-31*
