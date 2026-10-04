---
session: SIM-2026-06-20-001
kind: 辯論模擬
factor: FSIM_FlowPersistence
type: cross-sectional
verdict: REJECT
date: 2026-06-20
---

# 因子辯論報告 — FSIM_FlowPersistence(taker-flow 持續性,順勢,橫截面)

**Session** `SIM-2026-06-20-001` · **裁決 REJECT** · 80 幣加密 universe(flow，2023~2026，n=1130 天)
線索:訂單流的**反轉**版本(OFR/CVD/TFI，SIM-011/012)早已 REJECT；本輪測**順勢/持續性**這一相對未開發的方向，看 taker 流的跨日漂移能否收割。

## 1. Proposer(子代理)
提 **FSIM_FlowPersistence**:過去 10 天 taker flow imbalance(tfi)**方向持續一致**的幣，未來相對報酬高。機制宣稱=持續單向 taker 流入代表分批建倉+做市商庫存壓力，推動跨日順勢漂移；用 `sign` 一致性 + z-score clip±3 + 流動性閘宣稱可避開「訂單流反轉的微結構死法」。新維度=taker 流的**持續性(順勢)** 而非反轉。

## 2. Builder(子代理)
`core/signals/FSIM_FlowPersistence.py`，簽名 `factor(flow_df, n=10, z_window=60, clip=3.0)`。per-coin:tfi 做 60 日滾動 z-score(ddof=1，std==0→NaN)→ clip±3；`consist=mean(sign(tfi),10d)`、`mag=mean(z,10d)`、`raw=consist*mag`、`shift(1)`。Smoke pass(len 對齊/暖機 NaN/1131 有效值/無前視)。

## 3. Empiricist(主代理親跑，crosssec_flow_eval + 自訂 dollar-PnL，net 10bps)

| 指標 | 值 | 門檻 | 過? |
|---|---|---|---|
| Rank IC | 0.0062 | >0.02 | ✗ |
| IC-IR | 0.051 | >0.3(Gate1) | ✗ |
| IC_t | 1.708 | ≥2 | ✗ |
| Mono | 非單調(最低分位 0.00039 > 最高分位 0.00005，方向**反**) | ≥0.7 | ✗ |
| 順勢 LS net Sharpe | h1 **−2.07**(t−3.65)/ h5 −0.68 / h10 −1.18，逐年 2023-26 **全負** | >0.5 | ✗ |
| 順勢剔最高5%日 | −3.4 ~ −4.9(更負) | — | ✗ |

**翻號(反轉方向)診斷**:h1 −1.05 / h5 −0.48 / h10 +0.438(t=0.77 不顯著)；剔最高5%日 **−2.55**(尾部集中)。
**流動性閘**(剔最小 30% dollar-vol):順勢 −0.58、反轉 −0.49 → **無改善**。

ledger 登錄 2 行(順勢 + 翻號)。

## 4. Risk(主代理)
book 內無已驗證的 crypto 橫截面因子；此因子兩方向 net Sharpe 皆負 → 邊際 Sharpe 貢獻 ≤ 0，無 book 價值。相關性分析無意義(負 Sharpe 無可疊加之 alpha)。

## 5. Skeptic(子代理)
(1) 順勢假設被**符號反向**證偽(LS IC_t −3.65、逐年全負)，非「沒訊號」而是「方向就是錯」。(2) 唯一翻正格(反轉 h10)t=0.77 本就不顯著，剔尾 −2.55=族C尾部集中的假陽性。(3) 庫存溢價故事與資料三處矛盾、事後附會。(4) clip/流動性閘是**安慰劑**——剔尾更負、流動性閘無改善，證明虧損是橫截面普遍、扣成本後結構性為負，非尾部污染。(5) 與已 REJECT 的 TFI/OFR/CVD 反轉族(SIM-011/012)同源，無可區別新機制。建議 do-not-revisit。

## 6. Arbiter(獨立子代理，未被告知期望)
**REJECT。通過 0/6 硬門檻**，Gate1(IC-IR 0.051)直接未過。多重比較 deflation:N≥12(順勢/反轉 × hold 1/5/10 × 全體/流動性閘)，唯一正號(反轉 h10，p≈0.44)Bonferroni p×N≈5.3≫0.05，且剔尾轉負 → **deflation 後零個站得住的顯著訊號**。定性:**符號反向證偽 + 同源已斃**。不建議 REWORK(非參數問題，是訊號本身在此 universe 無 alpha)。登錄 do-not-revisit，與反轉族並列。

## 7. 多重比較登錄(ledger N)
本 session 12+ 格(順勢/反轉 × hold 1/5/10 × 全體/流動性閘)。最佳格(反轉 h10 +0.44)deflate 後不顯著且尾部集中。

## 結論
taker-flow imbalance 維度**順勢與反轉兩個方向都無可收割 alpha**:順勢方向被資料反向證偽，反轉方向只是已死的 SIM-011/012 微結構死法換皮。clip + sign 一致性 + 流動性閘三道設計皆無法把毛利推過成本。封存，taker-flow 持續性/順勢包裝一併進 do-not-revisit。
