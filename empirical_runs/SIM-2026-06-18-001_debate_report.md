---
session: SIM-2026-06-18-001
kind: 辯論模擬
factor: FSIM_TCA
type: cross-sectional
verdict: REJECT
date: 2026-06-18
---

# 因子辯論報告 — FSIM_TCA(Tail Co-movement Asymmetry)

**Session** `SIM-2026-06-18-001` · **裁決 REJECT** · 80 幣加密 universe(2023-02~2026-06)
靈感來源:Obsidian 知識庫精讀 **"Crashing Together, Rallying Apart"(arXiv 2606.16840)**。

## 1. Proposer
- **假設**:加密下行尾部相依近乎完全且穩定、上行尾部相依變薄(「一起崩、各自漲」);高 downside-beta 幣應收風險溢酬(Ang-Chen-Xing 2006)。
- **方向**:long 高 TCA、short 低 TCA。
- **類型**:橫截面 quintile 多空。

## 2. Builder
- `core/signals/FSIM_TCA.py`:`tca_series(coin_close, market_ret, window=90, min_side=20)`。
- 90 日窗內依等權市場報酬正負切子樣本算條件 beta,`TCA=β⁻−β⁺`,每側≥20 點,最終 `shift(1)`。
- 防前視:truncation test 證實去掉末日後早期值 byte-identical(max diff 0)。

## 3. Empiricist(主代理親跑,crosssec_eval 同數學)

| 時框 | Rank IC | IC-IR | IC t | LS Sharpe(net 10bps) | LS t | Mono | 非重疊 IC t (n) | regime |
|---|---|---|---|---|---|---|---|---|
| **1d** | -0.0006 | -0.0035 | -0.119 | **-1.234** | -2.198 | **-0.8** | -0.464 (231) | 前半 -0.0207 / 後半 +0.0036(**變號**) |
| **1w** | -0.0052 | -0.031 | -0.344 | +0.599 | 0.933 | 0.6 | 0.349 (25) | 前半暖機無資料 |

- quintile_fwd(1d)= [0.00019, 0.00072, -0.00014, 0.00017, -0.00059] — 非單調鋸齒。
- size 檢查:TCA vs log-dollar-vol 橫截面相關 **-0.245**(偏負,疑反向 size/流動性 proxy)。

## 4. Risk/Portfolio
單獨 net Sharpe -1.234(1d)、IC≈0、regime 變號 → 併入任何 book 邊際 Sharpe ≤0,**無增量價值**;相關性與容量分析已無意義。

## 5. Skeptic
兩 horizon IC 全≈0=純噪音;1d 負 Sharpe 來自尾部結構性負酬非排序資訊;1w +0.599 不顯著(t0.93、n25、暖機吃掉前半、單一 regime)=小樣本運氣;Mono -0.8 是 5 點脆弱統計;crypto 全市場 beta 趨同使 downside-beta 橫截面分散度低;挑 1w 正值有 cherry-pick 風險。傾向 REJECT。

## 6. Arbiter(獨立子代理,未被告知期望)
**REJECT。** 雙閘門全滅(Gate1 IC-IR≥0.3 差兩個數量級、Gate2 Sharpe<1 且 Mono<0.7);|RankIC|、t≥2、Mono 全未達;多重比較 deflation(N≥2 直接變體 + 隱性自由度)直接判死,唯一正值 1w 屬 cherry-pick;邊際貢獻≤0;負 Sharpe 非排序資訊、反向亦不可靠。
**救活最小條件**:對 log-dollar-vol 殘差化後,在全樣本跨≥2 regime 達 Gate1 + Bonferroni×N 後 IC t≥2;否則永久歸檔。

## 7. Librarian
- 報告:本檔。因子筆記:`deprecated/FSIM_TCA.md`。
- ledger:append 1d/1w 兩變體(SIM-2026-06-18-001)。
- index.db:debate_sessions ×1、debate_transcripts ×7、debate_rounds ×1(arbiter,真實數字)。
- factors:`FSIM_TCA` status=deprecated。

## 多重比較登錄(ledger N)
本因子直接變體 N=2(1d、1w)+ 隱性自由度(window=90、min_side=20、quintile=5、等權市場代理)。Arbiter 已據此 deflate。

## 教訓
- 又一個方向被既有教訓命中:**加密 4~80 標的、3 年樣本對需要穩定 t≥2 的因子極不友善**;downside-beta 在全市場 beta 趨同的 crypto 橫截面分散度太低,β⁻−β⁺ 多為估計噪音。
- 論文洞見(尾部不對稱為真)≠ 可交易橫截面 alpha:不對稱是**時間序列/市場層級**現象(整體 ES 被低估),不必然在**個幣橫截面排序**上變現。

---

## REWORK 救援(SIM-2026-06-18-001-RW)— 維持 REJECT,永久歸檔

依 Arbiter 救活條件試「**市值加權市場(成交額 proxy)+ size 中性化**」。資料無流通量,市值以 dollar-volume 加權近似;size 中性化=橫截面對 log 滾動成交額殘差化。

| 變體 | IC-IR | IC t | LS Sharpe(net) | Mono | 非重疊 IC t (n) | regime(IC-IR 前/後) |
|---|---|---|---|---|---|---|
| capw+中性化 1d | -0.0027 | -0.092 | -0.596 | -0.6 | -1.489 (231) | -0.108 / +0.019(變號) |
| capw-raw 1d | -0.0342 | -1.163 | -1.117 | -0.5 | -1.526 (231) | -0.099 / -0.021 |
| capw+中性化 1w | -0.0255 | -0.287 | +0.577 | 0.7 | 0.50 (25) | 暖機吃前半 |
| capw-raw 1w | -0.0557 | -0.627 | +0.564 | 0.7 | 0.374 (25) | 暖機吃前半 |

**獨立 Arbiter 救援裁決:REJECT(終局,do-not-revisit)**
- 救活三條件 (b) Gate1 IC-IR≥0.3、(c) deflate 後 IC t≥2 各差 1~2 個數量級;1w 因暖機無法跨 regime 驗證。
- size 中性化**未解放任何被遮蔽的 alpha**,只把「弱負」磨到「貼 0 的負」→ 更強的 REJECT 證據。
- TCA 家族已試 **6 個直接變體**(等權/capw-raw/capw-中性化 ×1d/1w)+ 多隱性自由度,救活路徑已窮舉。
- **封存**:後續復活須帶全新經濟機制或全新 universe/資料源並重置 ledger,不得再以「調 window/分位/中性化口味」重開(只會膨脹 N)。

**核心教訓(已寫入)**:尾部不對稱是**市場層級**現象;在 crypto 全市場 beta 趨同下,個幣 β⁻−β⁺ 無乾淨橫截面分散,size 中性化也救不回——這是 do-not-revisit 級的乾淨否證。
