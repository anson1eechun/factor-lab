# Factor Lab — 多代理因子研究系統

## 目錄結構
```
/home/anson/factor-lab/
├── candidates/          # 候選因子筆記 (F{N}.md)
├── core/
│   ├── signals/         # 因子信號 Python 實作
│   ├── data.py          # 統一鏈上資料載入（load/meta/data_dictionary）
│   ├── adapters/crypto.py # 幣安 OHLCV 適配器
│   └── smoke_test.py    # 信號函數驗證
├── references/
│   ├── papers/          # 已歸檔論文
│   └── pending_extraction/ # 待精讀論文
├── graveyard/           # 已拒絕因子歸檔
├── index.db             # SQLite 因子知識庫索引
├── scripts/
│   └── debate_flow.py   # 辯論管線狀態機
└── CLAUDE.md            # 本檔案
```

## Obsidian Vault
路徑：`/home/anson/Documents/Obsidian Vault/量化交易/`
目錄結構：
- `01-交易策略/` — 因子筆記、策略組合
- `02-市场数据/` — 數據來源與處理
- `03-回测框架/` — 回測方法論
- `04-风险管理/` — 風控框架
- `05-编程技术/` — 實作技巧
- `06-书籍论文/` — 文獻筆記
- `07-交易心理/` — 行為金融
- `08-工具资源/` — 工具與資源
- `09-作者专题/` — 作者索引

Obsidian 筆記格式：
- 檔名：YYYY-MM-DD 標題.md
- YAML frontmatter 必要欄位：date, author, source, tags

## 辯論管線流程
1. `debate_flow.py prepare` — 準備階段（論文掃描）
2. `debate_flow.py run proposer` — Proposer 提出候選因子
3. `debate_flow.py run builder` — Builder 實作信號函數
4. `debate_flow.py run skeptic` — Skeptic 五維批判
5. `debate_flow.py run empiricist` — Empiricist 回測實證
6. `debate_flow.py run arbiter` — Arbiter 最終裁決
7. `debate_flow.py run librarian` — Librarian 歸檔

每個階段結束後需執行 `debate_flow.py done <agent>` 推進狀態。

## CryptoAdapter 使用
```python
from core.crypto_adapter import CryptoAdapter
adapter = CryptoAdapter()
df = adapter.get_ohlcv(symbol='BTCUSDT', interval='1d', limit=1000)
# 欄位: open, high, low, close, volume
# 索引: DatetimeIndex
```

## 資料限制
- Binance funding rate API：僅 ~67 天歷史

> ⚠️ 本檔是專案規則，不是 run-log。no-op／連線失敗（如 watcher DNS 解析失敗）**不要**寫進來；run-log 一律進 `logs/`。下列僅保留真實操作紀錄：
- 2026-06-14: 提案 F21 Credit Spread Term Structure Pressure Factor（來源 CIR++ 論文），建立雙向連結至因子庫
- 2026-06-13: 補齊 1 篇文獻 credibility 標註（deep learning 可轉債定價論文），清理 4 篇已不存在之紀錄
- 2026-06-13: 批量歸檔 6 篇待歸檔文獻（見下方列表）
- 2026-06-05: 處理 TimeClaw 文獻，建立與 Hypotheses to Factors 的雙向連結。

### 2026-06-13 批次歸檔
| 筆記 | Credibility | 類別 | 待提案因子線索 |
|-----|-------------|------|----------------|
| Beyond-Prompting-Agentic-AI-Factor-Investing | high | 方法論 | ✅ Agentic AI 自主因子發現框架 |
| Asymptotic-Behaviour-of-Unexpected-Losses | high | 風險管理 | ✅ 風險比率極限壓力測試 |
| Explicit-Rational-Formulae-for-Bachelier | high | 金融數學 | ✅ 無迭代 IV 計算工具 |
| Price as Focal Point Prediction Markets | medium | 預測市場 | ✅ SCI 訊號可信度指標 |
| LLM-Based Financial Sentiment Analysis | low | NLP | ❌ 僅方法參考 |
| Accurate Efficient Deep Learning (NOT_RELEVANT) | low | 不相關 | ❌ 建議刪除 |
- Binance OI API：僅 ~31 天歷史
- 所有依賴 funding rate/OI 的因子無法通過實證門檻
- 主要可用數據：
  - BTCUSDT 1d OHLCV（`empirical_runs/btcusdt_1d_1500.pkl`，~1500 根）
  - 鏈上日線 13 條（`data/onchain/`，~3.5 年；含 Coinbase Premium Gap、exchange netflow、taker buy/sell、MVRV…）
- 鏈上資料一律 `from core.data import load("<name>")`；資料字典 `data/onchain/data_dictionary.yaml`
- Signal 契約與唯一 harness：`docs/SIGNAL_CONTRACT.md`（`scripts/onchain_eval.py`，扣成本、lag≥1 無前視）
- 一鍵研究：`scripts/quick_research.py --factor <name>`（auto 選模→plateau→walk-forward→自包含 HTML 報告；stdout 印 JSON 供 agent 解析）

## 實證門檻
- |Rank IC| > 0.02
- IC-IR > 0.3
- Long-Short Sharpe > 0.5
- 最大回撤 < 30%
- 至少 T≥2

## 發起 Agent 調用
主 agent (Arbiter) 透過 terminal spawn 各 profile：
```
hermes chat --profile fl-<role> -q '<動態任務描述>'
```
所有 spawn 必須以 `/home/anson/factor-lab` 為工作目錄。
