# Factor-Lab — 多代理量化因子研究系統

Factor-Lab 是一套基於 LLM 多代理辯論的自動化量化因子研究管線。它讓不同角色的 AI Agent 圍繞候選 alpha 因子進行完整辯論——從假設提出、程式實作、五維批判、歷史回測、仲裁裁決到知識庫歸檔——模擬一個小型量化研究團隊的協作流程。

## 設計理念

傳統量化研究瓶頸在於：(1) 文獻追蹤費時、(2) 因子假設容易陷入資料探勘、(3) 回測過擬合無人把關、(4) 研究成果散落各處難以復用。Factor-Lab 以結構化辯論取代個人主觀判斷，每個因子的存活必須通過 Proposer 的經濟直覺論證、Skeptic 的五維批判、Empiricist 的嚴格回測（含 PBO 校正）、以及 Arbiter 的綜合裁決——四個角色相互制衡，降低假陽性率。

## 系統架構

```
factor-lab/
├── config.yaml              # 全域設定：路徑、gate 門檻、pipeline 參數
├── index.db                 # SQLite 索引庫（文獻、因子、證據、辯論記錄）
├── dashboard.html           # 自包含 Mission Control 儀表板
├── sources.yaml             # RSS/文獻來源設定
├── requirements.txt         # Python 相依套件
│
├── core/                    # 核心引擎
│   ├── kb.py                # 知識庫存取層（Obsidian vault + SQLite）
│   ├── backtest.py          # ADRS 回測框架（PBO/Purged CV/WF/Sensitivity）
│   ├── metrics.py           # 效能指標運算（Sharpe、IC-IR、Rank-IC 等）
│   ├── gate.py              # Gate 機器檢查（soul question 字數、回測數字門檻）
│   ├── stages.py            # 階段狀態機（Stage 0-5 + Graveyard + Rework）
│   ├── memory.py            # Factor memory 模組（paper_insights + design_constraints 自動注入）
│   └── signals/             # 因子訊號函數（F1-F9）
│       ├── F1_Complexity_Gap_Regime.py
│       ├── F2_Liquidity_Consumption_Tilt.py
│       ├── F3_Volatility_Roughness_Filter.py
│       ├── F4_Flow_Divergence_Ratio.py
│       ├── F5_Anchored_Mean_Reversion_Score.py
│       ├── F6_Return_Asymmetry_Premium.py
│       ├── F7_session_gap_momentum_decomposition.py
│       ├── F8_cubic_momentum_threshold_reversal.py
│       └── F9_cross_asset_lead_lag_coherence.py
│
├── scripts/                 # 可執行腳本
│   ├── debate_flow.py       # 辯論管線編排（Proposer→Builder→Skeptic→Empiricist→Arbiter→Librarian）
│   ├── data_sync.py         # Binance REST → Parquet(zstd) 資料同步
│   ├── generate_report.py   # Plotly 4-row HTML 互動報表（K 線/權益/回撤/Rolling Sharpe）
│   ├── generate_dashboard.py # Mission Control 儀表板產生器
│   ├── daily_refresh.py     # 日度儀表板更新
│   ├── midweek_refresh.py   # 週中資料同步+回測重跑+儀表板更新
│   └── librarian_archive.py # Librarian 歸檔腳本
│
├── ingestion/               # 資料攝取
│   ├── watcher.py           # RSS 文獻監控（arXiv、Robot Wealth、Glassnode）
│   └── threads_poller.py    # Threads 平台輪詢
│
├── data/                    # 市場資料（Parquet zstd）
│   ├── btcusdt_1d.parquet
│   └── ethusdt_1d.parquet
│
├── validated/               # 已驗證因子（Obsidian 筆記 + 訊號函數備份）
│   ├── F4_flow_divergence_ratio.md
│   ├── F4_Flow_Divergence_Ratio.py
│   ├── F5_anchored_mean_reversion_score.md
│   ├── F5_Anchored_Mean_Reversion_Score.py
│   └── factors/
│       └── F8_cubic_momentum_threshold_reversal.md
│
├── candidates/              # 候選因子（等待辯論）
│   ├── F7_session_gap_momentum_decomposition.md
│   └── done/                # 已完成辯論的候選
│       ├── F8_cubic_momentum_threshold_reversal.md
│       └── F9_cross_asset_lead_lag_coherence.md
│
└── deprecated/              # 已淘汰因子（保留完整辯論記錄）
    └── F9_cross_asset_lead_lag_coherence.md
```

