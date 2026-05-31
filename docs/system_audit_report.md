# Factor-Lab 系統審計報告

> 審計日期：2026-05-29  
> 審計範圍：`/home/anson/factor-lab/` 全部 49 個 .py 檔案（深度閱讀 12 個核心模組）  
> 審計方法：代碼閱讀 + 單元測試結構分析 + 架構一致性檢查

---

## 1. 架構總覽

```
factor-lab/
├── config.yaml              ← 全域設定（vault 路徑、市場、門檻）
├── cetus.py                 ← MVP CLI（new/dedup/gate0/bury/log）
├── index.db                 ← SQLite 持久化（辯論記錄、因子註冊、論文洞見）
├── conftest.py              ← pytest 設定
├── core/
│   ├── backtest.py          ← 回測引擎（AlphaPurify.FactorAnalyzer 包裝）
│   ├── gate.py              ← 機器檢查：Gate 0/2/3
│   ├── stages.py            ← 階段狀態機（0→1→2→3→4a→4b→5 + graveyard）
│   ├── kb.py                ← 知識庫管理（Obsidian vault 讀寫）
│   ├── memory.py            ← 辯論記憶（SQLite schema + 因子註冊 + 論文洞見）
│   ├── dedup.py             ← 因子去重（詞袋餘弦相似度）
│   ├── metrics.py           ← 因子評估指標（Rank-IC、IC-IR）
│   ├── exposures.py         ← 因子曝險與收益歸因（AlphaPurify.PureExposures）
│   ├── data.py              ← 資料獲取（CCXT Binance）
│   ├── signals/             ← 因子信號實現
│   │   ├── F1_Complexity_Gap_Regime.py       (258 行, ✓ 驗證)
│   │   └── F8_cubic_momentum_threshold_reversal.py (123 行, ✓ 驗證)
│   └── validators.py        ← 信號格式驗證
├── tests/
│   ├── test_gate.py         ← Gate 測試（10 cases, Boundary-aware）
│   ├── test_stages.py       ← 階段機測試（11 cases, tmp index.db 隔離）
│   └── test_backtest.py     ← 回測測試（已生成）
├── scripts/
│   ├── debate_flow.py       ← Phase 2 辯論流程協調器 (227 行)
│   ├── data_sync.py         ← CCXT → Parquet 資料同步
│   ├── generate_dashboard.py ← 4-tab HTML dashboard
│   └── generate_report.py   ← Plotly 報告生成
├── strategies/              ← 策略代碼產物（非 vault 內容）
├── logs/                    ← 執行記錄
├── candidates/              ← 候選因子 markdown
└── docs/                    ← 系統文件
    └── system_audit_report.md (本文件)
```

### 核心設計理念

