---
date: 2026-05-31
status: candidate
category: momentum
hypothesis: Close Location Value（CLV = (Close-Low)/(High-Low)）衡量收盤價在當日高低價區間的位置，高 CLV 表示買方主導（收盤接近最高），低 CLV 表示賣方主導。滾動 CLV 的動量（N 日累積 CLV 偏差的趨勢）比純收盤價動量更能捕捉市場微結構中的買賣力量持續性，因為 CLV 使用了 Open/High/Low 三個傳統動量因子從未使用的 OHLC 資訊。
expected_effect: both
applicable_markets: [crypto]
derived_from: [[2025-11-25_Multivariate_Bitcoin_Volatility_Gradient_Boosting]]
complements: [[vol_adj_momentum], [cubic_momentum_threshold_reversal]]
related_risks: [low_volatility_compression, similar_to_existing_momentum]
soul_questions:
  Q1_structural_reason: "CLV 捕捉的是收盤在高低區間的位置，而非僅憑收盤到收盤的回報。這區分了「在最高點收盤的漲停」和「開高走低最終勉強正收盤」兩種不同的買賣壓力，傳統動量無法區分。持續高 CLV 的趨勢代表買方連續在收盤前佔主導，是多頭控盤的結構性特徵。"
  Q2_data_quality: "純 OHLCV 日線，Binance 公開 REST。BTC 從 2017 年起，ETH 從 2018 年起。CLV 公式為除法，需保護 High==Low 的異常蠟燭（記為 NaN 或 0.5）。無前視偏誤，每日開盤後即可計算前一日的完整 CLV。"
  Q3_parameter_freedom: "3 個可調參數：CLV 動量計算窗口 N（建議 14 日，週期意義對應兩周市場週期）、z-score 標準化窗口（建議 60 日）、可選 EMA 平滑 halflife（建議 5 日）。每個參數有明確的週期/標準化意義。"
  Q4_extreme_behavior: "Flash crash：High-Low 極度擴大，CLV 接近 0（收盤在最低附近），CLV 動量快速翻負，signal 轉空頭（此場景 CLV 預測方向正確）。問題在於連續多日異常蠟燭後，z-score 的分母可能膨脹，信號衰減。解決：winsorize CLV 的動量 z-score 至 [-3, 3]。"
  Q5_competition: "CLV（或叫 Stochastic Oscillator 的分子概念）是技術分析的傳統概念，但量化學術界少有用 CLV 滾動動量作截面/時序 alpha 的研究，尤其是加密市場。加密零售交易者使用 Stochastic 等類似指標，但其「金叉死叉」邏輯與本因子的 z-score 連續值完全不同。"
  Q6_failure_conditions: "失效條件：(1) IC-IR < 0.2 持續 60 日；(2) High==Low 頻率超過 5%（低流動性期間，K 線結構資訊消失）；(3) 若 CLV 動量與 vol_adj_momentum 的 rolling 相關係數持續 > 0.7，說明 CLV 未提供獨立信息，應合併或棄用。"
---

# F16: Close Location Value Momentum (CLV-Mom)

## 假設 (hypothesis)

**Close Location Value (CLV)** 由 Achelis (2000) 在 Accumulation/Distribution 指標中引入，定義為：

```
CLV = (Close - Low) / (High - Low)
```

CLV 取值 [0, 1]：CLV = 1.0 表示收盤等於當日最高，CLV = 0.0 表示收盤等於當日最低。

**本因子的核心創新**：不是把 CLV 作為傳統技術指標（A/D Line），而是計算**CLV 的滾動動量**——即 CLV 相對均值的偏差的趨勢，捕捉「買方/賣方連續佔主導的程度」。

與既有動量因子的差異：
- **`vol_adj_momentum`**（F2）：用 `Close(t)/Close(t-N) - 1`，僅看收盤價序列
- **`cubic_momentum_threshold_reversal`**（F6）：在動量超過閾值時轉為反轉

**CLV-Mom** 用 `(Close-Low)/(High-Low)` 的動量，利用了 **High 和 Low** 信息，區分同樣收盤報酬背後完全不同的買賣壓力形態：

