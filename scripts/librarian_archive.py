#!/usr/bin/env python3
"""Librarian archival script for e2e-test-20260526."""
import sqlite3
import datetime
import hashlib

ROOT = "/home/anson/factor-lab"
DB = f"{ROOT}/index.db"
NOW = datetime.datetime.now().isoformat(timespec="seconds")

def _fingerprint(name, formula=""):
    return hashlib.sha1(f"{name.strip().lower()}|{formula.strip()}".encode()).hexdigest()[:16]

conn = sqlite3.connect(DB)

# === 1. debate_sessions ===
conn.execute("""
  INSERT OR REPLACE INTO debate_sessions
  (session_id, title, num_factors_proposed, num_factors_validated,
   num_factors_deprecated, total_duration_seconds, started_at, completed_at, notes)
  VALUES (?,?,?,?,?,?,?,?,?)
""", (
  "e2e-test-20260526",
  "Phase 2 E2E: F4-F6 因子辯論",
  3, 2, 1, 1500.0,
  "2026-05-26T00:00:00", "2026-05-26T00:25:00",
  "F4條件驗證(flow), F5驗證通過(value, IC-IR=1.003), F6淘汰(經濟邏輯反轉)"
))
print("[1/6] debate_sessions: done")

# === 2. debate_transcripts ===
steps = [
  (1, "proposer", "F4,F5,F6",
   "基於42條論文洞見與phase2-e2e教訓，提出3個新因子候選。",
   "提出F4(Flow Divergence Ratio), F5(Anchored Mean-Reversion Score), F6(Return Asymmetry Premium)。",
   66.0, "deepseek-v4-pro"),
  (2, "builder", "F4,F5,F6",
   "為F4/F5/F6撰寫Python信號函數，寫入core/signals/。",
   "三個信號全部實現並通過smoke test，輸出範圍正確，無NaN。",
   46.0, "deepseek-v4-pro"),
  (3, "skeptic", "F4,F5,F6",
   "對F4/F5/F6執行五維批判(data-mining/economic/lookahead/duplication/cost)。",
   "F4: z-score自包含偏誤。F5: Wilder ATR用SMA非正確平滑。F6: 經濟邏輯反轉(SK-F6-05)致命。",
   35.0, "deepseek-v4-pro"),
  (4, "empiricist", "F4,F5,F6",
   "Binance BTCUSDT日線500根，N=1/5/10/20日實證。",
   "F4 IC-IR=0.676(N=5), F5 IC-IR=1.003(N=1), F6 IC-IR=0.309(N=1)方向反轉。12列evidence已寫入。",
   322.0, "deepseek-v4-pro"),
  (5, "arbiter", "F4,F5,F6",
   "整合全部輸出做出最終仲裁裁決。",
   "F4條件驗證(需修復z-score+成本+反轉), F5驗證通過(需修復ATR+成本+反轉), F6淘汰(三致命缺陷)。",
   0.0, "human (anson via deepseek-v4-pro)"),
  (6, "librarian", "F4,F5,F6",
   "執行裁決後完整歸檔：vault歸位/去重/註冊/wikilinks/MOC更新。",
   "F5->validated/, F4->validated/(conditional), F6->deprecated/。去重通過。雙向wikilinks建立。MOC更新。",
   300.0, "deepseek-v4-pro"),
]
sql_t = (
  "INSERT INTO debate_transcripts"
  " (session_id,step_order,agent_role,factor_refs,input_context,output_summary,"
  "  duration_seconds,model,created_at)"
  " VALUES (?,?,?,?,?,?,?,?,?)"
)
for s in steps:
  conn.execute(sql_t, ("e2e-test-20260526",) + s + (NOW,))
print(f"[2/6] debate_transcripts: {len(steps)} rows")

