# SIM-2026-07-05-001 — MAX-aversion 2019-11~2022 backward-OOS 終局診斷 辯論報告

> kind: 辯論模擬(終局診斷輪) · 裁決:**REJECT-終局封存(矩陣格 IC-CONFIRM×PnL-NEG=教科書終局)** · lottery 家族關線(5/5)
> 設計:零訊號自由度 backward-OOS——凍結 MAX21 訊號(2026-06-08)× 上輪延伸資料(80 幣至 2019-09);雙層判讀+九格矩陣先寫死
> 主規格:W-back quintile hold10@10bps;W-back=[T30=2019-11-05, 2022-12-31],1153 交易日

## 一、七階段摘要

| 階段 | 執行者 | 要點 |
|---|---|---|
| Proposer | 子代理 | 雙層科學問題(Q1 排序層/Q2 美元層);C1/C2 分箱+R1 復活條款(三重 t≥2)+九格矩陣先寫死;檢定力全計算;剔尾申報 disclosure-only(彩券機制尾部即本體);倖存偏差鎖定不可簽名 |
| Builder | 子代理→orchestrator 代行 | Builder 寫完 runner 後被 session 限額終止;L1 鎖第一次 FAIL 落盤(hold20 +0.081 超出由六月報告推斷之帶);**Proposer 裁定 L1-A1**(規格轉錄缺陷,hold5&10 維持帶、hold20 撤帶);orchestrator 依裁定原文代行修改並執行,diff 歸檔 `_runner_amendment_diff.md` |
| Empiricist | 主代理 | L1(修訂後)PASS、L2 完美零差(新舊 pkl 鎖窗 Δ全 0);confirmatory 單次批跑;腳本斷言全過(腿和 gap 5.5e-17、複刻 vs evaluate ≤0.001);2 行入 ledger(lock-FAIL+主行) |
| Risk | 主代理 | book 影響零;翻號(做多彩券籃)已於原 XLOT 輪 REJECT 且 q0+0.69 係倖存灌水,無殘留誘惑 |
| Skeptic | 子代理 | L1-A1 不構成實質 lock-shopping(修訂後 runs 與 FAIL 版逐位相同=改謂詞不改數字,檔案親核);**機制歸因缺口**:MAX 與 vol21 機械共線未分離;C2 措辭邊界;三項 known-unknowns;四條制度建議 |
| Arbiter | 獨立子代理 | **REJECT-終局封存**;C2 依邊界收窄措辭;機制降級全採;程序四理由不損效力;制度建議 4/4 入 v2.3 |
| Librarian | 主代理 | 本報告+deprecated 筆記+index.db+ledger 通道行+低波動族掛鏈+skill v2.3+Obsidian |

## 二、Verdict inputs 與矩陣

| 層 | 門檻 | 實測 | 分箱 |
|---|---|---|---|
| C1 排序層 | CONFIRM: ic_t≥3 且 NW21-t≥2 | **ic_t 7.894 / NW21-t 9.387** | **IC-CONFIRM** |
| C2 美元層 | NEG: ls_t≤0 | ls −0.821 / **ls_t −1.458** | **PnL-NEG** |
| R1 復活 | ic_t≥2 且 NW≥2 且 ls_t≥2 | ls_t −1.458 | **false** |

**矩陣格 IC-CONFIRM×PnL-NEG(預註冊措辭)**:排序層跨 regime 真異象+美元層跨 regime 不可變現=limits-to-arbitrage 完整證據 → REJECT-終局封存。

## 三、關鍵數字(全真實;主代理執行,Skeptic 對檔核數)

**排序層(可簽「真且穩健」)**:W-back IC-IR **0.2325** vs in-sample 0.2285(幾乎相同);**九年 IC 全正**(2019-2026,0.017→0.069);折半 0.152/0.334;T20/T40 敏感度 ic_t 7.71/8.44;LOO 剔 FTM ic_t 只動 0.025。倖存偏差加註:對排序層方向保守。

