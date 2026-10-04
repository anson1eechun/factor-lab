# EQ-SIM-2026-06-10-006 — Small-Cap Value 跨 universe OOS(Russell 2000 ex-S&P1500)

**裁決:REJECT(跨 universe OOS 未過)+ ★重大方法論發現:v1 基本面管線不可重現,
EQ_SmallCap_Value 的 validated 數字是資料處理 artifact → 降級 REWORK。**

## 0. 預登錄(跑前已對齊,未搬龍門)
- 假設(confirmatory、方向預定):行業中性 value(E/P+B/P+S/P)在 R2000 扣除 S&P1500 的獨立池(1,286 檔)仍是「便宜>貴」。
- PASS 須同時:① IC_t≥2 同向 ② 季頻淨LS(25bps/邊)>0 且多頭超額>0 ③ 剔最高5%月仍正 ④ IS/OOS 兩半同向 ⑤ 十分位 Spearman>0。
- FAIL → validated 筆記降級。harness 照搬 eq_universe_retest/eq_value_refine 邏輯,不調參數。

## 1. Builder:資料與管線
- universe:Vanguard VTWO(R2000 proxy,1,935 檔)→ 剔除 S&P1500 → SEC CIK 對映 1,286 檔,SIC→sector 桶,tier=`r2k_ex`(`build_universe_r2k.py`)。
- 增量抓 SEC companyfacts(1,286 檔)+ Yahoo 月線(1,261 檔,2014-07→2026-06)。
- harness:`eq_r2k_oos.py`,同跑 tier=small 作為對照(應重現 validated 數字)。

## 2. ★Empiricist 中途發現:對照組無法重現 → 追根 → v1 管線 bug
對照組 small 跑出 IC_t 3.06 / 季頻淨LS 0.63,**遠低於 validated 記錄的 3.85 / 1.70**。
原版 `eq_value_refine.py` 今日重跑同樣只有 0.63 → 不是新 harness 的問題。隔離測試定位根因:

**v1 管線的 PIT 選列是「任意」的。** 同一筆 10-K 申報(同 ticker+filed)內含本期年度值+
前期比較值+季度值——`sec_facts` 沒存 `start`(期間起日),無法分辨;NetIncomeLoss **99% 的申報
含多個相異值(中位 3 個),其中真年度期間僅 46%**。v1 的 `merge_asof` 靠 `sort_values("filed")`
(**不穩定 quicksort**)的平手順序「隨機」取一個值 → 加入 1,286 個無關 ticker 後,small 池自身的
IC_t 從 3.85 變 3.06(資料未變、僅排序擾動)。**結果不可重現 = 不可採信。**

修法:全量重抓含 `start`(`fetch_sec_fundamentals_v2.py` → `sec_facts_v2.parquet`,舊檔保留供取證);
年度 flow 取期間 300–400 天、每 (ticker,filed) 取最新 end,全程穩定排序。連跑兩次逐位相同 ✓。

## 3. 修正後結果(v2 資料,143 月,25bps/邊,季頻)
| 池 | 覆蓋 | IC_t① | 十分位Sp⑤ | 淨LS② | 多頭超額② | 剔5%③ | IS/OOS④ | 近36m |
|---|---|---|---|---|---|---|---|---|
| small(對照=原validated池) | 319 | **1.01** | +0.26 | **−0.04** | +0.17 | **−0.55** | −0.82/+0.77 | +0.63 |
| r2k_ex(OOS池) | 579 | 5.93 | **−0.07(U型)** | **−0.36** | +0.26 | **−0.78** | **−0.02/−0.61** | −1.07 |

- r2k_ex 預登錄五關:①過(5.93)、**②③④⑤全敗** → **REJECT**。
- IC_t 5.93 但 LS 為負、十分位 U 型(最貴 D1 +2.27 與最便宜 D10 +2.04 兩端都高)= **IC-IR 與 PnL 脫鉤**(SIM-015 同款海市蜃樓);成分:bp IC_t 7.65 / sp 4.56 / ep 0.65,但無一轉成可交易 LS。
- **對照組 small 在正確資料上也崩**:IC_t 1.01、淨LS −0.04、剔5% −0.55 → validated 的數字無法在
  修正管線上重現。v1 的 3.85/1.70 來自「任意混入季度/前期值」的 artifact 組合 + 不穩定排序的偶然。

## 4. Skeptic / Risk 補充
- 為何 artifact 能「跨 IS/OOS、十分位單調、剔5%」全過?因為 v1 的任意選列在**固定資料快照下是
  確定性的**——它等於定義了一個「混合期間 E/P」的別種因子,所有 OOS 檢驗都在同一條被污染的
  訊號上自我一致。**七道規格防得住統計僥倖,防不住管線級 bug**;唯一能抓到它的是「重現性檢驗」
  (加無關資料/換排序,數字就變)。
- 本池 survivorship bias(VTWO 僅當前成分)依然存在,但兩池同款限制,不影響「對照組崩潰」的結論。
- 未測殘留路徑:乾淨的 **TTM/季度 E/P**(v2 資料已支援 start,可分辨季度)是「v1 偶然混入季度值
  或許捕捉到盈餘新近性」的正式檢驗——屬新假設,須另行預登錄。

## 5. Arbiter 裁決
1. **跨 universe OOS:REJECT**(預登錄 5 關敗 4)。
2. **EQ_SmallCap_Value:validated → REWORK 降級**,筆記移 candidates/。理由:對照組在修正後
   資料上 IC_t 1.01/LS −0.04,原 validated 數字是 PIT 選列 artifact;「small-cap value」作為構念
   未被全面否證(bp/sp 在 r2k_ex 有強 IC),但**原宣稱(Sharpe 1.7、過七關)作廢**。
3. **方法論新增規格(第 9 條):重現性檢驗**——任何結果須在「加入無關資料 / 改變排序」下不變;
   管線一律穩定排序 + 確定性選列;基本面 flow 必須帶 start 分辨期間。

## 6. 歸檔
- ledger +2(OOS 假設 REJECT;EQ_SCV 降級 supersedes EQ-SIM-004)
- `sec_facts_v2.parquet` 為新標準資料(v1 保留取證);harness `eq_r2k_oos.py`
- index.db:debate_sessions/rounds/transcripts(EQ-SIM-2026-06-10-006)
- `validated/EQ_SmallCap_Value.md` → `candidates/EQ_SmallCap_Value_REWORK.md`(加降級前言)
