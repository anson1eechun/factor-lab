---
name: factor-lab
description: Factor-Lab 多代理因子研究系統 — 兩條主流程：文獻採集歸檔、因子辯論研究。源自 /home/anson/factor-lab/，已從 Claude Code 適配到 Hermes。
---

# Factor-Lab — 多代理因子研究系統

專案根目錄：`/home/anson/factor-lab/`
知識庫 vault：`/home/anson/Documents/Obsidian Vault/量化交易`

本 skill 同時是**編排者（Orchestrator）入口**：載入它的主 agent 就是編排者，依序調度
`factor-lab-<role>` 子代理跑完整管線。Arbiter 不委派，由主 agent 親自裁決。

## Hermes 啟動與入口

在 repo root 啟動時，Hermes 會自動讀取 `CLAUDE.md` 作為專案規則：

```bash
cd /home/anson/factor-lab
hermes -s factor-lab
```

進入 Hermes 後的命令路由：

| 命令 | 動作 |
| --- | --- |
| `/factor-lab ingest [--limit N]` | 跑 Pipeline A（文獻採集 → extractor → archivist） |
| `/factor-lab research` | 跑 Pipeline B（因子辯論），詳細 CLI 序列見 [references/orchestration-runbook.md](references/orchestration-runbook.md) |
| `/factor-lab new-idea <idea>` | 跑 Cetus Stage 0 / Gate 0（conor/daemon/helen） |

One-shot / cron 用 helper 產生固定工作流 prompt：

```bash
cd /home/anson/factor-lab
python3 scripts/hermes_factor_lab.py doctor              # 檢查路徑、skill 安裝、待辦量
python3 scripts/hermes_factor_lab.py pending --limit 20  # 列出待精讀筆記
hermes -s factor-lab -z "$(python3 scripts/hermes_factor_lab.py prompt ingest --limit 5)"
hermes -s factor-lab -z "$(python3 scripts/hermes_factor_lab.py prompt research)"
```

角色 skills（單一真相源在 repo `hermes/skills/`，由 `scripts/install_hermes_skills.py`
同步到 `~/.hermes/skills/` 與 deepseek profile）：
`factor-lab-extractor`, `factor-lab-archivist`, `factor-lab-proposer`,
`factor-lab-builder`, `factor-lab-skeptic`, `factor-lab-empiricist`,
`factor-lab-arbiter`, `factor-lab-librarian`。委派時各代理只擁有自己的檔案，
不得回退其他代理的編輯。完整 runbook 見 `docs/hermes-agent-workflow.md`。

## Cetus Stage 0 / Gate 0（new-idea）

`/factor-lab new-idea <idea>` 把一個 alpha 想法走完 Stage 0：

1. `python3 cetus.py new "<idea>"` 建 alpha-idea 筆記，從輸出取 slug。
2. `python3 cetus.py gate0 <slug>` 跑機器把關（dedup + 結構檢查）。
3. 用 `.claude/agents/daemon.md`（dedup）、`.claude/agents/helen.md`（Soul Questions 語意判斷）、
   `.claude/agents/conor.md`（彙整）完成 Gate 0 審查。
4. 回報 alpha note 路徑、soul_score、裁決（pass / rework / graveyard）與理由。

## 兩條主流程

### Pipeline A：文獻採集 (`factor-lab-ingest`)
依序：Watcher（自動）→ Extractor（LLM）→ Archivist（LLM）

1. **Watcher**：`python3 -m ingestion.watcher [--dry-run]`
   - 依 `sources.yaml` 輪詢 arXiv API + RSS feeds
   - 去重（SHA1 of URL → `index.db`）
   - 寫入待精讀筆記到 vault（frontmatter + 摘要 + ⏳ 待精讀標記）
   - 更新 MOC

2. **Extractor**：讀取待精讀筆記 → 爬原文 → 填入結構化因子資訊
   - 核心因子/訊號、計算定義、報告績效、限制與適用條件、對本知識庫的啟示
   - 移除 `待精讀` tag，加上內容類別標籤（動能/籌碼/情緒/鏈上/風控）