**美元層(僅可簽「點估負、跨規格一致、無正向收割證據」)**:hold5 **−1.25(t −2.21)**/ hold10 −0.82(t −1.46)/ hold20 −0.38 / rank-w −0.98 / gross −0.72 / exploratory 2485 日 **−0.91(t −2.38)**;MaxDD −93%。「證實虧損」僅得引 hold5 與 exploratory 窗。

**機制指紋**:quintile_fwd = [40.4, 36.8, 21.9, 20.6, 27.5] bps——**q0(高 MAX)均值最高但排序最弱**=肥右尾;剔最好 5% 日 → −3.45、剔最差 5% 日 → +2.01(雙向尾部主導,均 disclosure-only 不得翻案引用);q0 籃−EW +0.69(倖存灌水,禁單獨流通)。

**機制歸因降級(Arbiter 全採)**:機制欄=「**lottery/高波動/高 beta 未分離**」——MAX21 與 vol21 機械共線、無雙排序、無 corr(LS,EW) 披露、六月 IRANGE ic_t −5.78 強於 MAX −5.26。降級不削弱 REJECT(limits-to-arbitrage 是楔形結構定性),但 do-not-revisit 措辭正名+與低波動族雙向掛鏈(家族多重比較計數合併)。

**Known-unknowns(註記級)**:rebalance 相位未測;min_periods=10 上市部分窗 MAX;W_in fillna(0) 退市蒸發。W_in 自然窗 −0.686 vs backup 錨 −0.335:panel 構造差異之量級標定(±0.35),雙 panel 皆負,前提無恙。

## 四、程序記錄(L1-A1 事件鏈)

1. L1 第一次 FAIL 落盤 `lock_fail_1.json`+ledger FAIL 行(v2.2 紀律)
2. Proposer 裁定 L1-A1:六月報告「quintile −0.28~−1.0」未記載 hold×cost 對應=規格轉錄缺陷;四同一性量已確立(ic_ir Δ0.0005/ic_t Δ0.035/hold5 對 ledger Δ0.011/hold10 在帶);漂移假說被 07-04 carry L1 完美重現證偽;修訂對 C1/C2/R1 零影響;hold20 雙向 disclosure-only
3. orchestrator 代行(Builder session 限額終止):修改僅兩處,diff 歸檔;修訂後 runs 與 FAIL 版逐位相同
4. **Arbiter 程序裁定:不損裁決效力**(正交性/逐位同一/無可購物面/溯源完整)

## 五、制度產出(入 skill v2.3,Arbiter 4/4 採納)

1. **provenance-or-soft**:鎖帶數字須繫於凍結工件(hash/出處);報告轉錄推斷之帶一律降 soft
2. **修訂會簽**:鎖修訂須非提案角色會簽;只准收斂到有出處的量
3. **runner 自 hash**:runner 每次輸出記自身 hash;修訂自動留痕
4. **緊急代行協議**:orchestrator 代行 Builder 限「裁定原文逐字+強制 diff 歸檔+事件鏈披露+下一角色收案核驗」

## 六、Do-not-revisit(Arbiter 正名版)

**封印面:以 MAX21 或其單調變換作 crypto XS 直接多空訊號之任何 horizon/加權/成本變體**(禁訊號用法,非變數本身)。與已封存低波動族**雙向掛鏈**:未來 vol/beta/MAX 鄰接提案之家族計數合併兩線。
**解鎖前提**:(a) 含陣亡幣宇宙重建;(b) 借券/資金費率入帳+實際做空管道論證;(c) MAX 作條件變數/overlay 之新假說(附分離負擔:對 vol21/beta 雙排序或正交化)。均須全新家族提案引用本條。

## 七、Ledger 與資產

- Ledger:lock-FAIL 行+主行+通道狀態行;lottery 家族 5/5 關線;crypto XS 0 validated
- 方法資產:`scripts/max_aversion_final_20260705.py`(A/B/CDEF 分相+鎖靜默+NW21-t+腿記帳+LOO 模板);L1-A1 修訂範例(`_runner_amendment_diff.md`)
- 產物:`SIM-2026-07-05-001_{baseline,replication_lock,results,lock_fail_1}.json`
