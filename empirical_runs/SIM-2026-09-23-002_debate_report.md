---
kind: 辯論模擬
session: SIM-2026-09-23-002
verdict: REJECT
type: cross
family: xs.anchoring
flow: v3(Stage 0 KILL)
---

# SIM-2026-09-23-002 — FSIM_Anchor_High_Proximity(距 180 日高點錨定)

> **判決:REJECT**(Stage 0 機械 KILL,零自由度)。依 v3 流程不召喚 Skeptic / Arbiter。
> 預註冊 [[SIM-2026-09-23-002_prereg]] · spec `SIM-2026-09-23-002_spec.json` · Stage 0 `SIM-2026-09-23-002_stage0.json`

## 流程
Proposer(子代理)→ Builder(子代理,恆等式誤差 4.4e-16)→ **Stage 0 KILL** → 主代理獨立複驗 → 歸檔。
v3 首次實戰;未進入 lock / run,未消耗 Skeptic / Arbiter。

## 假設
George–Hwang 52 週高點效應的 crypto 版:以近期高點為錨,逼近前高者反應不足 → 越接近 180 日高點,後續報酬越高。
`SIG = log(C_t/Hmax_180) = ret_L − runup_L`,宣告 `ret_L` +1、`runup_L` −1,方向 +1,hold 5,10bps,含 funding。

## Stage 0 結果(80 幣 universe_1d,2264 日)
| 項目 | rank IC | NW t | 宣告 | 判定 |
|---|---|---|---|---|
| 主訊號 SIG | +0.0129 | +2.60 | +1 | 篩檢會過(t≥1) |
| 成分 ret_L(180 日報酬) | **−0.0117** | **−2.40** | +1 | **反號 → 敘事不成立** |
| 成分 runup_L(路徑峰值漲幅) | −0.0249 | −6.21 | −1 | 同號 |

lint 通過、截斷 40 天重算逐格一致(無前視)。

控制變數自身 IC(預註冊階段即落地):mom20 −0.0236(t −5.12)、sig20 −0.0629(t −13.4)、max21 −0.0529(t −13.4)、
ladv20 +0.0015(t 0.38)。前三者皆比候選強且反號 → **v2.4 §4 不適格**,殘差化檢定(K2)在此宇宙結構上作廢。

## 主代理獨立複驗
不經 pack,以 pandas 逐日 rank 相關重算:SIG +0.0129、ret_L −0.0117、runup_L −0.0249,樣本天數一致(2264/2263)。

## 解讀
1. 錨定敘事要求「中期報酬延續」,但 crypto 橫截面 180 日報酬是**顯著反轉**(t −2.40)。
2. 主訊號的 +0.0129 全部來自 **−runup_L**:過去 180 日曾大漲到高峰的幣後續較弱 —— 這是長窗的彩券/MAX 特徵,
   與已封線的 `xs.lottery`(MAX21 IC −0.053)同源。名目上主訊號 t=2.60 看似可做,拆成分後是彩券族換皮。
3. 這正是 v2.4 教訓「複合訊號最常見的死法是成分反號」的第 3 例,且 v3 在 9 秒內攔下(v2.4 流程會跑完整一輪才發現)。

## 對流程的觀察
- 控制變數 mom20/sig20/max21 在 crypto 80 幣宇宙中 IC 量級(0.02–0.06)普遍大於新候選,且皆為負;
  今後任何 IC 為正、量級 <0.02 的 crypto XS 候選,這三個殘差化檢定都會自動作廢。Proposer 提案時應預期此事。
- 操作失誤(已更正):第一次跑 Stage 0 時殘留測試環境變數,輸出寫到 `/tmp` 測試副本;只印判決、未印數字,
  清變數後重跑,真實 ledger 只有一列 stage0 紀錄。

## 產出
`SIM-2026-09-23-002_prereg.md` · `_spec.json` · `_stage0.json` · `core/signals/FSIM_Anchor_High_Proximity.py` ·
ledger +1(stage0)+ 歸檔列 · index.db(備份 `index.db.bak-SIM-2026-09-23-002`)