## 代理角色 (Agent Roles)

Factor-Lab 的辯論管線由七個專業化 AI Agent 角色組成，每個角色有明確的職責邊界與輸出格式：

| 角色 | 職責 | 模型策略 |
|------|------|----------|
| **Orchestrator** (Conductor) | 接收自然語言指令，調度完整辯論管線；分配角色、傳遞上下文、裁決爭議 | DeepSeek V3 |
| **Proposer** (Ideator) | 基於 vault 知識庫與論文洞見提出新因子假設；回答 Soul Questions 六問 | DeepSeek V3 |
| **Skeptic** | 對候選因子執行五維批判：資料探勘 / 經濟直覺 / 前視偏誤 / 重複造輪 / 成本流動性 | Claude Sonnet 4.6 |
| **Builder** (Engineer) | 將因子假設轉為精確可計算的 Python 函數，確保無前視偏誤 | Claude Sonnet 4.6 |
| **Empiricist** (Quant) | 用歷史行情量化因子預測力；產出 Rank-IC / IC-IR / 分組回報 / 相關性矩陣 | Claude Sonnet 4.6 |
| **Arbiter** (Judge) | 綜合 Proposer/Skeptic/Empiricist 所有證據，做出 PASS / REJECT / REWORK 裁決 | Claude Opus |
| **Librarian** | 裁決後歸位、去重、建連結、更新知識庫索引 | DeepSeek V3 |

角色分配策略採用「判斷層 Opus、執行層 Sonnet、整理層 V3」的階梯式模型選擇，平衡成本與推理品質。

## 辯論管線 (Debate Pipeline)

每輪辯論遵循嚴格的順序管線，由 Orchestrator 編排：

```
Proposer (提出假設)
    │
    ▼
Builder (程式實作)
    │
    ├──► Skeptic (五維批判) ──┐
    │                          ├──► Arbiter (綜合裁決)
    └──► Empiricist (歷史實證) ─┘          │
                                   ┌───────┼───────┐
                                   ▼       ▼       ▼
                                 PASS   REJECT  REWORK
                                   │       │       │
                                   ▼       ▼       ▼
                              Librarian  Graveyard 回 Proposer (限一次)
```

### Gates（品質門檻）

系統設有三道 Gate，確保只有嚴格的因子能存活：

1. **Gate 0 — Soul Questions 檢查**
   - 六個靈魂提問每題需 ≥ 100 字
   - 至少 4/6 題通過（可配置）
   - 去重檢查：與既有/已死策略重複則自動淘汰

2. **Gate 2 — Mini Backtest**
   - Sharpe ≥ 0.0（預篩階段寬鬆）
   - PBO ≤ 0.3（過擬合控制）
   - 交易次數 ≥ 20
   - 最大回撤 ≤ 45%

3. **Gate 3 — Full Backtest**
   - Sharpe ≥ 0.5
   - OOS Sharpe ≥ 0.25
   - PBO ≤ 0.3
   - WF Decay ≥ 0.3（樣本外穩定性）
   - 交易次數 ≥ 20

所有 Gate 門檻在 `config.yaml` 中可配置。

### 階段狀態機 (Stage Machine)

因子遵循嚴格的生命週期狀態機，不可跳級、不可繞 Gate：

```
stage_0 (Alpha Idea)
  → stage_1 (Research)
  → stage_2 (Factor Dev)
  → stage_3 (Full Backtest)
  → stage_4a (Paper Trade, 未實作)
  → stage_4b (Small Capital, 未實作)
  → stage_5 (Live, 未實作)
  → graveyard (終態)

rework: 任一階段可退回一次，第二次退回強制進 graveyard
```

轉換記錄寫入 `index.db` 的 `transitions` 表供審計追蹤。

## 回測框架 (ADRS)

回測引擎基於 **ADRS**（Anti-Data-Snooping Robust Strategy）框架，整合多層過擬合防護：

- **Purged Walk-Forward CV**：訓練/測試集之間加入 purge gap，確保資訊不跨區洩漏
- **PBO (Probability of Backtest Overfitting)**：透過排列測試量化過擬合機率
- **Sensitivity Analysis**：參數擾動下策略穩定性評估
- **OOS Testing**：嚴格樣本外驗證，訓練集與測試集時間順序隔離
- **分段 WF Decay**：檢測樣本外表現是否隨時間衰減（alpha decay）