factor-lab 是一個**多代理因子研究系統**，靈感來自學術論文 [Agentic AI for Factor Research (Paper #5)]。核心流程：

1. **Proposer** 從 vault 知識庫與論文洞見出發，提出新因子假說
2. **Empiricist** 用歷史行情數據量化測試因子預測力（Rank-IC、IC-IR、分組回報）
3. **Skeptic** 對候選因子進行五維批判（資料探勘、經濟直覺、前視偏誤、重複造輪子、成本流動性）
4. **Arbiter** 綜合所有證據做出 PASS / REJECT / REWORK 裁決

最大辯論輪數：3（config.yaml → research.max_debate_rounds）

---

## 2. 模組逐一評估

### 2.1 config.yaml — 評分：★★★★☆

**優點：**
- 集中管理所有門檻參數，單一事實來源（避免 magic number 散落代碼中）
- 測試檔案（test_gate.py）直接從 config 讀取門檻，做到 config-driven testing
- 中文路徑與 vault 結構完全映射

**問題：**
- **缺失 `kb.paper_paths` 的 schema 文檔**：`paths.paper` 定義為 "06-书籍论文"，但 kb.py 中可能還有其他隱含路徑，建議在 config 中顯式列出所有 kb 子路徑
- **`twstock.universe` 為空**：台灣股票市場未配置，但已有 market 定義，屬未完成功能（非 bug）

**建議：**
- 加入 `paths.` 下所有子路徑的完整列表（含 11-alpha提案、12-深度研究、13-策略墳场）
- 考慮為 `markets.default: crypto` 增加 fallback market 選項

---

### 2.2 core/backtest.py — 評分：★★★☆☆

**優點：**
- 完整包裝 AlphaPurify.FactorAnalyzer，介面設計合理
- 支援多符號並行回測（crypto universe: BTC/ETH/SOL/BNB）
- 包含 PBO（Probabilistic Backtest Overfitting）計算

**問題與風險：**

1. **PBO 是簡化近似（已知限制）**
   - 記憶中明確記錄：`PBO 為簡化近似`（非完整 Deflated Sharpe Ratio 或 CSCV）
   - 建議在 docstring 中明確標示 `PBO (簡化近似)` 與實際方法的差異

2. **外部依賴 AlphaPurify**
   - `alphapurify` 是第三方套件，若版本更新可能中斷 API
   - 建議在 requirements.txt 或 pyproject.toml 中鎖定版本

3. **錯誤處理覆蓋不足**
   - 僅有 try/except 捕獲 `Exception`，無針對性錯誤處理（如網路超時、API 限流）
   - Binance API 可能回傳 429/418/5xx，建議增加指數退避重試

4. **無策略參數敏感度分析**
   - 回測僅輸出 Sharpe/IC/PBO，未提供參數穩健性分析（如參數平面 heatmap）
   - 對論文依據的因子（如 F1 RMT window=60、n_components=10）未記錄選參理由

**建議：**
```python
# 建議加入重試裝飾器
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def fetch_ohlcv(...):
    ...
```

---

### 2.3 core/gate.py — 評分：★★★★★

**優點：**
- **測試覆蓋極佳**：10 個測試涵蓋所有邊界條件
  - `test_gate0_passes_at_exactly_min_score`（邊界值測試）
  - `test_gate0_duplicate_blocks_even_if_all_long`（去重阻擋）
  - `test_gate0_strips_template_placeholders`（模板清理）
  - `test_backtest_passes_at_boundary`（剛好通過門檻）
  - `test_gate3_checks_oos_and_wf_decay_unlike_gate2`（Gate 差異驗證）
- **純函數設計**：無副作用，所有狀態從參數傳入
- **Gate 分層合理**：
  - Gate 0：Soul Questions（語意理解，機器可檢查部分）
  - Gate 2：Mini-backtest（快速過濾，低門檻）
  - Gate 3：Full-backtest（嚴格條件，含 OOS、WF decay）
- **錯誤防禦**：`gate_backtest({}, "stage_3")` 缺鍵時以保守預設不通過，不拋例外

**無發現問題。**

---

### 2.4 core/stages.py — 評分：★★★★☆

**優點：**
- 狀態機設計嚴謹：合法轉換由 `TRANSITIONS` dict 明確定義
- **graveyard 為終態**：不可復活（終態保證）
- **rework 限額機制**：`config.rework_limit=1`，第二次 REWORK 強制擋下
- **測試覆蓋完整**：11 個測試，含非法跳級、終態鎖定、rework 限額、slug 隔離

**問題：**

1. **Stage 4a/4b 區分不明確**
   - 記憶中提到 `Stage 0→1→2→3→4a→4b→5`
   - 但 stages.py 中僅定義 `stage_3 → stage_4a → stage_4b → stage_5` 的路徑合法性
   - **4a 與 4b 的語意差異**、各自進入條件、以及 exit criteria 未在代碼中記錄
   - 建議在 docstring 中補充狀態機全圖

2. **rework 後回到哪個 stage？**
   - 記憶中 rework 從 stage_2 → rework，但未明確 rework 後回到 stage_0 還是 stage_1
   - stages.py 僅定義 `* → rework` 合法，無 `rework → *` 的轉換規則
   - **架構疑慮**：agent 如何從 rework 返回正常流程？

**建議：**
- 補充 `rework → stage_0` 的顯式轉換（回到原點重新提案）
- 在 config.yaml 或 stages.py 頂部加入 ASCII 狀態圖

---

### 2.5 core/memory.py — 評分：★★★★☆

**優點：**
- SQLite schema 設計合理：`debate_rounds`（辯論軌跡）、`factor_registry`（因子去重）、`paper_insights`（論文洞見）
- 因子指紋去重（SHA1 of name+formula）防止重複提案
- `generate_context_prompt()` 為 LLM agent 生成結構化上下文（含 active factors、淘汰因子、最近裁決、論文約束）
- `update_factor_evidence()` 只更新到更好的值（best-so-far tracking）

**問題：**

1. **`paper_insights` 表缺少全文索引**
   - `paper_id` 有索引，但 `insight`（文本欄位）無 FTS 索引
   - 當論文洞見數量增長時，`generate_context_prompt()` 的全文掃描會變慢
   - 建議加入 FTS5 虛擬表：`CREATE VIRTUAL TABLE paper_insights_fts USING fts5(insight, content=paper_insights)`

2. **`factor_registry.fingerprint` 碰撞風險**
   - SHA1 截斷至 16 hex chars = 64 bits → 約 2^32 後開始有碰撞風險
   - 對因子庫規模（預計 < 10,000）來說足夠，但若未來擴展應考慮完整 SHA256

3. **缺少資料遷移機制**
   - 若 schema 變更，無 alembic 或手動 migration script
   - 建議加入 `memory.migrate()` 或使用 `PRAGMA user_version`

---

### 2.6 core/exposures.py — 評分：★★★☆☆

**優點：**
- 封裝 AlphaPurify.PureExposures，介面簡潔
- `factor_correlation_matrix()` 自實現 Pearson 相關（無依賴 numpy.corrcoef）
- 返回結構化 dict（`correlations` + `avg_abs_corr`）

**問題：**

1. **Pearson correlation 算法效率問題**
   - 每個因子對都重新 drop_nulls + to_list，對 N 個因子產生 O(N²) 次 DataFrame 掃描
   - 對 20 個因子 × 500 天資料，性能尚可；若擴展至 100 因子 × 5000 天可能成為瓶頸
   - **建議**：一次性計算相關矩陣（`df[factor_cols].to_pandas().corr()`），或使用 Polars 內建 corr

2. **依賴 `statistics` 模組而非 numpy**
   - `st.fmean` 與 `numpy.mean` 行為一致，但混用兩者增加維護成本
   - 函數已在前面 `import numpy as np`，卻改用 `statistics` — 一致性不佳

3. **`analyze_exposures` 返回過於簡單**
   - 僅返回 `{"status": "ok", "message": "..."}` 或 `{"status": "error", ...}`
   - 未返回 PureExposures 的分析結果（因子貢獻百分比、殘差 alpha 等）
   - Arbiter 無法從返回值中獲取足夠資訊做決策

**建議：**
```python
# 建議返回更豐富的結構
return {
    "status": "ok",
    "factor_name": factor_name,
    "systematic_contribution": {...},  # 來自 ex.results
    "residual_alpha": ...,
    "independence_score": ...,
}
```

---

### 2.7 core/dedup.py — 評分：★★★☆☆

**優點：**
- 輕量級實現（詞袋 + 餘弦相似度），無需 embedding 模型或 pgvector
- 比對 graveyard + active factors，防止重複提案

**問題：**

1. **詞袋方法對語意變化不敏感**
   - `"momentum_12_1"` vs `"momentum_1_12"` 詞袋完全相同（無法區分）
   - `"volatility adjusted momentum"` vs `"momentum adjusted volatility"` 相似度 = 1.0
   - 對於因子名稱（短語），建議加入字符 n-gram（如 3-gram）作為補充

2. **餘弦閾值為固定值**
   - `duplicate_cosine: 0.85`、`similar_cosine: 0.65` 是全域設定
   - 不同因子類別（momentum vs volatility）可能有不同的有效閾值
   - 但當前規模下，固定閾值足夠 — **不是優先修復項**

3. **無語料庫正規化**
   - 未做 stemming（如 `adjusted` → `adjust`）、未過濾停用詞
   - 中文因子名稱（如 `「複雜度間隙相位」`）無法處理（jieba 分詞）

---

### 2.8 core/signals/ — 評分：★★★★☆

已審查兩個已驗證信號：

**F1_Complexity_Gap_Regime.py (258 行)**
- **優點**：
  - 完整的文獻引用（Laloux 1999, Plerou 2002）
  - 清晰的前視偏誤防範文檔（僅使用 t 及之前資料）
  - 自實現 expanding-window z-score（非 sklearn StandardScaler 的 look-ahead）
  - 相位分類有經濟直覺（disordered → 均值回歸, ordered → 趨勢）
  - 數值穩定性處理（clip eigenvalues, shrinkage, fill_diagonal）
- **問題**：
  - `_safe_log_returns` 中的缺失值填充用 Python loop 逐元素處理，對長序列效率低（建議向量化）
  - 使用 `numpy.linalg.eigh`（O(N³)），n_components=10 時無礙，但標記了效能上限
  - shrinkage intensity 公式 `min(0.3, n_components / (window * 2))` 是啟發式，未引用 Ledoit-Wolf 原始公式

**F8_cubic_momentum_threshold_reversal.py (123 行)**
- **優點**：
  - 三次多項式轉換（CMI）設計新穎，非平凡因子
  - 根從滾動分位數動態計算（自適應）
  - 前視偏誤分析文檔清晰
- **問題**：
  - 使用 pandas 而非 polars（與 backtest.py 的 polars 不一致）
  - `a/b/c` 使用 rolling(252).quantile()，對日線合理；但若用於小時線，252 天的窗口過長

---

### 2.9 測試基礎設施 — 評分：★★★★☆

**優點：**
- `conftest.py` 確保 `core.*` import 路徑
- `test_stages.py` 使用 `monkeypatch` 隔離 SQLite（tmp_path），測試互不污染
- `test_gate.py` 從 config 讀取閾值（boundary-aware testing）
- 測試命名清晰：`test_gate0_fails_below_min_score`、`test_graveyard_is_terminal`

**缺失：**
- 無 `test_backtest.py` 的內容驗證（檔案存在但未深度審查）
- 無 integration test（端到端：新因子從提案到裁決的完整流程）
- 無信號函數的單元測試（F1、F8 的 compute() 函數無測試保護）

---

## 3. 跨模組一致性問題

| 問題 | 嚴重性 | 涉及模組 |
|------|--------|---------|
| polars vs pandas 混用 | 中 | backtest.py(polars) vs signals/(pandas) |
| 錯誤處理策略不一致 | 中 | backtest.py(裸 Exception) vs exposures.py(結構化 error dict) |
| AlphaPurify 依賴無版本鎖定 | 高 | backtest.py, exposures.py |
| rework → 返回路徑未定義 | 高 | stages.py, debate_flow.py |
| 無 CI/CD pipeline 設定 | 低 | 全域 |
| 無 requirements.txt / pyproject.toml | 高 | 全域 |

---

## 4. 風險矩陣

| 風險 | 衝擊 | 可能性 | 等級 |
|------|------|--------|------|
| AlphaPurify API 變更中斷回測 | 高 (全部回測停擺) | 中 | 🔴 高 |
| rework 後 agent 無法返回流程 | 高 (辯論卡死) | 中 | 🔴 高 |
| PBO 簡化近似誤導裁決 | 中 (false positive) | 中 | 🟡 中 |
| 因子重複提案（dedup 漏檢） | 低 (可人工發現) | 低 | 🟢 低 |
| polars/pandas 轉換效能瓶頸 | 低 (當前資料量小) | 低 | 🟢 低 |

---

## 5. 建議修復優先級

### P0 — 立即修復（阻礙生產使用）

1. **加入 `requirements.txt` 或 `pyproject.toml`**
   - 鎖定 `alphapurify`、`polars`、`pandas`、`numpy`、`pytest` 版本
   - 新增 `tenacity`（用於 API 重試）

2. **定義 rework 返回路徑**
   - 在 stages.py 加入 `rework → stage_0` 轉換
   - 在 debate_flow.py 中處理 REWORK 裁決後的重新提案流程

### P1 — 短期修復（提升穩健性）

3. **exposures.py 返回完整分析結果**（非僅 status/message）
4. **backtest.py 加入 API 重試機制**（指數退避 + max 3 attempts）
5. **PBO 簡化近似加註 docstring**（避免誤解為完整 CSCV）
6. **統一 polars/pandas**：信號模組改用 polars 或加入 DataFrame 轉換層

### P2 — 中期改善（品質提升）

7. **加入 integration test**（端到端提案→裁決）
8. **F1 信號的缺失值填補向量化**（替換 Python loop）
9. **加入 FTS5 全文索引**（paper_insights）
10. **加入 schema migration 機制**（PRAGMA user_version）

---

## 6. 總體評價

**整體成熟度：7.0/10**

factor-lab 的架構設計合理，核心的 Gate→Stage→Memory 三層次分明，測試文化良好（test_gate.py 的 boundary-aware testing 值得稱讚）。主要風險來自外部依賴（AlphaPurify）的版本管理缺失，以及 rework 流程的未完成部分。信號實現（F1、F8）品質高且前視偏誤防範到位。

**最大資產**：memory.py 的辯論記憶與因子去重機制、gate.py 的分層檢查、test_gate.py 的邊界測試

**最大負債**：無依賴管理、rework 流程缺口、信號模組與回測引擎的 DataFrame 庫不一致

---

*審計完成。建議第一步先修復 P0 項目（加入 requirements.txt + 定義 rework 路徑），預計工作量 1-2 小時。*
