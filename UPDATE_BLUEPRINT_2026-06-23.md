# Factor-Lab 更新藍圖（2026-06-23）

> 來源：對齊 Balaena Quant YouTube《用 AI 做量化，到底能有多簡單？》(2026-06-23, U60eTIFTJ8o) 所展示的 **Nyrobrain** 能力。
> 定位決策：**factor-lab = 個人研究室**（產出餵給 Nyrobrain/Balaena，但本身不碰下單/OMS）。→ 範圍鎖定 Phase 0–4，**Phase 5（部署）不做**。
> 交付形態：本文件為規劃藍圖；對應任務清單已建立於 harness task list。

---

## 1. 影片願景摘要（Nyrobrain 三柱）

1. **知識庫** — 交織網路圖（青=知識點、紅=做過的 alpha research、藍=學過的 concept），「用越久越聰明」。
2. **自然語言 → 5 分鐘回測報告** — 貼推特 / 丟 factor endpoint+description → 生 **alpha story**（對手方、structural edge、為何持續）→ **依資料結構自動選 signal model** → 回測 → **plateau 優化** → **rolling walk-forward** → 誠實報告（Sharpe/Sortino/equity/heatmap/folds，每根 1/-1/0 不黑箱）。
3. **部署** — paper → 實盤（OMS + 配比）。【本研究室範圍外】

哲學：code 已扁平化，勝負在 **品味/認知/思路**；「問對問題」比答案重要；alpha 要貼底層邏輯（零和、誰虧錢）；數據說話、不杜撰（呼應既有記憶 [[no-fake-data-no-naming]]）。

影片案例都對得上 factor-lab 現有資料：Coinbase Premium Gap、exchange netflow、Spot Money Flow Index、ETH open interest/market cap。

---

## 2. 現況對照（誠實 gap，已標註既有資產，避免重造）

| 影片能力 | factor-lab 今天 | 缺口 |
|---|---|---|
| Alpha story（對手方/為何持續） | ✅ Soul Questions 6 題 + `gate0_machine`（`core/gate.py`）已強制 | 只在重量級 debate 跑，無輕量入口 |
| ADRS 穩健性 | ✅ `core/backtest.py`：PBO / walk-forward / purged-CV / sensitivity | WF 是單次 67/33；**無 rolling/concatenated-OOS 的 CV Sharpe** |
| 多年鏈上資料 | ✅ `data/onchain/` 13 條 ~3.5 年日線（Coinbase Premium Gap、netflow、taker ratio、MVRV…，~1283 點/條） | 各 signal 各自 `_load()`，**無統一 adapter / data dictionary**；缺 MFI、OI 長歷史、options |
| 「越用越聰明」 | ✅ `core/memory.py`（paper_insights + constraints 自動注入）、graveyard、`factor_registry` 指紋去重 | index.db 關聯式，**無 typed 圖譜/視覺化**；回饋迴路只到去重 |
| 報告透明（每根 position） | ✅ signal 已回傳 position∈[-1,1]；`scripts/generate_report.py` 4-row Plotly | 未與 plateau/folds 輸出綁定 |
| **依資料結構自動選 signal model** | ❌ 每個 signal 硬寫 `z-score + tanh` 一種 | **影片頭號賣點，完全缺** |
| **plateau 優化（綠色大片）** | ❌ 只有 1-參數 ±20% `sensitivity_check` | 無 grid search / plateau_score / heatmap |
| 一鍵 NL→報告 | ⚠️ `debate_flow.py` 多代理、手動 terminal spawn | 無單一快速入口 |
| 回測棧一致性 | ⚠️ `alphapurify` **當前環境 import 不到** → `backtest.py`/`preprocessing.py` 包裝層那條路是斷的 | 真正幹活的是 `onchain_eval.py` 這類 pandas 腳本（契約：date-indexed position∈[-1,1]，harness lag 1 日無前視）→ **兩套棧分裂** |
| 部署/OMS/配比 | state machine 有 Stage 4/5 但標「MVP 後」 | 研究室範圍外，交給 Nyrobrain/Balaena |

