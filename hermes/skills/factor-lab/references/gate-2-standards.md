---
name: factor-lab-gate-standards
description: Gate 2 裁決標準與 IC-IR 陷阱教訓 — 仲裁者在評估因子實證報告時必須遵守的額外守則。
triggers: arbiter 階段執行 Gate 2 審查時
---

# Factor-Lab Gate 2 標準（IC-IR 陷阱教訓）

## 核心教訓（來自 F16 CLV-Mom）

F16 CLV-Mom 的所有 horizon IC-IR 在 0.5~0.7 之間，看起來非常強勁。
但：
- LS Sharpe = 0.008（幾乎無效）
- 分組回報呈倒 U 型：Q2 最佳，Q5 ≈ Q1
- 因子有排序能力，但無法轉為正期望策略

**結論：IC-IR 是「陷阱指標」——高 IC-IR 不等於可交易 alpha。**

## Gate 2 必須附加的檢查

Gate 2 不能只看 IC-IR ≥ 0.3 就通過。必須附加：

### 1. 非線性表達測試
- 若 IC-IR 高但 quintile 分組非單調，因子可能只有排序能力而無經濟表達力。
- Arbiter 應標記：「IC-IR 有效但表達力不足 → 觀察」或「REWORK（調整表達方式）」。

### 2. 分組單調性（一票否決）
- 若 quintile 回報無單調性（Q5-Q1 spread < Q3-Q1 或 Q2 優於 Q5），因子不可直接 PASS。
- 可能的修復（REWORK）：logit 轉換、分段閾值、截斷極端 quintile。
- 若修復後仍無單調性 → REJECT。

### 3. IC-IR 與 Sharpe 落差檢查
- 若 IC-IR ≥ 0.4 但 LS Sharpe < 0.3，arbiter 必須：
  - 檢查 quintile 分組是否單調
  - 檢查是否存在非線性表達（如中間組最佳）
  - 標記為 REWORK 而非 PASS

### 4. Crypto 波動率 ≠ 傳統 risk premium
- 在 crypto 市場，高波動率區間往往伴隨負 Sharpe。
- 若因子假設「高波動 = 高風險溢價」，arbiter 應懷疑此假設在 crypto 中的有效性。
- Skeptic 在質疑此類因子時，應主動引用此反例。

## 參考
- F16 CLV-Mom 裁決記錄
- 知識庫：2025-11-25_Multivariate_Bitcoin_Volatility_Gradient_Boosting（crypto vol 特性）
- 2026-05-31 週常辯論會 F12/F16 案例
