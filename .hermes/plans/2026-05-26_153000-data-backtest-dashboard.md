# 建置計劃：06-DATA-AND-BACKTEST + 05-UI-DASHBOARD

## 目標

將 alpha_agent_plantform 的資料管線、回測引擎、儀表板實作到 factor-lab。

## 約束

- 無 Docker、無 PostgreSQL、無 Redis — 全部單機檔案系統
- Parquet + DuckDB 代替資料庫（既有設計）
- Dashboard 使用自包含 HTML（無伺服器），符合使用者現有偏好
- 暗色主題，對齊 05-UI-DASHBOARD.md 的 design tokens
- 費用模型：0.09% per side

---

## Part A：06-DATA-AND-BACKTEST（資料管線 + 回測引擎）

### A1. 資料同步管線

**檔案**: `scripts/data_sync.py`

功能：
- `fetch_and_store(symbol, timeframe)` — CCXT 拉 OHLCV，增量寫入 parquet (zstd)
- `validate_ohlcv(df)` — 檢查排序、缺口、OHLCV 邏輯、零成交量
- `backfill(symbol, timeframe, days)` — 手動補洞
- CLI 介面：`--fetch BTCUSDT 1d`, `--backfill BTCUSDT 1d --days 365`, `--validate BTCUSDT 1d`
- 輸出目錄：`data/btc_1d.parquet`, `data/eth_1d.parquet` 等

**驗證**：
- 執行 `python scripts/data_sync.py --fetch BTCUSDT 1d` 產生 parquet 檔案
- 用 `duckdb.sql("SELECT count(*) FROM 'data/btc_1d.parquet'")` 確認筆數 > 500

### A2. 回測引擎（ADRS 框架）

**檔案**: `core/backtest.py`

功能：
- `BacktestEngine` 類別
  - `.run_mini(signal, returns)` — Stage 2: Rank-IC, IC-IR, quantile returns, cumulative IC
  - `.run_adrs(signal, returns)` — Stage 3: PBO, Purged CV, Walk-Forward, Sensitivity
- `compute_pbo(returns, n_trials=1000)` — López de Prado (2016) Probability of Backtest Overfitting
- `purged_cv(signal, returns, n_splits=5)` — Purged Cross-Validation with TimeSeriesSplit + purge gap
- `walk_forward(signal, returns, train_years=1, test_months=3)` — Rolling walk-forward Sharpe
- `sensitivity_analysis(factor_fn, df, param_ranges)` — Optuna-based ±20% 網格
- `residual_alpha(new_returns, known_factors)` — OLS regression 取獨立 alpha
- 費用模型：`apply_costs(returns, signals, cost_per_side=0.0009)`

**既有可復用**：`core/adapters/crypto.py` (CryptoAdapter), `core/metrics.py` (rank_ic), `core/preprocessing.py`

**驗證**：
- 對既有 F1 (Complexity Gap) 跑 mini backtest → 確認 IC-IR 與之前計算一致
- 對既有 F5 (AMRS) 跑 full ADRS → 確認無 crash

### A3. HTML 互動回測報表

**檔案**: `scripts/generate_report.py`

功能：
- 讀取回測結果 → 產生單一 HTML 檔案
- 四個子圖 (Plotly make_subplots, rows=4)：
  1. K 線圖 + 進出場標記
  2. 權益曲線 (log scale)
  3. 回撤曲線 (filled area)
  4. 滾動 Sharpe (90-day)
- 暗色主題對齊 design tokens
- 自動開啟 Chrome

**驗證**：
- 跑 `python scripts/generate_report.py --factor F5` → 產出 HTML → Chrome 顯示四個圖

---

## Part B：05-UI-DASHBOARD（Mission Control 儀表板）

### 設計決策：自包含 HTML，非 Next.js

理由：
- 無 Docker、無 Redis、無 Node.js 伺服器 — 規格中的 SSE 推送不適用
- 使用者已偏好 HTML 互動報表（Plotly, 暗色主題, Chrome 開啟）
- 單一檔案可攜、不需要部署
- Dashboard 資料從 index.db + debate_state.json 讀取，嵌入 HTML

### B1. Dashboard 生成器

**檔案**: `scripts/generate_dashboard.py`

功能：
- 讀取 factor-lab 所有狀態 → 產生 `dashboard.html`
- 可定時重新生成（cronjob 每小時）或手動

### B2. Dashboard 頁面（單頁應用，4 個 tab）

**檔案**: `scripts/generate_dashboard.py` 內嵌 HTML 模板

#### Tab 1：Factor Registry（因子庫概覽）
- 表格：名稱 | 類別 | IC-IR | Sharpe | Status | Vault 路徑
- 狀態顏色：active=綠、conditionally_validated=橘、deprecated=灰
- 按類別分組，可排序
- 頂部摘要：N 有效因子、N 條件驗證、N 淘汰

#### Tab 2：Pipeline（辯論管線）
- 漏斗圖 (Plotly Funnel)：proposer → builder → skeptic → empiricist → arbiter → librarian
- 每階段通過率
- 最新辯論記錄表格：日期 | 因子數 | Validated | Rejected | 耗時

#### Tab 3：Debate History（辯論歷史）
- 時間線圖：每次辯論的因子數、通過/淘汰比例
- 點擊展開該場辯論詳情（各 agent 輸出摘要）

#### Tab 4：Knowledge Base（知識庫統計）
- 卡片網格：12 類 vault 目錄，每類檔案數
- 來源：掃描 `/home/anson/Documents/Obsidian Vault/量化交易/` 子目錄
- 最新論文數、已驗證因子數、淘汰因子數、辯論記錄數

### B3. 視覺規範

從 05-UI-DASHBOARD.md 提取 design tokens：
- `--bg-canvas: #0a0e14` / `--bg-surface: #11161e`
- `--text-primary: #e6edf3` / `--text-secondary: #9aa6b7`
- `--status-active: #4cc38a` / `--status-warning: #f5a524` / `--status-error: #e5484d`
- 字型：Geist, JetBrains Mono (tab 數字)

**驗證**：
- `python scripts/generate_dashboard.py` → `google-chrome dashboard.html` → 四個 tab 都有內容

---

## 執行順序

```
Phase 1: data_sync.py (基礎，先有資料)
    ↓
Phase 2: backtest.py + generate_report.py (需要 Phase 1 的資料)
    ↓
Phase 3: generate_dashboard.py (讀取 factor-lab 既有資料，獨立)
```

Phase 1 和 Phase 3 可並行（彼此無依賴）。Phase 2 依賴 Phase 1。

## 檔案清單

| 檔案 | 類型 | 說明 |
|------|------|------|
| `scripts/data_sync.py` | 新建 | 資料同步管線 |
| `core/backtest.py` | 新建 | ADRS 回測引擎 |
| `scripts/generate_report.py` | 新建 | HTML 互動回測報表 |
| `scripts/generate_dashboard.py` | 新建 | Mission Control 儀表板 |
| `data/` | 新建目錄 | parquet 儲存目錄 |

## 風險

- CCXT 可能 rate-limit → 加 `enableRateLimit: True` 和 retry logic
- Binance API 可能改版 → 用既有 CryptoAdapter 的 API 呼叫方式
- Dashboard 嵌入大量 JSON 可能讓 HTML > 10MB → 只嵌入摘要，詳情 lazy-load
- 既有因子信號函數可能 API 不一致 → 實作前先檢查既有信號函數的簽名
