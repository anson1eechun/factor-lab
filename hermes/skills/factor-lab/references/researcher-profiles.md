# Researcher Profiles for Factor-Lab

2026-05-31 建立的三個 researcher profiles，可作為 factor-lab agent 的替代執行環境。

## Profile 配置總覽

| Profile | 模型 | Provider | Context | Max Tokens | 成本 (in/out per 1M) | SOUL 角色 |
|---------|------|----------|---------|------------|----------------------|-----------|
| `researcher1` | `deepseek/deepseek-v4-pro` | openrouter | 1M | 32768 | $0.43 / $0.87 | 數據分析師 — 數據驅動決策 |
| `researcher2` | `openai/gpt-5.5` | openrouter | 400K | 16384 | $5 / $30 | 技術研究員 — 技術架構與代碼 |
| `researcher3` | `minimax/minimax-m2.7` | openrouter | 200K | 16384 | $0.26 / $1.20 | 市場策略師 — 市場與投資分析 |

所有 profile 的 OpenRouter API key 統一存放於各 profile 的 `.env`（`OPENROUTER_API_KEY`），從 deepseek profile 複製。

## 建議的 Factor-Lab 角色映射

| Factor-Lab Step | Profile | 理由 |
|-----------------|---------|------|
| **Proposer** (創意提案) | `researcher2` (GPT-5.5) | 最強推理力，論文合成+經濟直覺 |
| **Builder** (代碼實作) | `researcher3` (MiniMax M2.7) | 編碼優化型模型，公式→Python 強項 |
| **Skeptic** (五維批判) | `researcher1` (DeepSeek V4 Pro) | 量化批判，數據分析師視角 |
| **Empiricist** (回測實證) | `researcher1` (DeepSeek V4 Pro) | 數據分析核心，同角色不同 task |
| **Arbiter** (最終裁決) | deepseek (主 agent) | 最高品質裁決，不委派 |

## Spawn 指令

```bash
# Proposer
hermes --profile researcher2 chat -q '<prompt>' -s factor-lab-proposer

# Builder
hermes --profile researcher3 chat -q '<prompt>' -s factor-lab-builder

# Skeptic
hermes --profile researcher1 chat -q '<prompt>' -s factor-lab-skeptic

# Empiricist
hermes --profile researcher1 chat -q '<prompt>' -s factor-lab-empiricist
```

## 煙霧測試結果（2026-05-31）

三個 profile 均通過煙霧測試，身份回應正常：

- `researcher1`：**【数据分析师】** 數據驅動，量化決策的分析師。
- `researcher2`：**【技术研究员】** 專注技術架構與代碼質量分析。
- `researcher3`：**我是专注市场策略的分析师，洞察机会与风险。**

## 注意事項

1. **SOUL.md 角色前綴**：所有 profile 的 SOUL.md 強制輸出前綴（如「【技術研究員】」），可能汙染 factor-lab skill 的輸出格式。需實測確認 skill 指令與 SOUL.md 的優先級。
2. **API Key**：所有 profile 透過 OpenRouter 統一管理，key 存放在各 profile 的 `.env`，非 global `.env`。
3. **成本**：researcher2 (GPT-5.5) 成本最高 ($30/M output)，但 Proposer 產出量有限（~2-3K tokens/次），單次辯論約 $0.10-0.30。
4. **Context 限制**：researcher3 (MiniMax M2.7) context 僅 204K，但 Builder 的輸入（候選筆記 + 既有代碼）通常 < 20K tokens，綽綽有餘。
