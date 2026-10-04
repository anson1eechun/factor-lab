---
session_id: SIM-2026-06-07-001
title: 辯論模擬 — Illiquidity-Impact Reversal (IIR)
date: 2026-06-07
kind: 辯論模擬 (multi-agent simulation; 非正式研究產出)
factor: FSIM_Illiquidity_Impact_Reversal
verdict: REJECT
data: empirical_runs/btcusdt_1d_1500.pkl (BTCUSDT 1d, 1500 bars)
harness: scripts/debate_sim_eval.py (確定性,已獨立重現)
agents: Claude Code 子代理 ×3 (Proposer/Builder/Skeptic) + 主代理 (Empiricist/Arbiter/Librarian)
---

# 辯論模擬報告 — IIR (Illiquidity-Impact Reversal)

> ⚠️ 本檔為「用 Claude Code 多子代理模擬 factor-lab 辯論管線」的產出,**非正式因子研究**。
> 但所有**實證數字皆為真實回測算出**(無捏造),符合「不要假資料」原則。

## 0. 流程與分工
| 階段 | 執行者 | 性質 |
|---|---|---|
| Proposer | 子代理 #1 | 提出候選因子 |
| Builder | 子代理 #2 | 實作 signal 函數 + smoke test |
| Empiricist | 主代理 | 跑確定性真回測(子代理數字已獨立重現) |
| Skeptic | 子代理 #3 | 五維批判 |
| Arbiter | 主代理 | 對門檻裁決 |
| Librarian | 主代理 | 歸檔 + 本報告 |

## 1. Proposer — 候選因子
**Illiquidity-Impact Reversal (IIR)**
- **假設**:高 Amihud 非流動性(|報酬|/成交額)下的價格變動多為流動性衝擊而非資訊,隨後均值回歸。
- **公式**:
  - `r_t = ln(C_t/C_{t-1})`;`DV_t = C_t·V_t`;`ILLIQ_t = |r_t|/DV_t`
  - `illiq_z_t = zscore(ln(mean(ILLIQ,5)+eps), 90)`
  - `mom_t = sum(r,5)`;`IIR_raw_t = -illiq_z_t · tanh(zscore(mom,90))`
  - `signal_t = zscore(IIR_raw,60).shift(1)`
- **預期**:正 Rank IC(內含反轉)。
- **新穎性**:現有 F6/F7/F10/F18/F19/F20 皆價格結構/波動/regime;IIR 是唯一以「量能效率(Amihud)」為核心的流動性反轉因子。

## 2. Builder — 實作
- 檔案:`core/signals/FSIM_Illiquidity_Impact_Reversal.py`,簽名 `factor(ohlcv_df, illiq_window=5, z_window=90, sig_window=60, eps=1e-12)`。
- 無前視:rolling 統計僅用至 t,最後 `signal.shift(1)`;`min_periods` 保證暖機期 NaN。
- smoke test 通過,n_obs=1346。

## 3. Empiricist — 真實回測(BTCUSDT 1d,N=1346 有效)
| 指標 | 值 | 門檻 | 通過 |
|---|---|---|---|
| Rank IC 1d | -0.0052 | — | |
| Rank IC 3d | -0.0068 | — | |
| Rank IC 5d | **+0.024** | \|IC\|>0.02 | 勉強 |
| Rank IC 10d | -0.0048 | — | |
| IC-IR (roll90) | **-0.08** | >0.3 | ❌ |
| Long-Short Sharpe | **-0.164** | >0.5 | ❌ |
| Max Drawdown | **-55.9%** | <30% | ❌ |
| t-stat | **-0.33** | ≥2 | ❌ |
| 年化報酬 | -4.8% | — | |

(harness 確定性,主代理已獨立重跑,數字完全重現。)

## 4. Skeptic — 五維批判(摘要)
1. **前視**:防線基本正確(shift1 + 滾動門檻 + t→t+1),洩漏非失敗主因。
2. **過擬合**:N=5/90/60 拍腦袋;4 個 horizon 只有 5d 為正、且正好對齊 5 日窗 → 「挑 horizon」的過擬合指紋;多重檢定校正後即消失。
3. **數據限制**:單資產 1346 樣本功效薄弱;Amihud 設計給中小流動性資產,BTC 流動性極深、分母過大使 ILLIQ 近常數;日線抹平日內反轉。
4. **經濟邏輯**:1d/3d IC 為負代表高 ILLIQ 漲跌反而**延續**(資訊性),與反轉假設相反;翻號也救不了(會翻掉唯一亮點)。
5. **穩健性**:IC-IR/Sharpe/t 全負、MaxDD 55.9% 災難級;t=0.33 與「無訊號」無法區分。
- **建議:REJECT**。

## 5. Arbiter — 裁決:**REJECT**
- 5 門檻:|IC|(5d 勉強)、IC-IR ❌、Sharpe ❌、MaxDD ❌、t ❌ → 4 項明確未過。
- 唯一達標的 5d Rank IC 帶多重檢定/過擬合瑕疵,不足採信。
- 實作確認無前視。
- **Rework 方向(若要救)**:這已是另一個因子 —— 需多資產(含中小流動性山寨幣)+ 日內頻率,重新檢驗 Amihud 反轉是否存在。BTC 日線上機制不成立。

## 6. Librarian — 歸檔
- 因子筆記:`deprecated/FSIM_Illiquidity_Impact_Reversal.md`(REJECT)
- index.db:`debate_sessions` / `debate_transcripts` / `debate_rounds`(session `SIM-2026-06-07-001`,清楚標註為模擬)
- 本報告:`empirical_runs/SIM-2026-06-07-001_debate_report.md`