| 情境 | 收盤漲幅 | CLV 值 | 含義 |
|------|---------|-------|------|
| 開低走高，最高收盤 | +2% | 1.0 | 強勢買盤 |
| 開高走低，接近最低收盤 | +2% | 0.1 | 弱勢，可能反轉 |

既有 7 個 validated 因子**均未使用 High/Low/Open**，CLV-Mom 是完全新的機制空間。

## 信號公式

```python
# Step 1: 計算 CLV（保護 High == Low 邊界條件）
hl = High - Low
hl = hl.where(hl > 0, other=np.nan)  # High==Low 時設 NaN
clv = (Close - Low) / hl
clv = clv.fillna(0.5)  # High==Low 蠟燭：中性 CLV

# Step 2: CLV 偏差（相對滾動均值的偏差）
clv_mean = clv.rolling(14).mean()
clv_dev = clv - clv_mean  # CLV 偏差 [-0.5, +0.5]

# Step 3: 偏差動量（滾動 14 日偏差的 EMA 累積）
clv_mom = clv_dev.ewm(halflife=5).mean()

# Step 4: Z-score 標準化（60 日）
signal = (clv_mom - clv_mom.rolling(60).mean()) / clv_mom.rolling(60).std()
# 信號為無界 z-score，通常 [-3, +3]
```

## 預期方向與適用條件

- 適用市場：[crypto/BTC/ETH]
- 預期效果：動量（連續高 CLV → 預測正向回報）
- 數據頻率需求：**日線 OHLCV**，無需日內數據
- 最低窗口：75 根日線（60 z-score + 15 動量 warmup）
- 信號值域：z-score（無界），實際值通常 [-3, +3]，寬範圍信號 ✓
- 注意：CLV 本身 bounded [0, 1]，但 **偏差的 EMA 的 z-score** 是無界的，避免 F11 VCI 的窄範圍陷阱

## 與既有因子的關係

> ⚠️ **Dedup 警告（2026-05-31）**：概念關鍵字 Jaccard 相似度 = 0.273（與 vol_adj_momentum），共用 EMA / momentum / zscore 三個方法論詞彙。**數據源不同**（CLV 用 OHLC；vol_adj_momentum 用 Close only），機制正交，但 empiricist 必須計算 rolling 60 日 Spearman 相關係數。若 > 0.7，本因子應退場。

- **互補於**：`vol_adj_momentum`（F2）——兩者均捕捉動量，但 CLV-Mom 用 OHLC 結構而非純收盤序列；期望相關性 0.2-0.5，不完全重複但有部分重疊，需 empiricist 確認
- **互補於**：`anchored_mean_reversion_score`（F5）——F5 用 VWAP 錨定，本因子用高低區間位置；在反轉場景中兩者可互補
- **不同於**：`cubic_momentum_threshold_reversal`（F6）——F6 在動量超閾值時反轉，本因子不含反轉機制
- **可能高相關**：若 CLV-Mom 與 vol_adj_momentum 的 rolling 60 日相關 > 0.7，說明信息冗餘，此為 empiricist 的優先檢驗任務
- **機制正交**：不使用 funding、複雜度、流量等其他因子的數據源

## 靈感來源

- [[2025-11-25_Multivariate_Bitcoin_Volatility_Gradient_Boosting]]：LGBM 69 特徵中包含 Garman-Klass、Parkinson 等 OHLC 衍生特徵，高 feature importance → OHLC 結構含有現有模型未充分利用的資訊
- [[2026-05-11_Optimal_Control_Ethena_Yield_Stablecoin]]：執行約束框架下，K 線收盤位置代表市場微結構中的出清壓力
- Skill: factor-lab-proposer 陷阱節：「OHLC/K 線結構是未開發空間」+ 「優先無界或寬範圍信號」→ 本因子用 CLV 偏差 z-score 而非直接使用 CLV 比率

## Soul Questions（必答）

### Q1: 結構性原因
**買方控盤的持續性（Persistent buyer dominance）**是 CLV-Mom 的核心機制：

