$$\rho_t = \text{Pearson}\bigl(r^{\text{BTC}}_{t-W+1:t},\ r^{\text{ETH}}_{t-W+1:t}\bigr)$$

其中 $W \in \{30, 60, 90\}$，預設 $W = 60$。

**Step 3 — 訊號核心**

$$\text{raw\_signal}_t = \text{sgn}(r_t^{\text{BTC}}) \times \rho_t \times |r_t^{\text{BTC}}|$$

$\rho_t$ 和 $r_t^{\text{BTC}}$ 均為時間 $t$ 的已知量；訊號預測的是 $\text{ETH}_{t+1}$（由 empiricist 做 `.shift(-1)` 對齊）。

**Step 4 — 條件過濾**

| 條件 | 動作 |
|------|------|
| $\|\rho_t\| < 0.4$ | 完全靜默（ETH 獨立 regime） |
| $0.4 \leq \|\rho_t\| < 0.7$ | 降權 $\times 0.5$ |
| $\|\Delta\rho_t\| > 0.3$ | Regime 切換，靜默 5 日 |

**Step 5 — 前視偏誤防範**

- coherence 視窗 $[t-W, t]$ 全在 $\leq t$，無未來洩漏
- `|Δρ| > 0.3` 使用 `coherence.diff()`（當期與前期，無 `center=True`）
- Regime pause 用 `.rolling(5).max()`（只看過去 5 日有無切換事件）
- empiricist 在計算 Rank-IC 時需將 `signal_t` 對齊 `ETH_return_{t+1}`（`.shift(-1)`）

### 輸出說明

函數輸出 Series 對應 DataFrame 中所有行：
- ETH 行：計算好的 $\text{signal}_t$ 值
- BTC 行：NaN（BTC 為觀察標的，不是交易標的）

### Smoke Test 結果（2026-05-27）

| 指標 | 數值 |
|------|------|
| 標的 | BTCUSDT + ETHUSDT 日線各 500 根 |
| ETH 有效值數量 | 480 |
| ETH NaN 數量 | 20（coherence 視窗暖身期） |
| 值域 | [-0.1386, 0.1071] |
| 平均 | -0.0005  標準差: 0.0201 |
| 輸出類型 | pd.Series（ETH 側訊號，BTC 行為 NaN） |
| 狀態 | PASS |

## 質疑 (skeptic)

### RW-1：BTC→ETH lead-lag 是 stat-arb 文獻中被研究最透徹的 crypto 效應之一
- **類型**：重複造輪子
- **具體內容**：BTC→ETH 日級 lead-lag 是 crypto 量化文獻中被最廣泛研究的效應。具體證據：(1) Kajtazi & Moro (2019) "The role of bitcoin in portfolio diversification" 已記錄 BTC→altcoin 的報酬傳導；(2) 機構 stat-arb 基金（候選筆記 Q5 承認 D.E. Shaw、Two Sigma crypto desk）已將日級 lead-lag 列為標準策略；(3) 更直接的重疊是 Binance 自身提供的「相關係數排行榜」功能，其核心計算等同本因子的 coherence 計算。既有因子庫的 `flow_divergence_ratio`（IC-IR = 0.676）雖是不同機制，但兩者都從「BTC 作為 crypto beta 錨」出發；proposer 聲稱「日線級且帶 coherence 過濾的版本相對少見」，但缺乏具體文獻引用支撐此聲明。
- **嚴重程度**：major
- **建議修正**：empiricist 需計算 F9 與 `flow_divergence_ratio` 的 Pearson 相關性。proposer 需引用至少 2 篇「日線 BTC→ETH lead-lag 無效或已被套利掉」的反例文獻，或提供 2020 年後（BTC ETF 前後）效應衰減的時序分析。

### EI-1：coherence（Pearson 相關性）≠ lead-lag 關係，概念混淆
- **類型**：經濟直覺
- **具體內容**：代碼第 104 行計算的是 `btc_ret.rolling(W).corr(eth_ret)`，即**同期（同時刻）**的 BTC 與 ETH 報酬滾動相關性。但因子的核心假設是「BTC_t 領先 ETH_{t+1}」，即**時間錯位的 lead-lag**。同期相關性 ρ(BTC_t, ETH_t) 衡量的是「兩者是否同步波動」，而非「BTC 是否先動」。若要驗證 lead-lag，應計算 `cross-correlation(BTC_ret[t-lag], ETH_ret[t])`，即帶 lag 的互相關。候選筆記假設「coherence 高時 BTC lead ETH」，但這個因果鏈條從未在因子計算中被直接建模：`coherence_t = ρ(同期)` 是相關性代理，而非 lead 關係的直接量化。
- **嚴重程度**：critical
- **建議修正**：(1) 代碼需增加 `lead_lag_correlation = btc_ret.shift(1).rolling(W).corr(eth_ret)` 計算**真正的 lag-1 互相關**，並與現有同期相關性比較；(2) 若 `lag-1 cross-correlation < lag-0 cross-correlation`，說明「同期相關性」而非「lead-lag 效應」是主要驅動力，因子的解釋框架需修正；(3) 筆記中聲稱的 Granger causality test 需在 empiricist 階段實際執行並記錄結果。

