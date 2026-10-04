# Factor-Lab — 多代理量化因子研究引擎

Factor-Lab 是一個人用的 alpha 研究引擎：讓多個 LLM 代理扮演小型量化團隊（提案、實作、批判、實證、裁決、歸檔），對候選因子跑完整的辯論與回測流程。設計重點不是「找到會賺錢的因子」，而是**可靠地殺掉假的因子**：預註冊、search ledger 記錄每一次試驗、依家族試驗數做 Bonferroni 與 Deflated Sharpe 校正、獨立裁判。

本專案只做研究，不下單、不接 OMS。唯一在跑的策略是一條凍結規格的 forward paper trade。

> 系統藍圖：[Cetus 設計文件](https://github.com/anson1eechun/cetus-design)　·　控制台：[Balaena Mission Control](https://github.com/anson1eechun/balaena-quant)

## 目前狀態（2026-10）

- **search ledger**：`empirical_runs/search_ledger.jsonl` 共 172 列、54 個辯論 session。絕大多數候選以 REJECT、CLOSE 或家族封線收場，封線條文與解鎖前提都寫在 ledger 裡。
- **唯一進入 forward 的訊號**：未條件化的 Coinbase Premium（`strategies/coinbase_premium_base.yaml`，2026-06-29 凍結）。置換檢定 p=0.006，但 OOS holdout t=0.84 不顯著、成本超過 30bps 轉負，屬於「真但弱」。每天 08:10（台北）由 crontab 執行 `scripts/paper_trade.py run` 記一筆。
- **研究結論摘要**：13 條鏈上日線單因子只有 1 條通過穩健檢定，約等於運氣預期；等權組合全負；crypto 橫截面因子反覆出現「排序層 IC 顯著、扣成本後美元層不可變現」的模式（見 `empirical_runs/power_curve_20260924_report.md`）。
- **測試**：`tests/` 共 48 個測試（stages、gate、blueprint）。

## 架構

```
           文獻 / 鏈上資料 / 行情                    兩條驅動路線
  ┌───────────────┐  ┌──────────────┐     ┌────────────────────────────┐
  │ ingestion/    │  │ core/data.py │     │ Hermes Agent 技能群         │
  │ arXiv·RSS·    │  │ 13 條鏈上日線 │     │ hermes/skills/factor-lab-*  │
  │ Glassnode 圖  │  │ adapters/    │     ├────────────────────────────┤
  └──────┬────────┘  └──────┬───────┘     │ Claude Code 子代理          │
         ▼                  ▼             │ .claude/agents/*.md         │
  Obsidian vault ◄── core/kb.py ──► index.db (SQLite：文獻/因子/辯論/轉換)
                         │                └─────────────┬──────────────┘
                         ▼                              ▼
   Proposer → Builder → Stage 0 → 預註冊 → Empiricist pack → [Skeptic] → Arbiter → Librarian
                                   │             │                          │
                          replication_lock   labkit.py / backtest.py   ledger.py（家族 N、
                          （鎖靜默）          （PBO、DSR、WF、NW-t）     Bonferroni、DSR 門檻）
```

### 目錄

```
factor-lab/
├── config.yaml            # 路徑、gate 門檻、pipeline 參數
├── cetus.py               # 薄 CLI：建 idea、dedup、Gate 0 檢查、埋進 graveyard、看階段歷史
├── core/
│   ├── data.py            # 統一鏈上資料載入（load / meta / data_dictionary）
│   ├── signal_models.py   # 因子序列 → 部位 [-1,1]；5 個模型 + 依資料結構自動選模
│   ├── backtest.py        # evaluate_positions、grid + plateau、rolling walk-forward、DSR、PBO
│   ├── metrics.py         # Sharpe、Rank-IC、IC-IR 等
│   ├── gate.py / stages.py# Gate 機器檢查與階段狀態機（stage_0 → graveyard / rework 限一次）
│   ├── memory.py          # paper insights、design constraints、proposer priors 回饋
│   ├── dedup.py           # 詞袋餘弦去重（中英 bi-gram）
│   ├── kb.py / kb_graph.py# 知識庫存取與 typed 知識圖譜
│   ├── exposures.py       # AlphaPurify 曝險歸因
│   ├── adapters/          # Binance OHLCV 適配器（有 ccxt 用 ccxt，否則 REST）
│   └── signals/           # 35 個訊號模組：F 系列（價量）、FSIM_（辯論模擬產出）、FSMC_（市場結構）
├── scripts/
│   ├── empiricist_pack.py # 實證套餐：一次產出所有門檻數字
│   ├── labkit.py          # 共用統計與記帳（NW-t、非重疊 t、sha256 鎖）
│   ├── ledger.py          # search ledger 唯一讀寫入口（家族 N / Bonferroni / DSR）
│   ├── librarian.py       # 裁決後歸檔：寫 index.db、ledger status 列、因子筆記
│   ├── paper_trade.py     # forward paper trade（run / status）
│   ├── quick_research.py  # 一鍵：載入 → 選模 → plateau → WF → DSR/PBO → HTML 報告
│   ├── universe_sweep.py / regime_combo_sweep.py   # 全域與組合掃描
│   ├── onchain_eval.py    # 單資產時序 harness（lag ≥ 1、扣成本）
│   └── debate_flow.py     # Hermes 版辯論狀態機
├── empirical_runs/        # 每個 session 的預註冊、results.json、integrity、辯論報告、search_ledger.jsonl
├── strategies/            # 凍結規格（forward 的預先承諾證據）
├── paper_trades/          # forward 紀錄（jsonl）
├── graveyard/ validated/ deprecated/   # 依裁決歸位的因子筆記
├── hermes/skills/         # Hermes Agent 角色技能（orchestrator、proposer、skeptic…）
├── .claude/agents/        # Claude Code 子代理角色卡
├── ingestion/             # arXiv / RSS watcher、Glassnode 圖表視覺分析、Threads poller
├── docs/SIGNAL_CONTRACT.md# 訊號契約
└── tests/
```

## 辯論流程

| 階段 | 做什麼 | 輸出 |
|---|---|---|
| Proposer | 從 vault 與封線清單（`ledger.py closed`）提出假設，回答靈魂六問 | 候選筆記 |
| Builder | 只新增一個訊號檔，遵守契約（無前視、標準介面） | `core/signals/FSIM_*.py` |
| Stage 0 | 便宜的提早淘汰 | KILL_STAGE0 或放行 |
| 預註冊 | 主規格、方向、門檻在看到數字前寫死；`replication_lock` 記 sha256 | `*_prereg.md`、`*_replication_lock.json` |
| Empiricist | `empiricist_pack.py` 跑完整套餐；凍結前數字只落盤不列印 | `*_results.json` |
| Skeptic（選用） | 五維批判、控制變數診斷 | ledger `diag` 列 |
| Arbiter | 獨立子代理，只看摘要、門檻與家族 N | VALIDATE / REWORK / REJECT / CLOSE |
| Librarian | 歸位、寫 ledger、更新 index.db | 因子筆記、ledger `status` / `closure` 列 |

### 多重比較管控

每個被評估的假設都要經 `ledger.py` 進入 search ledger，沒登錄就算作弊。Arbiter 的門檻依同家族累積試驗數 N 調整：

```bash
uv run --with "numpy>=2" --with pandas python scripts/ledger.py n --family xs.lottery --t-years 5.5
uv run --with "numpy>=2" --with pandas python scripts/ledger.py closed
```

一個家族的試驗額度用完就封線，封線條文寫明封的範圍與解鎖前提。

### 訊號契約

單資產時序研究的訊號是一個無參數函數，回傳 date-indexed 的部位 Series（值域 [-1, 1]）。無前視由 harness 負責（`shift(lag)`），資料一律走 `core.data.load()`。詳見 [`docs/SIGNAL_CONTRACT.md`](docs/SIGNAL_CONTRACT.md)。

```python
from core.data import load
from core.signal_models import auto_signal, data_profile

prem = load("coinbase_premium_gap")
print(data_profile(prem))            # 依資料結構建議模型，附理由
pos = auto_signal(prem, direction=1) # 部位 Series ∈ [-1, 1]
```

## 使用方式

需要 Python 3.12 以上。重活一律用 `uv` 臨時帶套件，系統 python 不裝 numpy、pandas：

```bash
UV='uv run --with numpy>=2 --with pandas --with pyyaml --with scipy'

$UV python scripts/quick_research.py --factor coinbase_premium_gap   # 一鍵研究報告
$UV python scripts/paper_trade.py status                             # forward 淨值與 expectation 對照
$UV python cetus.py dedup "<假設描述>"                                # 與既有 / 已死想法比對
$UV --with pytest python -m pytest tests/                            # 測試
```

完整套件清單在 `requirements.txt`。

辯論本身由代理驅動：在 Hermes Agent 用 `factor-lab` 技能群，或在 Claude Code 用 [factor-lab-debate skill](https://github.com/anson1eechun/factor-lab-debate-skill)。

## Gate 門檻（`config.yaml`）

| Gate | 條件 |
|---|---|
| Gate 0 靈魂六問 | 每題 ≥ 100 字，至少 4/6 題通過；與既有或已死策略重複就淘汰 |
| Gate 2 Mini backtest | Sharpe ≥ 0、PBO ≤ 0.3、交易 ≥ 20、MaxDD ≤ 45% |
| Gate 3 Full backtest | Sharpe ≥ 0.5、OOS Sharpe ≥ 0.25、PBO ≤ 0.3、WF decay ≥ 0.3 |

辯論流程的實證門檻集中在 `scripts/empiricist_pack.py` 的 `GATES`。2026-09-24 起，crypto 橫截面改以排序層為正式判準，美元層降為揭露。

### 靈魂六問

1. 這個 alpha 為什麼現在存在？（結構性原因，不接受「別人還沒發現」）
2. 什麼會殺死它？
3. 對手方是誰？
4. 一句話描述機制
5. 資料來源、頻率、欄位、歷史長度
6. Alpha 衰減速度

## 資料

| 來源 | 內容 | 位置 |
|---|---|---|
| 鏈上日線 | 13 條序列，約 3.5 年，來源 ErcinDedeoglu（CC BY 4.0） | `data/onchain/`（已收錄） |
| Binance REST | OHLCV、funding、OI | `core/data_sync.py` 產生，不收錄 |
| 微結構 | 逐筆、深簿 | 由 [crypto-datalake](https://github.com/anson1eechun/crypto-datalake) 匯出，不收錄 |

已知限制：Binance funding rate API 只有約 67 天歷史，OI 只有約 31 天，依賴這兩者的因子很難通過實證門檻。

repo 不收錄 `*.pkl`、`*.parquet`、`index.db`、報表 HTML 和備份，這些都可以由腳本重建。

## 已知限制

- 多處路徑寫死 `/home/anson/...`（vault、ledger、index.db），換機器要改 `config.yaml` 與腳本開頭常數。
- 依賴本機 Obsidian vault 與 Hermes Agent，單獨 clone 下來只能跑資料、回測與測試部分。
- 標的範圍：BTC/ETH 單資產時序，以及約 80 幣、約 3–5.5 年的 crypto 橫截面；這個 universe 對 t ≥ 2 的檢定力有限。
