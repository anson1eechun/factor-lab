---
session_id: SIM-2026-06-07-002
title: 辯論模擬 — Volume-Weighted Trend Persistence (VWTP)
date: 2026-06-07
kind: 辯論模擬 (multi-agent simulation; 非正式研究產出)
factor: FSIM_Volume_Weighted_Trend_Persistence
verdict: REWORK
data: empirical_runs/btcusdt_1d_1500.pkl (BTCUSDT 1d, 1500 bars)
harness: scripts/debate_sim_eval.py (確定性,已獨立重現)
agents: Claude Code 子代理 ×3 (Proposer/Builder/Skeptic) + 主代理 (Empiricist/Arbiter/Librarian)
---

# 辯論模擬報告 — VWTP (Volume-Weighted Trend Persistence)

> ⚠️ 多子代理模擬 factor-lab 辯論;實證數字皆為真實回測(無捏造)。

## 1. Proposer — 候選因子
**Volume-Weighted Trend Persistence (VWTP)**(換方向:動能延續,非上輪的反轉)
- **假設**:量能確認的方向一致性越高 → 趨勢越可能延續;量價背離則延續性弱。
- **公式**:`contrib=sign(r)·|r|·(V/SMA(V,20))`;`vwtp=Σcontrib_20 / Σ(|r|·vrel)_20 ∈[-1,1]`;`z=zscore(vwtp,90)`;`clip(-3,3)`;`EMA(halflife=3)`;`shift(1)`。
- **預期**:正 IC。修正了 F19 的 U 型缺陷(num/den 正規化恢復方向單調性)。

## 2. Builder — 實作
`core/signals/FSIM_Volume_Weighted_Trend_Persistence.py`,簽名 `factor(ohlcv_df, window=20, z_window=90, ema_halflife=3, eps=1e-12)`,無前視,smoke test 過(n_obs=1372)。

## 3. Empiricist — 真實回測(BTCUSDT 1d,N=1372)
| 指標 | 值 | 門檻 | 通過 |
|---|---|---|---|
| Rank IC 1d | +0.0199 | \|IC\|>0.02 | 貼線 |
| Rank IC 3d | +0.0268 | — | |
| Rank IC 5d | +0.0564 | — | |
| Rank IC 10d | +0.0993 | — | (疑 overlapping 膨脹) |
| IC-IR (roll90) | **-0.221** | >0.3 | ❌ |
| Long-Short Sharpe | **0.659** | >0.5 | ✅(但見批判) |
| Max Drawdown | **-34.3%** | <30% | ❌ |
| t-stat | **1.337** | ≥2 | ❌ |
| 年化報酬 | +19.6% | — | |

## 4. Skeptic — 五維批判(摘要)
1. **前視**:結構低風險;須查證 zscore 用因果滾動基準。
2. **過擬合**:20/90/3 圓整數=隱性自由度;horizon IC 單調上升疑為 **overlapping forward returns 自相關膨脹**(10d 等效獨立樣本僅 ~137)。
3. **數據限制**:單資產 1372、LS 557 活躍日;2021–2025 含多段大牛,full-sample 正 IC 恐由少數 regime 撐起,無法外推。
4. **經濟邏輯**:量價齊升延續有微觀結構支撐,但與反轉效應隨 regime 切換,非全程同號。
5. **穩健性(關鍵)**:**full-sample IC 正、rolling IC-IR −0.22** = regime 偽裝的趨勢 beta,多數時點站錯邊;Sharpe 0.66 為 false positive,被 t=1.34、MaxDD 34.3% 雙重否證。
- **建議:REJECT**。

## 5. Arbiter — 裁決:**REWORK**
- 與 Skeptic 的 REJECT 不同:動能方向**確有訊號**(IC 全正單調、Sharpe 過門檻),不像上輪反轉是死的 → 值得重做。
- 但 IC-IR/MaxDD/t 三項未過,不穩定診斷成立。**未達標前不得進任何資金配置。**
- **REWORK 路線**:(1) zscore 改 expanding 因果估計重跑;(2) 用**非重疊** forward returns 重算各 horizon IC/t;(3) sub-period/regime 分解證明非單牛市獨撐;(4) 加 ETH 等資產 OOS;(5) 20/90/3 參數敏感度掃描。重審門檻:IC-IR>0、t≥2。

## 6. Librarian — 歸檔
- 因子筆記:`candidates/FSIM_Volume_Weighted_Trend_Persistence.md`(REWORK)
- index.db:session `SIM-2026-06-07-002`
- 本報告:`empirical_runs/SIM-2026-06-07-002_debate_report.md`

