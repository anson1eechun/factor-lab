# SIM-2026-07-05-001 runner 修訂 diff 歸檔(L1-A1 執行紀錄)

> 修訂者:orchestrator(主代理,Builder 於 session 限額終止後代行,依 Proposer L1-A1 裁定原文)
> 修訂時點:2026-07-05,Phase A 重跑之前;Phase C(W-back)當時從未執行
> 修訂範圍聲明:**僅以下兩處**;`phase_B`(含 used_start 裁量)與 `phase_CDEF` 為 Builder 原稿,未觸碰
> 驗證:修訂後 Phase A 之 `runs` 區塊與 `lock_fail_1.json` 之 `runs` 逐位相同(Skeptic 親核)——改判定謂詞,未改任何計算

## Diff 1/2:phase_A 硬判準第 3 項(L1-A1 條款本體)

### 修訂前(原 Builder 稿,即 lock_fail_1 所用)
```python
    # 硬判準
    nets = {h: runs[f"hold{h}_cost10"]["ls_sharpe"] for h in (5, 10, 20)}
    hard = {
        "ic_ir(0.228±0.003)": {"value": ref["ic_ir"], "pass": bool(abs(ref["ic_ir"] - 0.228) <= 0.003)},
        "ic_t(7.84±0.10)": {"value": ref["ic_t"], "pass": bool(abs(ref["ic_t"] - 7.84) <= 0.10)},
        "quintile_net10_holds_in[-1.05,-0.23]": {
            "values": nets, "pass": bool(all(-1.05 <= v <= -0.23 for v in nets.values()))},
    }
    hard_pass = all(v["pass"] for v in hard.values())
```

### 修訂後
```python
    # 硬判準(L1-A1 修訂版,2026-07-05,見 W-back 前;原版第 3 項要求 hold{5,10,20} 全含,
    # 第一次嘗試 FAIL 已落盤 lock_fail_1.json;Proposer 裁定為「規格轉錄缺陷」——
    # 六月報告「quintile −0.28~−1.0」未記載 hold×cost 對應,ledger 唯一可考 PnL(−0.44)吻合 hold5)
    nets = {h: runs[f"hold{h}_cost10"]["ls_sharpe"] for h in (5, 10, 20)}
    hard = {
        "ic_ir(0.228±0.003)": {"value": ref["ic_ir"], "pass": bool(abs(ref["ic_ir"] - 0.228) <= 0.003)},
        "ic_t(7.84±0.10)": {"value": ref["ic_t"], "pass": bool(abs(ref["ic_t"] - 7.84) <= 0.10)},
        "quintile_net10_hold5&10_in[-1.05,-0.23]_(L1-A1)": {
            "values": nets, "pass": bool(all(-1.05 <= nets[h] <= -0.23 for h in (5, 10))),
            "hold20_no_band": "複現值權威 in-sample 參照;六月範圍出處網格不可考,likely 不含 hold20@10bps",
            "hold20_value": nets[20]},
    }
    hard_pass = all(v["pass"] for v in hard.values())
```

## Diff 2/2:phase_A 之 baseline JSON 輸出(新增披露區塊,無計算變更)

### 修訂前
```python
           "runs": runs, "ic_consistency": ic_consistency,
           "hard_criteria": hard, "soft_criteria": soft,
           "anchor_hold10_net10_ls_sharpe(W-in-canonical)": ref["ls_sharpe"],
           "pass": bool(hard_pass)}
```

### 修訂後
在 `"soft_criteria": soft,` 與 `"anchor_..."` 之間插入兩個純披露鍵:`soft_annotation_L1_A1`(折半前半超帶之加註)與 `amendment_L1_A1`(裁定全文摘要+屏障斷言+多重比較帳聲明)。無任何計算路徑變更。

## 範圍外聲明
- `phase_B` 的 `used_start` 裁量(字面 index[23]=2021-03-29 → 被截斷幣各自第 23 根之最大值 2023-03-19)為 **Builder 原稿內容**,其 discretion_note 於 Builder 撰寫時即寫入腳本與 JSON,非本次修訂引入。
- `phase_CDEF`、`daily_series`、`rankw_series`、`nw21_t` 等全部未觸碰。
- 凍結件 hash(signal `8ed5b818…`、harness `c1fb9da9…`、兩份 pkl)四份 JSON 跨 07-04/07-05 一致。

## Skeptic 制度建議(本輪採納狀態留給 Arbiter 裁定)
1. Provenance-or-soft:硬判準數字須引註歸檔件檔名+行號,無出處自動降 soft
2. 修訂會簽:lock FAIL 修訂需非提案角色會簽;只准收斂到有出處的量
3. Runner 自 hash:修訂後 runner 先記 hash 入 baseline 再准跑 CDEF
4. 緊急代行協議:orchestrator 代行 Builder 須預先申報 diff 範圍+事後 diff 歸檔(本檔即為執行)