# === 3. debate_rounds ===
rounds_data = [
  ("e2e-test-20260526", 7, "arbiter", "flow_divergence_ratio",
   "FDR=EMA(price_mom_z*vol_mom_z, halflife=10); signal=-FDR",
   "flow",
   "價量協同衰減捕捉趨勢衰竭：價格持續走高但成交量退潮->趨勢即將擱淺。",
   None, 0.676, None, None,
   "conditionally_validated",
   "IC-IR=0.676(N=5)通過門檻。4個horizon方向一致(+)。Q5-Q1全為負->需反轉。vs F1/F2極低相關。",
   NOW),
  ("e2e-test-20260526", 7, "arbiter", "anchored_mean_reversion_score",
   "AMRS=EMA((vwap_20-close)/ATR_14, halflife=5); signal=-AMRS",
   "value",
   "VWAP錨定均值回歸：價格偏離成交量加權平均成本時產生回歸壓力。",
   None, 1.003, None, None,
   "validated",
   "IC-IR=1.003(N=1)全部因子最強。4個horizon方向一致(+)。vs F1/F2極低相關。必修：Wilder ATR+成本模型。",
   NOW),
  ("e2e-test-20260526", 7, "arbiter", "return_asymmetry_premium",
   "RAP=EMA(clip(skew_20*vol_annualized,-3,3), halflife=5)",
   "behavioral",
   "偏態溢酬：正偏態應低報酬/負偏態應高報酬。基於前景理論。",
   None, 0.309, None, None,
   "rejected",
   "三致命缺陷：(1)經濟邏輯反轉;(2)統計不可靠-n=20偏態SE~0.55;(3)多horizon方向反轉。復活條件：信號反轉+窗口40-60日+idiosyncratic分解。",
   NOW),
]
sql_r = (
  "INSERT INTO debate_rounds"
  " (session_id,round_num,agent_role,factor_name,factor_formula,factor_category,"
  "  hypothesis,ic_mean,ic_ir,sharpe,max_drawdown,decision,decision_reason,created_at)"
  " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
for r in rounds_data:
  conn.execute(sql_r, r)
print(f"[3/6] debate_rounds: {len(rounds_data)} rows")

# === 4. factor_registry ===
factors_reg = [
  ("flow_divergence_ratio",
   "FDR=EMA(price_mom_z*vol_mom_z, halflife=10); signal=-FDR",
   "flow", "active",
   "10-因子库/validated/flow_divergence_ratio.md",
   0.676, None),
  ("anchored_mean_reversion_score",
   "AMRS=EMA((vwap_20-close)/ATR_14, halflife=5); signal=-AMRS",
   "value", "active",
   "10-因子库/validated/anchored_mean_reversion_score.md",
   1.003, None),
]
for name, formula, cat, status, note_path, ic_ir, sharpe in factors_reg:
  fp = _fingerprint(name, formula)
  existing = conn.execute(
    "SELECT id FROM factor_registry WHERE fingerprint=?", (fp,)
  ).fetchone()
  if existing:
    conn.execute(
      "UPDATE factor_registry SET last_evaluated=?, best_ic_ir=?, status=?, total_rounds=total_rounds+1 WHERE id=?",
      (NOW, ic_ir, status, existing[0]))
    print(f"  factor_registry UPDATE: {name}")
  else:
    conn.execute(
      "INSERT INTO factor_registry"
      " (name,formula,category,status,first_proposed,last_evaluated,"
      "  best_ic_mean,best_ic_ir,best_sharpe,total_rounds,note_path,fingerprint,created_at)"
      " VALUES (?,?,?,?,?,?,NULL,?,NULL,1,?,?,?)",
      (name, formula, cat, status, NOW, NOW, ic_ir, note_path, fp, NOW))
    print(f"  factor_registry INSERT: {name}")
print("[4/6] factor_registry: F4+F5 registered")

# === 5. factors table ===
factors_tbl = [
  ("flow_divergence_ratio", "Flow Divergence Ratio (FDR)", "flow", "active", 1,
   "10-因子库/validated/flow_divergence_ratio.md"),
  ("anchored_mean_reversion_score", "Anchored Mean-Reversion Score (AMRS)", "value", "active", 1,
   "10-因子库/validated/anchored_mean_reversion_score.md"),
  ("return_asymmetry_premium", "Return Asymmetry Premium (RAP)", "behavioral", "deprecated", 1,
   "10-因子库/deprecated/return_asymmetry_premium.md"),
]
for fid, name, cat, status, ver, note_path in factors_tbl:
  existing = conn.execute("SELECT id FROM factors WHERE id=?", (fid,)).fetchone()
  if existing:
    conn.execute("UPDATE factors SET name=?,category=?,status=?,version=?,note_path=? WHERE id=?",
                 (name, cat, status, ver, note_path, fid))
    print(f"  factors UPDATE: {fid}")
  else:
    conn.execute("INSERT INTO factors (id,name,category,status,version,note_path,created) VALUES (?,?,?,?,?,?,?)",
                 (fid, name, cat, status, ver, note_path, NOW))
    print(f"  factors INSERT: {fid}")
print("[5/6] factors table: F4+F5+F6 done")

conn.commit()
conn.close()
print("[6/6] All database writes complete.")