---
## 兩輪對照
| | 輪1 IIR | 輪2 VWTP |
|---|---|---|
| 機制 | 流動性反轉 | 量能動能延續 |
| Rank IC | 近 0/負 | **全正單調** |
| LS Sharpe | -0.16 | **0.659** |
| IC-IR | -0.08 | -0.22 |
| 裁決 | **REJECT**(死) | **REWORK**(有方向、不穩定) |


---

# REWORK 迭代(2026-06-07,真實計算)

照 Arbiter 路線執行 5 項,harness:`scripts/debate_rework_vwtp.py`。新增 ETH 資料 `empirical_runs/ethusdt_1d_1000.pkl`(Binance,2023-09~2026-06)。

## ① expanding zscore
改因果 expanding zscore:IC-IR −0.22 → −0.34(更差)→ 原 rolling 版**沒偷未來**(否則 expanding 會變好),排除前視疑慮。

## ② 非重疊 forward returns IC + t(證實 Skeptic)
BTC 5d ic=0.059 t=0.98;BTC 10d ic=0.092 t=1.07;ETH 10d ic=0.168 t=1.58。
→ overlapping 的 10d IC 0.099 在非重疊下 t 僅 1.07:量級真、顯著性被重疊膨脹高估。

## ③ 年度 regime 分解(關鍵翻案)
BTC h=5 IC:**2022 = −0.128**、2023 +0.067、2024 +0.066、2025 +0.045、2026 +0.068。
→ **4/5 年穩定為正(~+0.06/年),只有 2022 大熊崩盤反轉**。負 IC-IR 是「動能在 2022 崩盤反轉」單一 regime 拖累,非雜訊(推翻 Skeptic「單一牛市撐起」假設,實情相反)。

## ④ ETH 多資產(關鍵正面)
ETH(expanding,無濾):LS Sharpe **1.088**、MaxDD **−27.5%(過門檻)**、t **1.805** → 機制跨資產複製且更強,非 BTC 過擬合。

## ⑤ 參數敏感度掃描(18 組)
20/90/3 非 cherry-pick;但 0/18 組達 IC-IR>0 + 非重疊 t5d≥2;IC-IR 全負(−0.22~−0.47)→ 2022 反轉穩健存在。

## ⑥ 趨勢 regime filter(close > 100日SMA 才進場)
BTC:Sharpe 0.514→**0.875**、t 1.04→**1.78**、MaxDD −0.38、非重疊5d IC 0.105。
ETH:Sharpe 0.941、MaxDD **−0.123**、t 1.57。
→ 濾掉 2022 後 BTC 顯著逼近門檻、ETH 回撤大降。

## REWORK 後 Arbiter 複判:**維持 REWORK(機制已驗證,軌跡明確)**
- 仍未全達標:BTC LS t=1.78<2、MaxDD 38%>30%;IC-IR 全 param 為負。
- 但:4 年 IC 穩定為正 + ETH 複製(Sharpe>1)+ 失敗單一歸因 2022 動能崩盤 + regime filter 推近門檻。
- **下一步**:(a) 波動目標化/MaxDD 控制壓 38% 回撤;(b) 更穩健 crash 偵測補強 regime;(c) 多資產池正式 OOS 取 t≥2;(d) IC-IR 改 regime-conditional。達 IC-IR>0 + t≥2 + MaxDD<30% 前不配資。
- 結論:從「不穩定的可疑訊號」升級為「機制清楚、待風控收尾」的動能候選因子。


## v2 推門檻嘗試(2026-06-07,真實)— regime filter + 波動目標化 + BTC/ETH 組合
harness:`scripts/vwtp_v2_validate.py`(max_lev=1.0 只去槓桿,target_vol=0.4)
| 門檻 | 結果 |
|---|---|
| LS Sharpe>0.5 | ✅ 0.87(組合)/ BTC 0.95 / ETH 0.80 |
| IC-IR>0.3(regime) | BTC 0.287(差一點)/ ETH 1.14 ✅ |
| MaxDD<30% | ✗ −33%(BTC 主導;改善自 v1 的 −38%)|
| t≥2 | ✗ 1.76(組合)/ BTC 1.91 |
**結論:三指標卡門檻邊緣,未乾淨過關 → 維持 REWORK(borderline),不調參硬推。** 真要過需更多資產做正式 OOS 拉高 t、或接受它是需組合層風控的動能因子。
