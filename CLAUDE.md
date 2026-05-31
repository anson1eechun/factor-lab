# Factor-Lab — 多代理因子研究系統（團隊規則）

本專案是「量化因子知識庫 + 多代理辯論」系統。知識庫 = Obsidian Vault
（`/home/anson/Documents/Obsidian Vault/量化交易`），權威儲存是 Markdown 筆記，
`index.db` 只是去重/索引快取。

## 兩條主流程

### `/run-ingest` — 文獻來源採集（上游補料）
依序：**追蹤者 → 抓取者 → 精讀者 → 歸檔者**
1. 跑 `python -m ingestion.watcher`（追蹤+抓取+去重，產生「待精讀」筆記）。
2. 對每篇「待精讀」筆記，喚起 **extractor** agent 精讀，填入：因子/假設/公式/報告績效/對知識庫的啟示。
3. 喚起 **archivist** 分類打標、評可信度、連結到既有因子或標記「待提案線索」。

### `/run-research` — 因子辯論會（每日）
依序，最多 `max_debate_rounds`（見 config.yaml）回合：
**proposer → builder → skeptic ⇄ (builder/proposer 修正) → empiricist → arbiter → librarian**
- proposer 開工前**先讀**知識庫既有因子 + 最近新增的文獻摘要與「待提案線索」。
- empiricist 用 `core/metrics.py`（Rank-IC / IC-IR）量化證據；arbiter 以證據為主裁決。
- arbiter 裁 `revise` 則退回 builder/proposer 進入下一回合；`validated`/`deprecated` 則交 librarian 入庫。

## 鐵律
- **證據 > 口才**：arbiter 主要依 empiricist 的量化結果，不被最會講話的代理左右。
- **杜絕前視偏誤**：因子在時間 t 只能用 ≤ t 的資料；IC 對齊的未來報酬必在 t 之後。
- **去重強制**：入庫前 librarian 必須比對既有因子相關性。
- **全透明**：每回合的輸入/輸出/理由寫進對應筆記的 `debate_log`。
- **合法採集**：只走官方 API/RSS、尊重 ToS、不繞付費牆。
- **代理檔名**：`.claude/agents/*.md` 檔名須與此處引用一致。

## 程式進入點
- 採集：`python -m ingestion.watcher [--dry-run]`
- 指標：`core/metrics.py`（rank_ic, ic_series_stats, forward_returns）
- 行情：`core/adapters/crypto.py`（CryptoAdapter，無 ccxt 時走 Binance REST）