3. **Archivist**：分類確認 → 可信度標註（high/medium/low）→ 連結既有因子 → 標記待提案線索

### Pipeline B：因子辯論 (`factor-lab-research`)
依序：Proposer → Builder → Skeptic ⇄ Empiricist → Arbiter → Librarian
最多 `max_debate_rounds` 回合（config.yaml，預設 3）

1. **Proposer**：讀 `10-因子库` 既有因子 + 文獻的「待提案因子線索」→ 提 1~3 個新因子假設
2. **Builder**：精確數學定義 → 可執行 Python 函數（`core/signals/F<id>_<name>.py`）→ smoke test
3. **Skeptic**：逐條質疑（資料探勘/經濟直覺/前視偏誤/重複造輪子/成本流動性）
4. **Empiricist**：行情 → Rank-IC / IC-IR / 分組 / 相關性（`core/metrics.py`）
5. **Arbiter**：綜合裁決 → `validated` / `revise` / `deprecated`
6. **Librarian**：歸位/去重/建連結/更新索引/MOC

## 鐵律
- **證據 > 口才**：Arbiter 以 Empiricist 量化結果為主
- **杜絕前視偏誤**：因子時間 t 只用 ≤ t 資料
- **去重強制**：Librarian 入庫前比對既有因子相關性
- **全透明**：debate_log 記錄每回合輸入/輸出/理由
- **合法採集**：只走官方 API/RSS、尊重 ToS

## 設定檔關鍵參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `ic_horizon_days` | 5 | IC 用未來幾日報酬 |
| `ic_min_abs` | 0.02 | 最低 \|Rank-IC\| |
| `ic_ir_min` | 0.3 | 最低 IC-IR |
| `max_debate_rounds` | 3 | 辯論回合上限 |

## 進入點

```bash
# 採集
cd /home/anson/factor-lab && python3 -m ingestion.watcher [--dry-run]

# Glassnode 圖表 + 視覺分析
cd /home/anson/factor-lab && python3 -m ingestion.glassnode_visual [--dry-run] [--limit N] [--force]

# 記憶模組
python3 -c "from core.memory import generate_context_prompt, get_active_factors, get_design_constraints; print(generate_context_prompt())"

# 論文啟示寫入
python3 -c "from core.memory import record_paper_insight; record_paper_insight(paper_id='...', paper_title='...', insight_type='research_direction', insight='...')"

# 指標
python3 -c "from core.metrics import rank_ic, ic_series_stats, forward_returns; ..."

# 行情
python3 -c "from core.adapters.crypto import CryptoAdapter; ..."
```

## AlphaPurify 整合（因子清洗 + 回測引擎）

AlphaPurify (`alphapurify` PyPI) 提供高速 Polars 因子分析。三個封裝模組：

| 模組 | 路徑 | 功能 |
|------|------|------|
| `core/preprocessing.py` | factor-lab | 40+ 清洗方法：`preprocess_factor(df, factor_col, winsorize=, neutralize=, standardize=)` |
| `core/backtest.py` | factor-lab | IC 分析 + 多空分層回測：`FactorBacktest(df, factor_name=).run()` |
| `core/exposures.py` | factor-lab | 純因子曝險歸因 + 相關矩陣：`analyze_exposures(df, factor_name, exposure_cols)` |

安裝：`pip install --break-system-packages alphapurify`（系統 Python 受 PEP 668 保護）

### 進入點（AlphaPurify）

```bash
# 因子清洗
python3 -c "from core.preprocessing import preprocess_factor; ..."

# 回測（需 Polars DataFrame 含 datetime/symbol/close/{factor} 欄位）
python3 -c "from core.backtest import FactorBacktest; bt = FactorBacktest(df, factor_name='momentum_20').run(); bt.run_full_report()"

# 曝險分析
python3 -c "from core.exposures import analyze_exposures, factor_correlation_matrix; ..."
```