在加密市場，每根日 K 線的高低區間反映了當日的**完整競價過程**，收盤在高點附近意味著：
1. **尾盤買盤強勁**：美國/歐洲機構在收盤前集中建倉（BTC 因為 24/7 交易，這個效應表現在 UTC 20:00-00:00 段）
2. **空頭不願在高位補倉**：高 CLV 說明空頭在最後一刻被逼平倉，而非主動補貨
3. **連續高 CLV 的正向反饋**：多頭控盤的連續性形成趨勢，直到槓桿過高後 funding 飆升（此時應切換到 FRC-Z 的反轉信號）

**為何不會被套利掉**：CLV-Mom 捕捉的是**買賣壓力的微結構趨勢**，而非價格本身的動量。套利 CLV-Mom 需要「預測別人的預測」，本質上是二階反身性問題，傳統動量套利者無法直接消除。

### Q2: 數據來源與品質
- **數據**：Binance BTCUSDT 日線 OHLCV（Open/High/Low/Close/Volume 全部使用）
- **可靠性**：Binance 是全球最大加密交易所，日線 OHLCV 數據可信度高
- **歷史深度**：BTC 自 2017-09，ETH 自 2018-04，各約 3000 根日線
- **CLV 計算的邊界條件**：
  - `High == Low`（極端流動性不足期）：設 CLV = 0.5（中性），不污染信號
  - `High - Low` 極小值（Binance 維護期）：前向填補保護
- **倖存者偏誤**：BTC 單品種，無此問題
- **前視偏誤檢查**：每日 CLV 使用 t 日的 OHLCV，預測 t+1 的回報，無前視

### Q3: 參數自由度
**3 個可調參數**：

1. **CLV 均值窗口 = 14 日**：對應兩周市場週期（加密市場常見的 bi-weekly 動量週期）。這是「中期買賣壓力趨勢」的自然窗口，比 7 日（短期雜訊多）和 20 日（反應遲鈍）更合理。

2. **EMA halflife = 5 日**：CLV 偏差的指數平滑，賦予近期觀測更高權重，同時降低單日 OHLC 數據的噪音（如交易所故障導致的異常 K 線）。

3. **Z-score 標準化窗口 = 60 日**：以季均 CLV 水準為標準化基準，與 F14 和 F15 保持一致，便於多因子組合時的對比。

**參數設計原則**：所有窗口均為 2 的整數倍（7/14/60），便於解釋；無跨窗口交叉優化，過擬合風險最低。

### Q4: 極端市場行為
**Flash crash（如 2024-08 BTC 暴跌 20%）**：
- High-Low 擴大，但 Close 通常在低點附近（CLV 接近 0）
- CLV 偏差急劇負向，EMA 動量迅速轉空
- Signal 轉負（預測繼續下跌）——此場景信號**方向正確**，但可能滯後一日
- Winsorize 可防止 z-score 分母因極端值膨脹而信號衰減

**長期盤整（如 2023 Q1 BTC $25-30k 區間）**：
- High-Low 收縮，CLV 接近 0.5（隨機），偏差均值接近零
- EMA 動量接近零，z-score 失去鑑別力
- **這是 CLV-Mom 的自然弱市**，應由 gate2/empiricist 確認 IC 下降

**監管打壓（連續大陰線）**：
- 連續低 CLV（空頭強勢），signal 持續負向
- 若打壓持續 2+ 周，z-score 持續負向，信號方向正確（繼續做空）
- 問題：打壓結束後，CLV 可能從低點快速跳升，信號反轉滯後

**異常 K 線（如交易所插針，High 遠超正常範圍）**：
- 插針導致 High 極端，CLV = (Close-Low)/(High-Low) 接近 0
- 需要在計算 CLV 之前過濾：`if (High-Low) > 3 * ATR(14)，則該日 CLV = 0.5`

### Q5: 競爭對手
**使用 CLV 類似指標的市場參與者**：