### 效能指標

| 指標 | 說明 |
|------|------|
| Rank-IC | 因子排序與未來報酬的 Spearman 相關 |
| IC-IR | IC 的資訊比率（均值/標準差）|
| Sharpe Ratio | 年化夏普比率 |
| OOS Sharpe | 樣本外獨立測試的夏普比率 |
| Long-Short Annual Return | 多空組合年化報酬 |
| Max Drawdown | 最大回撤 |
| Trade Count | 交易次數（確保統計顯著性）|
| PBO | 回測過擬合機率（目標 ≤ 0.3）|
| WF Decay | 樣本外表現衰減率（目標 ≥ 0.3）|

## 因子庫 (Factor Library)

目前已實現 9 個因子（F1-F9），涵蓋 regime detection、microstructure、momentum、value、flow、cross-asset 六大類別：

| ID | 名稱 | 類別 | 狀態 | 核心公式 |
|----|------|------|------|----------|
| F1 | Complexity Gap Regime | regime | 實作 | RMT eigenvalue gap 相位切換 |
| F2 | Liquidity Consumption Tilt | microstructure | 實作 | BVOL/SVOL 不平衡 × 價格方向 |
| F3 | Volatility Roughness Filter | volatility | 淘汰 | 日線無法捕捉粗糙度特徵 |
| F4 | Flow Divergence Ratio | flow | **條件驗證** | signal = -EMA(price_mom_z × vol_mom_z, hl=10) |
| F5 | Anchored Mean Reversion Score | value | **驗證通過** | signal = EMA((VWAP₂₀−close)/ATR₁₄, hl=5) |
| F6 | Return Asymmetry Premium | carry | 淘汰 | skew × vol，經濟邏輯反轉致命 |
| F7 | Session Gap Momentum Decomposition | microstructure | 候選 | gap_ratio × sign_concordance |
| F8 | Cubic Momentum Threshold Reversal | momentum | 條件驗證 | CMI = (M−a)(M−b)(M−c) 三次多項式 |
| F9 | Cross-Asset Lead-Lag Coherence | cross_asset | 淘汰 | BTC→ETH coherence 條件訊號 |

### 因子設計約束

所有因子訊號函數必須遵守以下規範（由 memory 模組自動注入 Proposer/Builder）：

1. **無前視偏誤**：`signal[t]` 僅使用 `≤ t` 時刻的資料；`.shift(-1)` 對齊由 Empiricist 完成
2. **標準介面**：輸入 `OHLCV [{ts, open, high, low, close, volume}]`，輸出 `{'signal': np.ndarray, 'meta': dict}`
3. **輸入驗證**：處理 NaN / ≤0 close / 負 volume / 空列表
4. **宣告式來源**：Soul Q5 必須明確指定資料來源與所需欄位
5. **純 numpy 或 pandas**，不引入重型 ML 框架
6. **多標的相容性**：若適用，函數需處理多 symbol 的 DataFrame

## 資料管線

### 市場資料

- **來源**：Binance Public REST API `GET /api/v3/klines`
- **頻率**：日線（OHLCV）
- **標的**：BTC/USDT、ETH/USDT
- **格式**：Parquet (zstd 壓縮)，儲存於 `data/`
- **同步**：`scripts/data_sync.py` 支援 fetch / backfill / validate / fetch-all
- **排程**：每 5 分鐘 tick（cron）+ 週三 04:00 全量刷新（midweek_refresh.py）

### 文獻攝取

- **來源**：arXiv (quant-fin)、Robot Wealth Blog RSS、Glassnode Research RSS
- **排程**：每日 08:00 + 20:00（watcher.py）
- **歸檔**：完整全文寫入 Obsidian vault (`量化交易/06-书籍论文/`)，含 YAML frontmatter
- **去重**：透過 sha1 指紋檢查避免重複歸檔

### Glassnode 視覺化

- **排程**：每日 09:00 + 21:00
- **流程**：下載 Glassnode 圖表 → Gemini 2.5 Pro 視覺分析 → 更新 Obsidian 筆記

## 報告系統

### 因子回測報告 (`scripts/generate_report.py`)