## 記憶模組（`core/memory.py`）

記錄辯論軌跡 + 因子註冊 + 論文啟示，為 Phase 2 辯論提供持久化上下文。資料存於既有的 `index.db`。

### 核心表

| 表 | 用途 |
|---|------|
| `debate_rounds` | 每回合 agent 輸出（假說、評估、裁決） |
| `factor_registry` | 因子去重註冊（fingerprint = SHA1 of name+formula） |
| `paper_insights` | 論文驅動的設計約束/架構參考/研究方向 |

### 關鍵 API

```python
from core.memory import (
    # 辯論記錄
    log_round,                              # 記錄一回合 → row id
    get_session_history(session_id),        # 完整軌跡
    get_recent_decisions(limit),            # 最近 N 個裁決
    generate_context_prompt(),              # 生成 LLM prompt（含 active/deprecated/recent + paper design_constraints）

    # 因子管理
    register_factor(name=, formula=, category=),  # 註冊（去重）
    update_factor_evidence(name=, sharpe=, ic_mean=, status=),  # 更新最佳績效
    get_active_factors(category=),           # 有效因子
    get_deprecated_factors(),                # 已淘汰因子
    factor_fingerprint_exists(name=),        # 去重檢查

    # 論文啟示（Phase 2 自動注入辯論 prompt）
    record_paper_insight(paper_id=, paper_title=, insight_type=, insight=),
    get_design_constraints(),                # design_constraint 類型
    get_research_directions(),               # research_direction 類型
)
```

`generate_context_prompt()` 自動從 `paper_insights` 注入 design_constraint 至 prompt。已寫入 6 條論文啟示（3 design_constraint + 1 architecture_reference + 2 research_direction）。

## 已歸檔關鍵論文（06-书籍论文/）

截至 2026-05-25，51 篇論文（經清理重複與不相關後）：26 篇已精讀（完整公式/數據/引用），25 篇 watcher 原始匯入待後續處理。核心論文分三級：

### 架構級（直接影響 factor-lab 設計）
| 論文 | ID | Sharpe | 核心啟示 |
|------|-----|--------|---------|
| Agentic Factor Discovery | 2604.26747 | 1.55 | append-only trace + 假說/配方分離 |
| AgenticAITA Multi-Agent | 2605.12532 | — | 三層管線 + Agentic Friction + AZTE trigger |
| PRISM-VQ Factors | 2605.13407 | 1.57 | VQ 瓶頸正則化 + 先驗/學習因子混合 |
| Cross-Stock LLM Network | 2604.19476 | 0.82 | Retrieve-then-Reason 邊過濾 |

### 方法論級（影響回測評估標準）
| 論文 | ID | Sharpe | 核心啟示 |
|------|-----|--------|---------|
| Strategy Backtests Eval | 2604.18821 | — | peer benchmark + regime timing bias |
| GNN Volatility→Portfolios | 2605.19278 | — | MSE ≠ RankIC ≠ Sharpe（三目標不可互換） |
| Regime Classifier (MNQ) | 2605.11423 | — | 波動率+成交量+缺口 + walk-forward OOS |
| Beyond De Prado HRP | 2604.23833 | — | HRP → 一般 mean-variance 層次方法 |

### 技術級（可借鑒方法）
| 論文 | ID | Sharpe | 核心啟示 |
|------|-----|--------|---------|
| VP-MACD | 2604.26063 | — | 波動率+成交量調整價格 + λ sensitivity |
| VGRSI (Visibility Graph) | 2605.01300 | 2.55 | 幾何圖論指標（需審視槓桿/過擬合） |
| Price as Focal Point | 2604.24147 | — | SCI 指標區分持久訊號 vs 暫時壓力 |

論文啟示已寫入 `core/memory.py` 的 `paper_insights` 表，`generate_context_prompt()` 自動注入 design_constraints 至辯論 prompt。

## 論文圖表分析：LaTeX 原始碼提取（vision 工具不可用時的替代方案）

