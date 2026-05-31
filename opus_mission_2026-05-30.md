# Opus 4.8 MAX 作戰指令：新因子發現與策略設計
**日期**：2026-05-30
**目標**：以最嚴謹的量化研究流程，構思 2-3 個全新因子（不得與既有因子重複），設計完整交易策略，回測驗證，撰寫正式研究報告，歸檔至 Obsidian 知識庫。

---

## 一、既有因子庫（不得重複提案）

### validated（6 個，已通過完整辯論）
| # | 因子 | 類別 | 公式核心 | IC-IR | Sharpe |
|---|------|------|---------|-------|--------|
| F1 | SuperTrend(10,3)+ADX(20,40)+Vol≥1.1 | trend | ST方向 + ADX區間過濾 + 成交量確認 | - | 1.40 |
| F2 | complexity_gap_regime | regime | Δ=λ_max_norm−ρ, clip((Δ−0.035)/0.04) | -0.531 | - |
| F3 | volume_weighted_direction_tilt | microstructure | LCT=EMA((BuyVol−SellVol)/TotalVol,10) | -1.03 | - |
| F4 | flow_divergence_ratio | flow | FDR=EMA(price_mom_z×vol_mom_z,10); signal=−FDR | 0.676 | - |
| F5 | anchored_mean_reversion_score | value | AMRS=EMA((vwap_20−close)/ATR_14,5); signal=−AMRS | 1.003 | - |
| F6 | cubic_momentum_threshold_reversal | momentum_reversal | Z=(R_0τ−mean_R)/std_R → sigmoid(Z) | 0.31 | 1.192 |

### deprecated（3 個，已淘汰）
| # | 因子 | 淘汰原因 |
|---|------|---------|
| F7 | volatility_roughness_filter | 日線數據解析度不足，Hurst指數無法可靠計算 |
| F8 | return_asymmetry_premium | IC-IR=0.309，邊緣，arbiter裁決淘汰 |
| F9 | cross_asset_lead_lag_coherence | IC-IR=0.11，無預測力 |

---

## 二、最新情報（今日下載論文，可作靈感來源）

以下為 2026-05-30 補強行動中新增至 vault 的論文（`06-书籍论文/`），挑選與量化因子直接相關者：

**波動率曲面與定價**：
- Volatility Surface Reconstruction using Deep Learning (2026-05-20)
- American Option Pricing Under Time-Varying Rough Volatility (2025-08-10)

**隨機控制與最優執行**：
- Optimal Control of Ethena Yield Stablecoin (2026-05-11)
- Optimal Investment and Entropy-Regularized Learning Under Stochastic Drift (2026-04-24)
- Entropy Regularization under Bayesian Drift Uncertainty (2026-02-18)

**貝氏方法與投資組合理論**：
- Bayesian Portfolio Optimization by Predictive Synthesis (2025-10-08)
- Bayesian Quantile-Based Portfolio Selection (2020-12-03)

** regime switching / HMM**：
- Regime-Based Portfolio Allocation Using Hidden Markov Models (2026-05-27)

**市場微結構**：
- Deep Limit Order Book Forecasting (2024-03-14)
- The Privacy Subsidy: Kyle's λ under Noise-Perturbed Order-Flow (2026-05-15)
- Learning Market Making with Closing Auctions (2026-01-24)

**另類數據與非線性**：
- Nonlinear and Heavy-Tailed Predictability in Transition-Energy Markets (2026-05-26)
- A Framework for Predictive Directional Trading Based on Volatility and Causal Inference (2025-07-14)

**深度學習與合成數據**：
- TRADES: Generating Realistic Market Simulations with Diffusion Models (2025-01-31)

---

## 三、可用武器（回測基礎設施）

### A. factor-lab 核心模組（`/home/anson/factor-lab/core/`）
```python
# 回測引擎
from core.backtest import backtest_factor, walk_forward_backtest
# 指標
from core.metrics import rank_ic, ic_series_stats, forward_returns, sharpe_ratio, max_drawdown
# 預處理
from core.preprocessing import preprocess_factor  # winsorize, zscore, neutralization
# 行情適配器
from core.adapters.crypto import CryptoAdapter  # Binance REST API
# 去重
from core.dedup import cosine_similarity  # 檢查與既有因子重複度
# 曝險
from core.exposures import sector_exposure, factor_exposure
```

### B. 即時模擬引擎（`/home/anson/quant-btc-gold/sim/`）
```python
# SuperTrend 完整回測（含進出場標記、權益曲線、回撤）
from sim.supertrend_full_backtest import run_full_backtest
# Sharpe 突破掃描
from sim.sharpe_breakthrough import run_sharpe_scan
# 多時間框架
from sim.sharpe_multitf import run_multitf_backtest
```

### C. 因子實作目錄
- 信號檔案：`/home/anson/factor-lab/core/signals/F<n>_<name>.py`
- 每個信號檔案含 `factor(df) -> pd.Series` 函數
- 既有信號檔案在 `core/signals/` 可作參考