產生暗色主題 Plotly 互動 HTML，包含四行圖表：
1. **K 線圖 + 進出場標記**：綠色向上箭頭（做多）、紅色向下箭頭（做空）
2. **權益曲線**：策略累積報酬 + buy-and-hold 基準
3. **回撤曲線**：滾動最大回撤百分比
4. **Rolling Sharpe**：滾動 60 日年化夏普比率

支援瀏覽器中縮放、平移、hover 細節。

### Mission Control Dashboard (`scripts/generate_dashboard.py`)

自包含 HTML 單頁儀表板，無 Tab 切換——所有資訊一頁呈現：
- **Top Bar**：系統運行時長、最後同步時間
- **Side Nav**：快速導航
- **System Health**：資料新鮮度、因子狀態摘要
- **KB Stats**：文獻數量、因子庫規模、辯論次數
- **Agent Team**：七個代理的狀態面板（角色/模型/能力/當前任務）
- **Pipeline**：最近辯論 session 摘要
- **Log Stream**：系統事件時間線

### 品質門檻

報告要求多維度品質標準（非單一條件）：
- 年化報酬 ≥ 25% **AND**
- Sharpe Ratio ≥ 1.0
- 以 HTML 互動報表為主要輸出格式

## 知識庫整合

Factor-Lab 深度整合 Obsidian vault (`/home/anson/Documents/Obsidian Vault/量化交易/`)：

```
量化交易/
├── 01-交易策略/       # 策略設計文件
├── 02-市场数据/       # 市場資料筆記
├── 03-回测框架/       # 回測方法論
├── 04-风险管理/       # 風險模型
├── 05-编程技术/       # 實作技術
├── 06-书籍论文/       # 文獻全文歸檔
├── 07-交易心理/       # 行為金融
├── 08-工具资源/       # 工具與資源
├── 09-作者专题/       # 按作者組織的專題索引
└── 10-因子库/         # 因子知識庫（驗證後歸位）
```

- **文獻歸檔**：完整 YAML frontmatter (date/author/source/tags)、YYYY-MM-DD 格式檔名、每作者一個索引頁
- **因子歸位**：PASS 因子寫入 `10-因子库/`；REJECT 因子記錄淘汰原因保留完整辯論
- **雙向連結**：因子筆記之間透過 `[[wikilink]]` 建立交叉引用（相關論文、互補因子、來源洞見）

## 使用方式

### 1. 環境安裝

```bash
cd /home/anson/factor-lab
pip install -r requirements.txt
```

核心依賴：`numpy`, `pandas`, `polars`, `scipy`, `plotly`, `pyyaml`, `alphapurify`（完整清單見 `requirements.txt`）

### 2. 資料同步

```bash
# 抓取最新資料
python scripts/data_sync.py --fetch-all

# 回補歷史資料
python scripts/data_sync.py --backfill BTC/USDT 1d --days 365

# 驗證資料完整性
python scripts/data_sync.py --validate BTC/USDT 1d
```

### 3. 執行辯論

辯論透過 Hermes Agent 驅動，由 factor-lab 技能群協調：

```
Orchestrator 接收自然語言指令 → 依序調度 Proposer/Builder/Skeptic/Empiricist/Arbiter/Librarian
```

具體命令範例（在 Hermes Agent 環境中）：

```
請根據最新論文洞見提出 3 個新的候選因子，並執行完整辯論管線
```

### 4. 產出報告

```bash
# 單品種回測報告
python scripts/generate_report.py --symbol BTC/USDT --output report_btc.html

# 儀表板
python scripts/generate_dashboard.py

# 用瀏覽器打開
google-chrome --new-window report_btc.html
```

### 5. Cron 排程

系統依賴以下 cron 任務維持自動化運轉（透過 Hermes cronjob 管理）：

| 排程 | 任務 | 說明 |
|------|------|------|
| 每 5 分鐘 | live trading simulation tick | 即時交易模擬 |
| 每日 04:05 | SuperTrend TST | 策略測試 |
| 每日 08:00, 20:00 | 文獻 watcher | arXiv + RW + Glassnode RSS |
| 每日 09:00, 21:00 | Glassnode visual | 圖表下載 + 視覺分析 |
| 週三 04:00 | Midweek refresh | 資料同步 + 回測重跑 + 儀表板 |

## 配置說明

`config.yaml` 主要區段：

