---
session: SIM-2026-06-18-003
kind: 辯論模擬
factor: FSIM_LowVol_Tilt
type: directional
verdict: REJECT
date: 2026-06-18
---

# 因子辯論報告 — FSIM_LowVol_Tilt(crypto long-only 低波動傾斜)

**Session** `SIM-2026-06-18-003` · **裁決 REJECT** · 80 幣加密 universe(2023-02~2026-06)
線索來源:`SIM-2026-06-18-002`(CalmStreak)對照組——純 -RV60 有真 IC(IC-IR 0.21、IC t 6.93)但 quintile LS 不可變現 → 改測 **long-only tilt vs 等權基準**。

## 流程註記
本輪信號極簡(low-vol 分數 -RV60),Proposer/Builder 由主代理內聯;保留 rigor 關鍵的**獨立 Skeptic + 獨立 Arbiter + 真實基準回測**。

## Empiricist(主代理親跑,net 10bps)

| 變體 | net Sharpe | 超額 Sharpe(vs EW,=vol-target後) | IR | MaxDD | t |
|---|---|---|---|---|---|
| EW 基準 | 0.077 / 0.145(1w) | — | — | -84% | 0.14 / 0.24 |
| A 逆波動 1d | 0.085 | +0.008 | 0.06 | -82% | 0.15 |
| B 低波動q 1d | 0.102 | +0.025 | 0.02 | -77% | 0.18 |
| A 逆波動 1w | 0.195 | +0.05 | 0.82 | -82% | 0.32 |
| **B 低波動q 1w** | **0.581** | **+0.436** | **1.167** | -67% | 0.96 |

- Mono(RV quintile)0.2;quintile_fwd(0高RV..4低RV)=[0.00023, 0.00029, -0.00029, 0.0001, 0.00046](非單調,靠最低波動端點);corr 低波動 vs size -0.10(**非 size 代理**);regime 1d 超額 Sharpe 前 0.032 → 後 0.006(衰退但仍正)。

## Risk
standalone:~95% crypto beta、MaxDD -67~84% 不可用;overlay/tilt:對等權微正超額(IR 0.82~1.17,t 不顯著)。

## Skeptic
超額正但多為機械降波動;1w-B Sharpe>0.5 但 t0.96 不顯著且 4 選 1(Bonferroni p≈0.67);MaxDD 超標 2~3 倍,名為 LowVol 卻 -84%;Mono 0.2 非單調=端點過擬合;本質是 -RV 砍掉 LS 腿後 long-only 化的 market beta。(主代理已校正其 n-樣本算術:1w-B ~2.7 年/140 週,非 3 週。)

## Arbiter(獨立子代理,未被告知期望)
**REJECT。** 四項硬門檻失敗:① 超額 Sharpe 唯一達量級者(1w-B)t 0.96 不顯著、deflate 後 p≈0.67;② MaxDD -67~84% 超標 2~3 倍;③ Mono 0.2 非單調;④ regime 衰退趨零、本質 market beta。非參數可修。若堅持 REWORK:改測**純 overlay 的條件式增益**,單一預註冊週頻設定 + 2025+ 樣本外 holdout,要求 t≥2。

## 多重比較登錄(ledger N)
本 session 4 變體(A/B × 1d/1w);1w-B 為最佳,deflate 後不顯著。

## 教訓 / 殘餘線索
- **低波動異常在此 crypto 樣本是「真但太薄」**:IC 層級真實(上一輪 IC t 6.93),但無論 LS(噪音)或 long-only tilt(market beta + 機械降波動 + 災難 DD)都無法變現。
- crypto 的巨大共同 beta + -67~84% 系統性回撤,使「低波動」名不副實——低波動幣崩盤照崩。
- **唯一未死的路**:把它當**純 overlay**(在 EW 基準上加薄 tilt),單一預註冊設定 + OOS holdout 驗 t≥2。否則低波動這條線在此 universe/樣本應歸檔。

---

## OOS round 2 — 預註冊乾淨驗證(SIM-2026-06-18-003-OOS)→ REJECT,低波動線封存

依上節活路做**預註冊**:鎖定唯一設定(**逆波動 overlay**、RV60 日、週頻 reb、10bps,**故意不選 in-sample 贏家 quintile-B**),IS≤2024-12 / OOS≥2025-01,裁決規則機械鎖定:`VALIDATE ⟺ OOS 主動報酬 t≥2 且 IR>0.5 且 主動MaxDD<30%`。

| | 主動報酬年化 | IR | t | 主動MaxDD | tilt Sharpe vs EW |
|---|---|---|---|---|---|
| IS(≤2024) | -1.8% | -0.37 | -0.50 | -8.8% | 1.018 vs 1.005 |
| OOS(≥2025) | +4.2% | 0.87 | **1.045** | -2.9% | -0.92 vs -0.93 |

**預註冊裁決:REJECT**(OOS 主動 t 1.045 < 2,規則機械觸發,無人為裁量)。
- **符號翻轉**:IS 主動 IR -0.37 → OOS +0.87,效應不穩。
- tilt Sharpe ≈ EW(IS 1.02 vs 1.01、OOS -0.92 vs -0.93)→ overlay 幾乎沒加東西。
- **紀律證明價值**:若當初挑 in-sample 贏家(1w quintile-B)會誤判 validate;param-free 預註冊在 holdout 上 t 不顯著 + 符號翻轉。
- **低波動這條線在此 universe/樣本正式封存**;真要復活須換更長樣本或更廣 universe 並重置 ledger。