### LA-1：訊號使用 BTC_t 報酬但預測 ETH_{t+1}，信息集邊界需要精確定義
- **類型**：前視偏誤（邊界案例）
- **具體內容**：代碼第 113 行 `raw_signal = sign(btc_ret) * coherence * btc_ret.abs()`，其中 `btc_ret` 是 `log(btc_close_t / btc_close_{t-1})`（代碼第 98 行），依賴 `btc_close_t`（T 日 UTC 00:00 收盤價）。若 ETH 和 BTC 的收盤時間點**完全相同**（都是 UTC 00:00），則 `btc_close_t` 與 `eth_close_t` 是同一個時間截面，不存在 lead-lag；真正的「BTC 先行」信息優勢只在 BTC 先於 ETH 反應的**分鐘級或小時級**才成立。在日線上，BTC_t 和 ETH_t 的收盤都是 UTC 00:00，`btc_ret_t` 和 `eth_ret_t` 是同步計算的，不存在 BTC 領先 ETH 的時間差。日線下的「lead-lag」實際上是**隔日效應**（BTC_t → ETH_{t+1}），需要確認這是否是真實的信息傳導而非殘差自相關。
- **嚴重程度**：critical
- **建議修正**：builder 需在 smoke test 中直接計算 `Pearson(btc_ret_t, eth_ret_{t+1})` 的相關係數並報告數值；若相關係數 < 0.05 且 p-value > 0.05，則「BTC 日線領先 ETH 次日」假設不成立，因子基礎動搖。此外應計算 `Pearson(eth_ret_t, btc_ret_{t+1})` 反向 Granger，若強於正向，lead-lag 方向錯誤。

### DM-1：Regime 切換過濾 |Δρ| > 0.3 的閾值缺乏統計依據
- **類型**：資料探勘
- **具體內容**：代碼第 108 行 `regime_switch = delta_rho > 0.3`：當 coherence 一階差絕對值超過 0.3 時暫停 5 日。問題：(1) 0.3 這個閾值是如何確定的？候選筆記 Q3 未提供統計依據（如分位數計算）。(2) `coherence.diff()` 在 coherence 計算窗口為 60 日時，其一階差的自然波動幅度取決於 coherence 的時序波動率。在 BTC/ETH 相關性激烈波動的市場（如 2022 年），`|Δρ|` 的 rolling std 可能本身就 > 0.2，導致 0.3 閾值頻繁觸發，訊號大量被過濾。(3) 整個「regime pause 5 日」機制在代碼中通過 `rolling(5).max()` 實現（第 110 行），這等同「若最近 5 日中任何一天發生切換就全部靜默」，但沒有測試 pause_days 參數對最終 IC-IR 的敏感性。
- **嚴重程度**：major
- **建議修正**：empiricist 需報告在不同閾值下（0.2, 0.3, 0.4）和不同 pause_days（3, 5, 7）的 IC-IR 矩陣；若 IC-IR 對此參數高度敏感（最大-最小差異 > 50%），視為過擬合風險因子。

### CL-1：僅交易 ETH 且 coherence > 0.7 才激活，有效持倉日數可能極少
- **類型**：成本/流動性
- **具體內容**：根據候選筆記第 46 行「coherence 高 regime 約佔 60-70% 時間」，加上 regime pause 過濾（每次切換暫停 5 日），實際激活的訊號比例可能低於 50%。更重要的是，代碼第 123 行在 `0.4 ≤ coherence < 0.7` 時降權 × 0.5，但完全激活需要 coherence > 0.7。在 2022 年的 crypto 熊市中，BTC/ETH 相關性長期 > 0.8（全市場系統性風險），此時 coherence 持續高位但 lead-lag 效應因「同步崩跌」而失效。換言之：**coherence 高的時候，正是 lead-lag 最弱的時候**（市場系統性衝擊讓兩者同步）。候選筆記 Q4 也承認「Flash crash 中 coherence 反而上升但 lead-lag 縮短至小時級」。
- **嚴重程度**：major
- **建議修正**：empiricist 需分別計算「coherence 高但波動率低（正常 regime）」和「coherence 高但波動率高（系統性風險 regime）」兩個子集的 IC，驗證假設「coherence 高 = lead-lag 有效」是否在高波動 regime 下失效。若失效，需增加「日內波動率 < 滾動 75th」的過濾條件。