```yaml
kb:
  vault_root: "/home/anson/Documents/Obsidian Vault/量化交易"
  index_db: "/home/anson/factor-lab/index.db"
  paths:
    papers: "06-书籍论文"
    author: "09-作者专题"
    factor: "10-因子库"

cetus:
  gates:
    gate0:
      soul_min_chars: 100
      soul_min_score: 4
    gate2:
      mini_sharpe_min: 0.0
      pbo_max: 0.3
      trade_count_min: 20
      max_dd_max: 0.45
    gate3:
      sharpe_min: 0.5
      oos_sharpe_min: 0.25
      pbo_max: 0.3
      wf_decay_min: 0.3
      trade_count_min: 20
```

## Soul Questions（靈魂六問）

每個候選因子在 Gate 0 必須回答六個問題，這是 Proposer 的核心輸出：

1. **為什麼這個 alpha 現在會存在？** — 必須提供結構性原因（市場微結構、行為偏差、制度摩擦），不接受「別人還沒發現」
2. **什麼會殺死它？** — 失效條件的具體場景，證明你理解 alpha 的邊界
3. **對手方是誰？** — 具名對手方（HFT 做市商、CTA、散戶），證明你知道在賺誰的錢
4. **一句話描述** — 用白話解釋經濟機制的核心
5. **資料來源** — 明確的 API、頻率、所需欄位、歷史長度
6. **Alpha 衰減速度** — 估計衰減週期並提供理由（半衰期預測）

## 設計決策記錄

### 為何採用多代理辯論而非單一 LLM？

- **假陽性控制**：單一 LLM 傾向過度樂觀地批准自己的假設；引入 Skeptic 的角色制衡顯著降低假陽性率
- **專業化**：Proposer 生成假設、Skeptic 尋找漏洞、Empiricist 計算證據、Arbiter 綜合裁決——角色分離避免「又當球員又當裁判」
- **可審計**：每個角色的完整輸出保留在 Obsidian vault，任何裁決都可追溯

### 為何使用 PBO 而非僅 Sharpe 作為品質門檻？

Sharpe 容易被過擬合最大化（透過參數網格搜尋），PBO 透過排列測試量化「這個 Sharpe 是否可能來自隨機資料探勘」。系統要求 Gate 3 必須 PBO ≤ 0.3（即策略真實有效的後驗機率 ≥ 70%）。

### 為何 Rework 限制一次？

實證顯示：需要多次 Rework 的因子通常是經濟直覺有根本缺陷、靠調整參數勉強過關。第二次被退回直接 Graveyard 避免無窮迴圈。

### F3 淘汰教訓

Volatility Roughness Filter 依賴 Hurst 指數的粗糙度特徵，但日線頻率無法捕捉微觀結構的粗糙度（需要 tick/分鐘級數據）。此淘汰記錄作為「頻率-特徵」匹配的前車之鑑，注入 memory 模組的 design_constraints。

### F6 淘汰教訓

Return Asymmetry Premium 的經濟邏輯被 Skeptic 證明是反轉的：負偏態資產應該有正溢酬（風險補償），而非負溢酬。致命經濟邏輯錯誤無法透過參數調整修正，直接淘汰。

## 相關技能 (Skills)

Factor-Lab 以 Hermes Agent 技能群實現，各角色對應獨立技能：

- `factor-lab` — 系統總覽與基礎設施
- `factor-lab-orchestrator` — 辯論管線調度
- `factor-lab-proposer` — 因子假設生成
- `factor-lab-skeptic` — 五維批判
- `factor-lab-builder` — Python 訊號函數實作
- `factor-lab-empiricist` — 歷史實證回測
- `factor-lab-arbiter` — 證據綜合裁決
- `factor-lab-librarian` — 知識庫歸檔
- `financial-research-report` — 金融研究報告撰寫

## 故障排除

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| 資料同步失敗 | Binance API 限流 | 等待 1 分鐘後重試；檢查 `data/` 目錄權限 |
| 回測輸出全 NaN | 資料不足（< 60 根 K 線） | 使用 `--backfill` 補足歷史資料 |
| Gate 0 卡在 soul score < 4 | Soul Questions 答案太短 | 每題需 ≥ 100 字，檢查 `config.yaml` 中的 `soul_min_chars` |
| PBO 過高 | 參數過度最佳化 | 減少參數自由度、檢查前視偏誤、增加 purge gap |
| Obsidian vault 寫入失敗 | 路徑不存在或權限不足 | 確認 `config.yaml` 中的 `vault_root` 正確且有寫入權限 |