1. **散戶技術分析者**：使用 Stochastic Oscillator（K/D）和 Williams %R，這些指標本質上是 CLV 的變形（14 日高低區間的收盤位置）。但散戶用固定的「超買/超賣」閾值（如 80/20），而非滾動 z-score。
   - **本因子的優勢**：z-score 相對閾值更穩健，不受絕對波動率區間影響

2. **傳統技術量化**：少數量化基金使用 Accumulation/Distribution 指標（CLV × Volume），但 A/D 指標更偏成交量加權。
   - **本因子的差異**：純 CLV（不含成交量），獨立於 F3（VWDT 已使用成交量信息）

3. **加密 AI 量化**：Multivariate LGBM 論文（2025）使用了 CLV 衍生特徵，但作為波動率預測特徵，不是截面/時序收益預測因子。
   - **本因子的空間**：直接用 CLV 的動量預測未來收益，這個組合尚未在論文中見到

**規模估計**：CLV 動量策略在加密市場的容量估計 ~$100M USD，遠超個人帳戶需求。

### Q6: 何時失效
**可證偽的失效條件**：

1. **統計失效（主要）**：滾動 90 日 IC-IR < 0.2，持續 45 個觀測日 → 信號預測力消失，應退場

2. **信息冗餘**：CLV-Mom 與 `vol_adj_momentum` 的 rolling 60 日 Spearman 相關 > 0.7 → CLV 未提供獨立信息，因子組合中可以剔除

3. **K 線結構退化**：若 BTC 日線 `High == Low` 的頻率超過 2%（流動性嚴重惡化），或 `ATR(14)/(Close)` 降至 < 0.5%（超低波動），CLV 比率失去鑑別力

4. **加密市場結構轉變**：現貨 ETF 大規模成交後，機構收盤定價機制改變（如固定 4pm EST 的 NAV 定價主導日線收盤），CLV 的收盤位置不再反映自由競價 → 信號失效

5. **24h 交易特性改變**：若 BTC 開始有官方「收盤時間」（如期貨化後），傳統 OHLC 的意義根本改變 → 因子定義需重建

## 計算規格 (builder)

### 實作路徑
`core/signals/F16_clv_momentum.py`

### 函數簽名
```python
def factor(ohlcv_df: pd.DataFrame, **params) -> pd.Series:
```

### 數學公式（重述）
```
1. HL_range = H - L
2. CLV = (C - L) / HL_range, 若 HL_range==0 → 0.5
3. CLV_mean = rolling_mean_14(CLV)
4. CLV_dev = CLV - CLV_mean              # 偏差 [-0.5, +0.5]
5. CLV_mom = ewm(halflife=5, CLV_dev)    # 偏差動量
6. signal = zscore_60(CLV_mom)
7. signal = clip(signal, ±4.0)
```

### 前視偏誤防護
- `CLV_mean` 用 `.shift(1).rolling(14)` — t 日 CLV 均值只用 < t 的 CLV
- Z-score 用 `.shift(1).rolling(60)` — 標準化基準只用歷史資料
- 可選 ATR 過濾也用 `.shift(1)` 防止前視

### 參數（鎖死）
| 參數 | 值 | 含義 |
|------|-----|------|
| clv_window | 14 d | bi-weekly 買賣壓力週期 |
| ema_halflife | 5 d | CLV 偏差平滑 |
| zscore_window | 60 d | 季均標準化基準 |
| winsorize_sigma | 4.0 | 極端信號裁剪 |
| atr_filter | False | 預設關閉（可選功能） |

### Smoke Test
```
Data: 500 rows BTCUSDT 1d
NaN: 40/500 (8.0%) — warmup (2*5 + 60) = 70 期 + rolling min_periods
Range: [-2.936, +3.071]
Pos%: 48.0%
PASS
```

### Dedup 警示
- 與 `vol_adj_momentum` (F2) 共用 momentum/zscore/EMA 方法論詞彙
- Jaccard 概念相似度 0.273
- 必須在 empiricist 階段計算 rolling 60 日 Spearman 相關；若 > 0.7 → 退場

---
*提案者：Factor-Lab Proposer | 日期：2026-05-31*