當 vision 工具無法分析論文圖表（如 DeepSeek provider 不支援 image input、Gemini API 未設定），**優先使用 LaTeX 原始碼提取**，比視覺分析更準確：

### 適用條件
- 論文在 arXiv 上且有原始碼（點擊 "Download source" 或 `arXiv e-print` 頁面的 "Other formats"）
- 需要精確數字（Sharpe、t-statistic、回歸係數、表格數據）— LaTeX 原始碼中的表格是精確值，不是圖表猜測

### 操作步驟
```bash
# 1. 下載原始碼
PAPER_ID="2412.12350"
wget "https://arxiv.org/e-print/${PAPER_ID}" -O /tmp/${PAPER_ID}.tar.gz

# 2. 解壓並找關鍵檔案
mkdir -p /tmp/${PAPER_ID}_src && tar xzf /tmp/${PAPER_ID}.tar.gz -C /tmp/${PAPER_ID}_src
find /tmp/${PAPER_ID}_src -name "*.tex" | head -20

# 3. 讀取表格章節（通常命名為 Results.tex、tables/、Data.tex 等）
# 搜尋關鍵詞定位表格
grep -n '\\begin{table}\|Sharpe\|\\begin{tabular}' /tmp/${PAPER_ID}_src/*.tex
```

### 提取表格數據範例
LaTeX 表格原始碼：
```latex
\begin{tabular}{lccc}
\toprule
 & Sharpe & MaxDD & Calmar \\
\midrule
Risk Parity & 0.81 & -16.87\% & 0.48 \\
Equal Weight & 0.63 & -22.31\% & 0.28 \\
\bottomrule
\end{tabular}
```
→ 直接取得精確數字，不需視覺猜測。

### 何時仍用 vision
- 論文無原始碼（僅 PDF）
- 複雜圖表（熱力圖、網路圖、t-SNE 投影）— 無對應表格數據
- 此時才使用 `vision_analyze` 或 Gemini CLI（見 Glassnode Visual 設定）

## Hermes 適配策略

原 Claude Code 代理（`.claude/agents/*.md`）對應 Hermes 實現方式：

### Phase 1（✅ 已完成）：採集自動化
- Watcher (cron `factor-lab-watch` e7705b60ff4c) — 每日 08:00、20:00
  - arXiv (q-fin) + RSS (Robot Wealth + Glassnode Research)
  - 腳本：`scripts/factor-lab-watch.sh`
- Glassnode Visual (cron `glassnode-visual` 46506d44ab7e) — 每日 09:00、21:00
  - 掃描 Glassnode 待精讀筆記 → 下載圖表 → Gemini 2.5 Pro vision 分析 → 更新筆記
  - 腳本：`scripts/glassnode-visual.sh`，執行 `python3 -m ingestion.glassnode_visual`
  - **Gemini CLI 環境要求**：
    - `HOME=/home/anson`（否則 OAuth 認證失敗）
    - 圖檔必須放在 `/home/anson/factor-lab/.gemini_tmp/`（Gemini 工作區限制，其他路徑會報「無法訪問指定的檔案路徑，因为它位於我的工作區之外」）
    - 模型：`gemini-2.5-pro`（非 gemini-3.1-pro；gemini CLI 0.41.1 已配置 OAuth）
  - **Glassnode 圖表來源**：文章 HTML 中 `<figure><img src="https://insights.glassnode.com/cdn-cgi/image/...">` 的 CDN 圖片，可直接 curl 下載
  - **Prompt 要求**：必須在 prompt 中加入「用繁體中文回答，不要用英文」，否則 Gemini 預設用英文回覆
  - **筆記更新邏輯**：先用 regex 移除舊 `## 📊 圖表與分析` 段落（`re.compile(r'\n## 📊 圖表與分析.*$', re.DOTALL)`），再寫入新內容，避免重複累積
  - **Caption 提取**：部分文章有 `<figcaption>` 標籤，部分無（設為空字串即可）
  - `--force` flag：強制重新處理已分析過的文章
