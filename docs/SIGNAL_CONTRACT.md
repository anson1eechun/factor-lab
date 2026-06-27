# Signal 契約 — factor-lab 唯一 harness（Phase 0 定案）

> 目的：終結「回測棧分裂」。factor-lab 的**單資產時序**研究（crypto / 鏈上）一律走這條契約與
> harness；任何 signal 只要遵守契約，就能被同一支 harness 公平、扣成本、無前視地評估。

## 1. 契約（signal 作者只需記這段）

一個 signal 是一個**無參數函數**，回傳一條 **pandas.Series**：

```python
def strategy() -> "pd.Series":
    # index: DatetimeIndex（日頻，floor 到日）
    # value: 目標部位 position ∈ [-1, 1]
    #        +1 = 滿倉做多, -1 = 滿倉做空, 0 = 空手, 分數 = 按比例
    ...
```

- **方向即部位**：回傳的是「想持有的部位」，不是買賣訊號。harness 自己算換手與成本。
- **無前視是 harness 的責任，不是你的**：你可以用到「當日」資料；harness 會 `shift(lag)`（見下）。
- **資料一律走 `core.data`**，不要再在 signal 內各自寫 `_load()`：

```python
from core.data import load
prem = load("coinbase_premium_gap")        # date-indexed Series（自動容錯 btc_ 前綴）
# ... 你的邏輯：標準化、門檻、tanh 壓到 [-1,1] ...
```

- **把因子轉成部位**：用 `core.signal_models`（Phase 1）的 model 庫 + 自動選模，免每次手刻：

```python
from core.signal_models import auto_signal, data_profile
prof = data_profile(prem)               # 依資料結構建議 model（透明、附理由）
pos  = auto_signal(prem, direction=1)   # -> 部位 Series ∈[-1,1]；direction 由 alpha story 決定
```
model 庫（依資料結構匹配）：`zscore_reversion`（連續均值回歸）、`trend_drift`（持續趨勢）、
`percentile_rank`（偏態/有界）、`breakout_spike`（厚尾尖峰）、`sign_flow`（繞零有號流量）。

## 2. Harness：`scripts/onchain_eval.py`（唯一入口）

```
uv run --with "numpy>=2" --with pandas --with scipy \
    python scripts/onchain_eval.py <module> [func=strategy] [cost_bps=10] [lag=1]
```

harness 對部位做的事（節錄自 `scripts/onchain_eval.py`）：

1. 取 BTC 日線（`empirical_runs/btcusdt_1d_1500.pkl`），`fwd = close.shift(-1)/close - 1`（次日報酬）。
2. `pos = pos.reindex(price_dates).ffill().shift(lag).fillna(0).clip(-1, 1)`
   - **`lag` 預設 1**：鏈上資料有回報延遲，用「前一日」訊號交易 → **杜絕前視**。
3. `gross = pos * fwd`；`turnover = |Δpos|`；`net = gross - turnover * cost_bps/1e4`（預設 **10 bps**）。

輸出指標（全部扣成本後）：

| 指標 | 意義 |
|---|---|
| `net_sharpe` | 年化 Sharpe（√365） |
| `ann_return` / `max_drawdown` | 年化報酬 / 最大回撤 |
| `t_stat` | 日報酬 t 值（顯著性） |
| `turnover_per_day` / `breakeven_bps` | 日換手 / 打平成本（gross_bps ÷ turnover） |
| `exposure` | 在場比例 |
| `sharpe_ex_top5pct` | **剔除最強 5% 日後的 Sharpe**（戳破「靠幾天暴賺」的尾部假象） |
| `sharpe_by_year` | **逐年 regime** Sharpe（看跨牛熊穩定性） |

## 3. 真實範例（live run，非杜撰）

`core.signals.FSIM_Onchain_Supply:whale_short`（鯨魚充值比偏高→賣壓→做空）：

```json
{ "days": 1261, "net_sharpe": 0.28, "ann_return": 0.0737, "max_drawdown": -0.5593,
  "breakeven_bps": 13.96, "sharpe_ex_top5pct": -3.236,
  "sharpe_by_year": {"2022": -1.02, "2023": 1.46, "2024": -1.68, "2025": 1.62, "2026": 0.02} }
```

讀法：整體 Sharpe 0.28 看似有微弱 edge，但 `sharpe_ex_top5pct = -3.24` + 逐年正負交替，說明 edge 集中在少數尾部日、跨 regime 不穩 — 這正是 harness 要逼出來的誠實判斷。

## 4. 兩套棧的分工（為何說「分裂」已收斂）

- **時序 / 單資產（本契約）** → `scripts/onchain_eval.py` + `core.data`。crypto、鏈上研究的**唯一**路徑。
- **橫截面 / 多資產** → `core/backtest.py`、`core/preprocessing.py`（包裝 `alphapurify`，給 equity universe 用）。
  ⚠️ `alphapurify` **目前環境未安裝**，該路徑休眠中；要用須先裝。crypto/鏈上研究**不要**走這條。

Phase 2 已在本契約上**疊加**（`core.backtest`，與本 harness 同成本/lag/√365 慣例）：
- `evaluate_positions(pos, px, cost_bps, lag)` — 成本感知評估（與 `onchain_eval` 同數字）。
- `grid_optimize(make_pos, param_grid, px)` — best params + `plateau_score`（那片綠的密度）+ `positive_frac` + 2 參數 heatmap。
- `rolling_walk_forward(make_pos, param_grid, px, train_days, test_days, step_days)` — 每折重選參、串接 OOS → `cv_sharpe` + 正向折數 + `oos_max_drawdown`。

不取代本契約。
