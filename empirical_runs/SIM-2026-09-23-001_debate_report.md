---
kind: 辯論模擬
session: SIM-2026-09-23-001
verdict: CLOSE
type: priority-0 confirmatory
---

# SIM-2026-09-23-001 — comp_L ⊥ Mom20（priority 0）

> **判決：CLOSE**（預註冊機械判決，零自由度）。`ofi.size_bucketed` 子線封閉，3 回合配額不動用。
> 依 [[SIM-2026-09-14-001_debate_report]] Arbiter §12「優先序 0（而非一整輪）」執行。

## 流程
預註冊落盤（sha256 `d00d37c3…`）→ 複製鎖 → T1/T2/T3 → 歸檔。
Proposer 無（規格取自上輪 Arbiter）；Arbiter 不召喚（判準為預註冊機械規則）。

## 複製鎖（PASS）
| | IC | 淨 Sharpe | 上輪 |
|---|---|---|---|
| comp_L | +0.02058 | +0.5488 | +0.02054 / +0.5488 |
| Mom20（masked_ok） | −0.02974 | +0.8586 | −0.02974 / +0.8586 |
| Mom20（unmasked） | −0.02956 | +0.6536 | ✗ 不採用 |

## 預註冊中先行判定的適格性（v2.4 §4）
排序層 Mom20 IC −0.0297 比 comp_L +0.0206 強且反號 → **排序層殘差化不適格**。
美元層 Mom20 Sharpe +0.859 與 comp_L 同號 → 適格。故 T2 為唯一裁決檢定。

## 結果
| 檢定 | 原 | ⊥Mom20 | 備註 |
|---|---|---|---|
| **T2 淨 Sharpe（drift）** | 0.549 | **0.181**（NW t 0.36） | ρ **0.330** |
| **T2 淨 Sharpe（nodrift）** | 0.595 | **0.274**（NW t 0.54） | ρ **0.462** |
| T1 排序層 IC | 0.0206（t 4.90） | 0.0262（t 6.34） | **artifact**，依 §4 不得作正面證據 |
| T3 Mom20⊥comp_L Sharpe | 0.859 | 1.021（t 2.22） | Mom20 移除 comp_L 後反而更強 |
| T3 spanning 截距 | | 10.95%/年，NW t 0.53 | beta 0.306 |

兩口徑 ρ 皆 <0.50 → **CLOSE**。nodrift 的 0.462 距門檻 0.04，但兩口徑未跨越門檻，
v2.4 §2 解析度規則不觸發。預註冊已申報本閘門鑑別力低（SE(Sharpe)≈0.42）。

## 解讀
與 ASD 同一死法：**美元層 P&L 主要是 20 日動能的重複**（ASD 保留 38%，comp_L 33%／46%）。
排序層異象本身是真的、且方向上不被 Mom20 解釋——這是 §11.2「排序層真、美元層死」**第 4 次**出現。

## 對流程的意涵
crypto XS 流水線的美元層閘門在 T≈5.5 年、每日約 47 幣下 SE(Sharpe)=0.42，
結構上無法產出 validated。建議 v2.5 正式採用上輪 §11.2 選項 (a)（排序層 confirmatory + 邊際歸因，
美元層降為 disclosure）或 (b)（只打預期 Sharpe >1.2 的低換手／長 horizon 規格）。

## 產出
`SIM-2026-09-23-001_prereg.md` · `_replication_lock.json` · `_results.json` ·
`scripts/compL_mom20_20260923.py` · ledger +9（146→155）· index.db（備份 `index.db.bak-SIM-2026-09-23-001`）