- Extractor + Archivist → Hermes 直接執行（或 delegate_task 委派）
  - 觸發條件：cron job 跑完 watcher 後發現新內容時自動進行

### Phase 2（規劃中，基礎設施已就緒）：辯論流程
- 每個代理 → Hermes `delegate_task` subagent
- 回合控制 → 由主 agent 依序調度
- **記憶模組**（`core/memory.py`）已實作：辯論軌跡 + 因子註冊 + 論文啟示自動注入 prompt
- 優先用低成本模型（deepseek-v4）跑大部分代理，複雜推理（如 arbiter final call）可切 Claude

## 來源管理

`sources.yaml` 結構：
```yaml
arxiv:         # arXiv API 查詢（3 個查詢，覆蓋因子+ML+LLM）
  - query: "cat:q-fin.TR OR cat:q-fin.PM OR cat:q-fin.ST"
    keywords: ["factor", "momentum", "cross-section", "alpha", "signal", "crypto"]
  - query: "cat:q-fin.CP OR cat:q-fin.RM"
    keywords: ["machine learning", "deep learning", "neural network", "reinforcement learning", "portfolio", "volatility", "risk"]
  - query: "all:LLM AND all:finance OR all:transformer AND all:stock OR all:foundation model AND all:trading"
    keywords: ["LLM", "transformer", "foundation model", "agent", "sentiment"]
    max_results: 15
    priority: medium

rss:           # RSS/Atom feed（5 個，2 個已確認可用）
  - name: "Robot Wealth"
    feed: "https://robotwealth.com/feed/"
  - name: "Glassnode Research"
    feed: "https://insights.glassnode.com/rss/"
  - name: "Quantpedia"  # ✅ 可用
    feed: "https://quantpedia.com/feed/"
    author: "Quantpedia"
    priority: high
  - name: "AQR Research"  # ⚠️ XML 解析錯誤，需瀏覽器處理
    feed: "https://www.aqr.com/Insights/Research/Feed"
  - name: "Robeco Quant Investing"  # ⚠️ XML 格式錯誤
    feed: "https://www.robeco.com/en-int/insights/quantitative-investing/rss"
  - name: "Two Sigma Insights"  # ⚠️ HTTP 403 Forbidden
    feed: "https://www.twosigma.com/insights/feed/"

x:             # X/Twitter（需 X_BEARER_TOKEN 環境變數）
  - handle: "@lopezdeprado"
  - handle: "@CliffordAsness"
  - handle: "@quantpedia"
```

## Vault 目錄對應

| archive_as | vault 子目錄 |
|-----------|-------------|
| paper | 06-书籍论文 |
| author | 09-作者专题/<作者名> |
| factor | 10-因子库 |

## Vault 維護

### 品質審計
```bash
cd "/home/anson/Documents/Obsidian Vault/量化交易/06-书籍论文/"
echo "已精讀: $(grep -l 'status: 已精讀' *.md | wc -l)"
echo "已標註: $(grep -l 'status: 已標註' *.md | wc -l)"
echo "未標註: $(for f in *.md; do head -1 "$f" | grep -q '^---$' && ! grep -q '^status:' "$f" && echo "$f"; done | wc -l)"
```

### 重複清理
watcher 自動匯入的短檔名（如 `2501.12345_Paper_Title.md`）可能與後續手動改寫的長檔名版（如 `2026-05-01_Paper_Title.md`）重複。找出重複後刪除短檔名版：
```bash
for f in *.md; do grep -oP '\d{4}\.\d{4,5}' "$f" | head -1 | while read id; do echo "$id|$f"; done; done | sort -t'|' -k1
# 手動審查後 rm 短檔名版
```

### 不相關論文清理
定期檢查並刪除與量化交易無關的論文（圖像 tokenization、穿戴裝置、人口學、純 LLM benchmark 等）。刪除前先確認：
```bash
grep -l 'NOT_RELEVANT' *.md
```