## 實證 (empiricist)

### 數據範圍
- 標的：BTCUSDT + ETHUSDT（跨資產），ETH 側訊號 → ETH 未來報酬
- 頻率：日線
- 期間：2025-01-12 ~ 2026-05-26（BTC/ETH 各 500 筆，有效訊號 480 筆，NaN 佔 4.0%）
- IC 計算方式：時序 IC（rolling 60 日窗口 Spearman），共 419~400 個窗口點

### skeptic EI-1 驗證：BTC→ETH lead-lag 是否存在？
| 相關性類型 | Pearson 係數 | 解讀 |
|-----------|-------------|------|
| 同期 Pearson(BTC_t, ETH_t) | **+0.8461** | 高度同期相關（系統性同步） |
| Lead-lag Pearson(BTC_t, ETH_{t+1}) | **-0.0389** | 幾乎為零，BTC 日線不領先 ETH |
| 反向 Pearson(ETH_t, BTC_{t+1}) | **-0.1021** | 同樣接近零 |

**關鍵發現**：BTC 與 ETH 日線的 lead-lag 相關性接近零（-0.04），遠不如同期相關（+0.85）。這驗證了 skeptic EI-1 的質疑：**coherence（頻率域相干性）≠ 時域 lead-lag**，日線頻率下 BTC 並不領先 ETH。

### 預測力指標（多 horizon）
| Horizon | Rank-IC | IC Std | IC-IR | IC>0% | 門檻通過 |
|---------|---------|--------|-------|-------|----------|
| 1 日 | +0.0302 | 0.1112 | +0.272 | 57.0% | FAIL（差距0.028）|
| 5 日 | -0.0526 | 0.0938 | -0.561 | 29.9% | PASS（均值回歸方向）|
| 10 日 | -0.0417 | 0.1121 | -0.372 | 38.8% | PASS |
| 20 日 | -0.0786 | 0.1471 | -0.534 | 37.0% | PASS |

**通過門檻**：3/4 horizon（H=5/10/20d 通過，IC-IR 門檻 0.3）
**注意**：H=5/10/20d IC 為**負值**，意味著「高相干性→ ETH 未來報酬低」（**反向**預測，與因子原始假設方向相反）

### 分組回報（5 組，5 日 horizon）
| 組別 | 平均 5 日報酬 |
|------|-------------|
| Q1 (lowest coherence) | -0.27% |
| Q2 | -0.28% |
| Q3 | +0.62% |
| Q4 | +0.21% |
| Q5 (highest coherence) | -0.28% |
| **Q5-Q1 spread** | **-0.01%（近零，無線性單調）** |

### 穩健性檢查
- [x] 前視偏誤：F9 使用 rolling 窗口計算 coherence，t 時刻僅用 ≤ t 的數據
- [x] 缺值處理：NaN 佔 4.0%（rolling 暖身期），dropna 後計算
- [x] 極端值處理：winsorize 1% 後 zscore 標準化
- [x] 多 horizon 一致性：H=5/10/20d IC 均為負且方向一致，**均值回歸模式**（高相干性後反轉）
- [x] lead-lag 基礎驗證：Pearson(BTC_t, ETH_{t+1}) = -0.039，日線 lead-lag 不存在

### 與現有策略關聯
- 跨因子正交性：F9 vs F7 Pearson = 0.139（低相關）；F9 vs F8 未直接計算（預計低相關）
- 同期 BTC/ETH 相關性 0.85 說明兩者高度聯動，信號的獨立性主要來自相干性的**變化**而非水準

### 實證結論（供 arbiter 參考）
1. **lead-lag 假設在日線頻率不成立**：Pearson(BTC_t, ETH_{t+1}) = -0.039 接近零，因子原始假設（BTC 領先 ETH）在日線頻率下無實證支持。
2. **反向預測力存在**：H=5/10/20d IC-IR 均通過門檻（絕對值 0.37~0.56），但方向為**負**（高相干性預測 ETH 未來報酬偏低）。這可能揭示「高相干 regime 下跟隨效應飽和後的均值回歸」。
3. **分組回報無單調性**：Q5-Q1 spread ≈ 0，線性因子假設不成立，非可靠量化信號。
4. **建議（revise）**：(a) 改為 1H/4H 數據驗證短週期 lead-lag；(b) 或以反向（負相干性）作為均值回歸信號，但需解釋機制；(c) skeptic CL-1 指出高波動 regime 失效問題，需分 regime 子集測試。