**維護債（順手處理）**
- `ingestion/watcher.py` 壞了：CLAUDE.md 第 61–69 行重複「watcher DNS 解析失敗」log。
- `README.md` 已過時（仍寫 F1–F9、只有兩個 parquet；實際已長出 equity/A-share/intraday/SMC）。

---

## 3. 更新藍圖（Phase 0–4，每階段有可驗收標準）

### Phase 0 — 修地基
- 13 條 onchain JSON 收進一個 `OnchainAdapter` + `data_dictionary.yaml`（名稱/單位/符號性/敘事/歷史長度）。
- 解決回測棧分裂：既然 `alphapurify` 沒裝、真正在用的是 pandas position-series 契約，**選定 `onchain_eval.py` 那套為唯一 harness**，文件化 signal 契約（date-indexed position∈[-1,1]，lag≥1，無前視）。
- 修或停掉 watcher；同步 README / CLAUDE.md。
- **驗收**：`from core.data import load("coinbase_premium_gap")` 可跑；一份 signal 契約文件；CLAUDE.md 不再長 DNS 垃圾 log。

### Phase 1 — Signal-Model 庫（補頭號缺口）
- 小 registry：~5 個 model，每個純函數 `series → position[-1,1]`，**比照現有 signal 風格、不造框架**：
  - z-score 均值回歸、spike/breakout、mean-drift trend、percentile-rank、sign/flow。
- `data_profile(series)` 給序列打標籤（continuous / signed / skewed / log-normal / spiky）→ 建議 model。
- **驗收**：對 13 條任一序列 `auto_signal(series)` 能選 model 出 position；重現影片的 MFI 均值回歸與 Coinbase Premium 案例。

### Phase 2 — 穩健性引擎（plateau + rolling WF）
- `grid_optimize()`：回傳 best params + **plateau_score**（grid 內落在最佳 X% 的比例＝那片綠）+ heatmap data。
- `rolling_walk_forward()`：錨定/滾動、concatenated OOS folds → **CV Sharpe + 正向 fold 數**；擴充而非取代 `core/backtest.py` 既有函數。
- **驗收**：輸出欄位對得上影片報告（CV Sharpe、MDD、positive folds、plateau heatmap）。

### Phase 3 — 一鍵研究入口（影片的「5 分鐘」體驗）
- 單一 `scripts/quick_research.py --factor <name>`：吃 factor+description → 生 alpha story（複用 Soul Questions）→ `auto_signal` → `grid_optimize` → `rolling_WF` → 用 `generate_report.py` 出誠實報告。做成**確定性 harness**，讓 debate agent 呼叫。
- **驗收**：一行指令，5 分鐘內出含 equity/heatmap/folds/per-bar position 的完整報告。

### Phase 4 — KB 經驗圖譜
- 在 index.db + graveyard + `core/memory.py` 上建 typed graph（node: concept/factor/alpha-research/paper；edge: derived-from / duplicate-of / killed-by / cites），掛進 Balaena 控制台（localhost:8900）當影片那張網路圖。
- 閉迴路：把過往 verdict（graveyard 教訓、evidence）餵回 Proposer 先驗。
- **驗收**：圖能 render；Proposer 每次提案至少引用 1 條過往結果/墳場教訓。

### Phase 5 — 部署【不做】
- paper/live（Stage 4/5）交給 Nyrobrain/Balaena 的 OMS；本研究室不碰下單。

---

## 4. 建議推進順序
**Phase 0 → 1 → 2** 為近期主線：signal-model 庫 + plateau/rolling-WF 是影片最想賣、factor-lab 最缺的兩塊，且能立刻讓現有 13 條鏈上資料產出 demo 級結果。Phase 3 把前三者縫成一鍵入口，Phase 4 補知識庫視覺化與回饋迴路。

## 5. 已知缺資料（待補，非阻塞）
Spot Money Flow Index (MFI)、多年 open interest 歷史、options（影片用的是 enterprise 級分鐘資料；研究室層級先用日線替代即可起步）。