### D. 回測參數（`config.yaml`）
```yaml
research:
  ic_horizon_days: 5
  ic_min_abs: 0.02        # 最低 |Rank-IC|
  ic_ir_min: 0.3          # 最低 IC-IR
markets:
  crypto:
    exchange: binance
    universe: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    timeframe: "1d"
cetus:
  gates:
    gate2:
      mini_sharpe_min: 1.0
      pbo_max: 0.5
      trade_count_min: 30
      max_dd_max: 0.40
    gate3:
      sharpe_min: 1.5
      oos_sharpe_min: 1.2
      pbo_max: 0.4
      wf_decay_min: 0.5
      trade_count_min: 100
```

---

## 四、任務要求

### Phase 1：因子構思（2-3 個全新因子）
1. **先讀既有因子**：讀取 `10-因子库/validated/` 和 `10-因子库/deprecated/` 中所有 .md 檔案，確保不重複
2. **瀏覽最新論文**：從上方「最新情報」中挑選 3-5 篇精讀，提取量化洞見
3. **構思新因子**：每個因子必須有：
   - 清晰的經濟/行為直覺（不是事後硬湊）
   - 結構性理由（為什麼不會被套利掉）
   - 精確的數學公式（可直接實作）
   - 預期方向與失效條件
4. **去重檢查**：與既有 9 個因子做相關性/概念去重

### Phase 2：回測驗證（每個因子獨立）
1. **實作因子函數**：寫入 `core/signals/F<n>_<name>.py`，函數簽名 `factor(df) -> pd.Series`
2. **數據取得**：使用 CryptoAdapter 拉取 BTC/USDT 日線（取最大可用歷史）
3. **完整回測**：
   - Rank-IC + IC-IR（多 horizon：1/5/10/20 日）
   - 分組回報（5 組，Q5-Q1 spread）
   - 累積 IC 曲線
   - 與既有因子相關性矩陣
4. **策略層級回測**（至少對最優因子）：
   - 基於因子信號生成交易規則（進出場邏輯）
   - Walk-forward 回測
   - 權益曲線 + 回撤曲線
   - Sharpe ratio + 年化報酬 + 最大回撤
   - PBO（Probability of Backtest Overfitting）近似
5. **多標的驗證**：若因子邏輯泛用，至少在 BTC 和 ETH 上測試

### Phase 3：報告撰寫（繁體中文，學術標準）
每篇報告結構：
1. **摘要**（200 字）
2. **經濟直覺與假設**（文獻支撐）
3. **數學定義與實作細節**
4. **實證結果**（表格＋圖表）
   - Rank-IC 多 horizon 表
   - 分組回報表
   - 權益曲線（若產出圖表路徑，標註）
5. **穩健性檢查**
   - 前視偏誤檢查
   - 參數敏感度分析
   - 極端市場行為討論
   - 與既有因子相關性
6. **交易策略設計**（將因子轉換為可執行策略）
   - 進場條件
   - 出場條件
   - 部位規模
   - 風險管理
7. **限制與後續工作**

### Phase 4：歸檔（Obsidian Vault）
1. **因子筆記**：寫入 `10-因子库/candidates/F<n>_<name>.md`，含完整 frontmatter
2. **研究報告**：完整報告寫入 `12-深度研究/` 或 `06-书籍论文/`
3. **交易策略**：策略筆記寫入 `01-交易策略/` 對應子目錄
4. **更新 MOC**：在 `📊-量化交易知识库-MOC.md` 中添加新因子/策略連結
5. **因子信號檔案**：保留在 `core/signals/`

---

## 五、品質門檻（嚴禁放水）

### 因子級別
- |Rank-IC| ≥ 0.02（均值）
- IC-IR ≥ 0.3
- IC>0 比例 ≥ 55%（或 IC<0 ≥ 55%，若方向一致為負）
- 分組 Q5-Q1 spread 單調性（至少大致單調）

### 策略級別
- 年化報酬 ≥ 25%
- Sharpe ratio ≥ 1.0
- 最大回撤 ≤ 40%
- 交易次數 ≥ 30（避免過度擬合少數交易）
- 樣本外 Sharpe ≥ 樣本內 Sharpe × 0.5（Walk-forward）

### 報告級別
- 每個主張必須有數據支撐
- 每個數字必須可重現（附程式碼路徑）
- 負面結果如實報告（不美化）
- 不達標因子明確標記為「未通過」並記錄原因

---

## 六、禁止事項
- ❌ 不得與既有 9 個因子重複（概念或公式高度相似）
- ❌ 不得使用未來數據（前視偏誤）
- ❌ 不得美化或選擇性報告回測結果
- ❌ 不得跳過穩健性檢查
- ❌ 不得在日線數據上使用需要 tick/分鐘級數據的因子（如 Hurst、roughness、microstructure timing）
- ❌ 不得使用付費數據源（僅 Binance 公開 API）

---

## 七、執行方式
- 工作目錄：`/home/anson/factor-lab/`
- Vault：`/home/anson/Documents/Obsidian Vault/量化交易/`
- 每一步先讀取相關檔案理解現狀，再行動
- 所有 Python 腳本可直接執行，無需虛擬環境（系統 Python 已含 pandas/numpy/scipy/ccxt）
- 產出檔案使用繁體中文

---

**開始執行。嚴謹為上。**
