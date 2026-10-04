---
session_id: SIM-2026-06-07-003
title: 辯論模擬 — Volatility-of-Volatility Timing (VoVT)
date: 2026-06-07
kind: 辯論模擬 (multi-agent simulation; 非正式研究產出)
factor: FSIM_Vol_of_Vol_Timing
verdict: REJECT
data: empirical_runs/btcusdt_1d_1500.pkl (BTCUSDT 1d, 1500 bars)
harness: scripts/debate_sim_eval.py (確定性,已獨立重現)
agents: Claude Code 子代理 ×3 (Proposer/Builder/Skeptic) + 主代理 (Empiricist/Arbiter/Librarian)
---

# 辯論模擬報告 — VoVT (Volatility-of-Volatility Timing)

> ⚠️ 多子代理模擬 factor-lab 辯論;實證數字皆為真實回測。

## 1. Proposer — 候選因子
**VoVT**(全新方向:波動的二階矩)
- **假設**:已實現波動本身的不穩定(vol-of-vol 高)= 擾動/不確定期 → 後續報酬偏負;低 vov(穩定)→ 偏正。
- **公式**:`pk=(1/4ln2)(ln(H/L))²`;`rv=sqrt(mean(pk,10))`;`vov=std(rv,20)`;`z=zscore(vov,60)`;`raw=-z`;`signal=raw.shift(1)`。
- **預期**:正 IC。衡量波動穩定度,與波動水位(F6)正交。

## 2. Builder — 實作
`core/signals/FSIM_Vol_of_Vol_Timing.py`,簽名 `factor(ohlcv_df, rv_window=10, vov_window=20, z_window=60)`,無前視,smoke 過(n_obs=1409)。

## 3. Empiricist — 真實回測(BTCUSDT 1d,N=1409)
| 指標 | 值 | 門檻 | 通過 |
|---|---|---|---|
| Rank IC 1d/3d/5d/10d | −0.0003 / +0.0014 / −0.0001 / +0.0056 | \|IC\|>0.02 | ❌(全≈0)|
| IC-IR (roll90) | +0.097 | >0.3 | ❌ |
| LS Sharpe | −0.066 | >0.5 | ❌ |
| Max Drawdown | −38.4% | <30% | ❌ |
| t-stat | −0.134 | ≥2 | ❌ |

## 4. Skeptic — 五維批判(摘要)
- IC 在 [−0.0003, +0.0056] 變號亂跳 = **純噪音特徵**(非過擬合)。
- 單資產 1409、活躍日僅 489(35%),統計力薄弱。
- **關鍵經濟邏輯錯位**:BTC 波動叢聚強,高 vov 出現在劇烈**雙向**行情,對報酬**符號**幾乎零資訊;vov 能預測「未來波動大小」而非「方向」→ 把它當方向 alpha 是用錯地方,頂多是 vol-targeting 的倉位縮放器。
- **建議:REJECT**。

## 5. Arbiter — 裁決:**REJECT**
5 門檻全敗;唯一正的 IC-IR 0.097 與負 Sharpe 自相矛盾、無經濟價值。機制誤用(波動量級≠報酬方向)。若要救只能改造成 vol-targeting 縮放器,那已非方向因子。

## 6. Librarian — 歸檔
- 因子筆記:`deprecated/FSIM_Vol_of_Vol_Timing.md`
- index.db:`debate_sessions`/`transcripts`/`rounds`(session `SIM-2026-06-07-003`)+ **寫入 `factors` 表**(故出現於控制台)
- 本報告:`empirical_runs/SIM-2026-06-07-003_debate_report.md`

## 三輪總結
| 輪 | 因子 | 機制 | 裁決 |
|---|---|---|---|
| 1 | IIR | 流動性反轉 | REJECT(機制不適用 BTC)|
| 2 | VWTP | 量能動能延續 | REWORK(有真 edge,需 regime 風控)|
| 3 | VoVT | 波動二階矩擇時 | REJECT(波動量級≠方向)|
