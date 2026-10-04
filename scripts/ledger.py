#!/usr/bin/env python3
"""ledger.py — search ledger 的唯一讀寫入口。

舊列(schema 1)不改寫,讀取時以 empirical_runs/ledger_families.json 推斷 family/kind;
新列(schema 2)由 append() 驗證後寫入,欄位固定,不得自創鍵。

  python scripts/ledger.py n --family xs.lottery [--t-years 5.5]   # Arbiter 用:N / Bonferroni / DSR
  python scripts/ledger.py closed [--family xs.funding]            # Proposer 用:封線與通道狀態(精簡)
  python scripts/ledger.py families                                 # 各家族試驗數
  python scripts/ledger.py show --family xs.venue_share             # 單家族精簡表
"""
import sys, os, re, json, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import labkit as K

ER = "/home/anson/factor-lab/empirical_runs/"
LEDGER = os.environ.get("FACTORLAB_LEDGER", ER + "search_ledger.jsonl")
FAMILIES = ER + "ledger_families.json"

KINDS = {"trial", "lock_fail", "diag", "gate", "risk", "status", "closure", "defect", "void", "correction"}
VERDICTS = {"PENDING", "KILL_STAGE0", "REJECT", "REWORK", "VALIDATE", "DISCLOSURE", "DIAG", "FAIL", "CLOSE"}
REQUIRED = ["date", "session", "family", "kind", "factor", "module", "type", "asset", "tf", "params", "verdict"]
METRICS = ["gross_sharpe", "net_sharpe", "net_nw_t", "rank_ic", "ic_ir", "ic_nw_t", "t_nonoverlap",
           "excess_vs_benchmark", "max_drawdown", "turn_mean", "T_years", "mono"]
OPTIONAL = METRICS + ["note", "stage", "preregistered", "supersedes"]


def _rules():
    return json.load(open(FAMILIES))


def _match(rule, row):
    for key in ("session", "factor"):
        if key in rule and not re.search(rule[key], str(row.get(key, ""))):
            return False
    return True


def classify(row, rules=None):
    """回傳 (family, kind)。schema 2 列直接取欄位。"""
    if row.get("schema") == 2:
        return row["family"], row["kind"]
    rules = rules or _rules()
    fam = next((r["family"] for r in rules["rules"] if _match(r, row)), None)
    if fam is None:
        fam = "legacy." + re.sub(r"(-rw|-rework|-RW|-OOS|-u80|b)$", "", str(row.get("session", "?")))
    kind = next((r["kind"] for r in rules["kinds"] if _match(r, row)), "trial")
    return fam, kind


def load():
    rules = _rules()
    rows = []
    for i, l in enumerate(open(LEDGER)):
        if not l.strip():
            continue
        r = json.loads(l)
        r["_line"] = i + 1
        r["_family"], r["_kind"] = classify(r, rules)
        rows.append(r)
    return rows


def append(rows):
    """驗證後 append。任何未知鍵、缺欄、非法 kind/verdict 一律拒寫(整批不寫)。"""
    out = validate(rows)
    with open(LEDGER, "a") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(out)


def validate(rows):
    out = []
    for r in rows:
        r = dict(r)
        r.setdefault("date", datetime.date.today().isoformat())
        missing = [k for k in REQUIRED if r.get(k) in (None, "")]
        unknown = [k for k in r if k not in REQUIRED + OPTIONAL]
        if missing or unknown:
            raise ValueError(f"ledger 拒寫 {r.get('factor')}: 缺 {missing} / 未知鍵 {unknown}")
        if r["kind"] not in KINDS or r["verdict"] not in VERDICTS:
            raise ValueError(f"ledger 拒寫 {r['factor']}: kind={r['kind']} verdict={r['verdict']}")
        if len(str(r.get("note", ""))) > 200:
            raise ValueError(f"ledger 拒寫 {r['factor']}: note 超過 200 字,長文放報告")
        out.append({"schema": 2, **K.sanitize(r)})
    return out


def counted(rows):
    """回傳計入家族 N 的列。schema 2 列另外排除:
    verdict DIAG(凍結規格上的揭露診斷,永不得升格為線索或候選);
    同 session+family 已有預註冊主規格時的 stage0 篩檢列(同一假設,不重複計);
    同 session 內 factor+params 相同的重跑 trial(只計第一筆)。lock_fail 每次都計。"""
    cnt = set(_rules()["count_toward_n"])
    prereg = {(r["session"], r["_family"]) for r in rows if r.get("preregistered")}
    out, seen = [], set()
    for r in rows:
        if r["_kind"] not in cnt:
            continue
        if r.get("schema") == 2:
            if r.get("verdict") == "DIAG" or (r.get("stage") == "stage0" and (r["session"], r["_family"]) in prereg):
                continue
            if r["_kind"] == "trial":
                key = (r["session"], r["_family"], r["factor"], json.dumps(r.get("params"), sort_keys=True))
                if key in seen:
                    continue
                seen.add(key)
        out.append(r)
    return out


def family_n(family, rows=None):
    rows = rows or load()
    fam = [r for r in rows if r["_family"] == family]
    return len(counted(fam)), fam


def cmd_n(a):
    n, fam = family_n(a.family)
    out = {"family": a.family, "N_trials": n, "rows_total": len(fam),
           "bonferroni_t_crit": round(K.bonferroni_t(n), 3)}
    if a.plus:
        out["N_with_planned"] = n + a.plus
        out["bonferroni_t_crit_with_planned"] = round(K.bonferroni_t(n + a.plus), 3)
    if a.t_years:
        nn = n + (a.plus or 0)
        out["T_years"] = a.t_years
        out["dsr_expected_max_sharpe"] = round(K.dsr_threshold(nn, a.t_years), 3)
    print(json.dumps(out, ensure_ascii=False))


def cmd_families(a):
    rows = load()
    cnt = {r["_line"] for r in counted(rows)}
    agg = {}
    for r in rows:
        f = agg.setdefault(r["_family"], {"trials": 0, "rows": 0, "last": ""})
        f["rows"] += 1
        f["trials"] += r["_line"] in cnt
        f["last"] = max(f["last"], str(r.get("date", "")))
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["trials"]):
        print(f"{k:28s} trials={v['trials']:3d} rows={v['rows']:3d} last={v['last']}")


def _short(r, w=110):
    s = str(r.get("factor", ""))
    v = str(r.get("verdict", ""))
    return f"[{r['_family']}] {s[:60]} → {v[:w]}"


def cmd_closed(a):
    for r in load():
        if r["_kind"] in ("status", "closure") and (not a.family or r["_family"] == a.family):
            print(_short(r, a.width))


def cmd_show(a):
    keys = ["net_sharpe", "net_nw_t", "rank_ic", "ic_nw_t", "t_nonoverlap", "ic_ir"]
    for r in load():
        if r["_family"] != a.family:
            continue
        m = " ".join(f"{k}={r[k]:.3g}" for k in keys if isinstance(r.get(k), (int, float)))
        print(f"L{r['_line']:<4d} {r['_kind']:10s} {str(r.get('factor'))[:55]:55s} {m}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("n"); p.add_argument("--family", required=True)
    p.add_argument("--t-years", type=float); p.add_argument("--plus", type=int, default=0,
                                                            help="本輪預註冊計畫中、尚未落盤的試驗數")
    sp.add_parser("families")
    p = sp.add_parser("closed"); p.add_argument("--family"); p.add_argument("--width", type=int, default=110)
    p = sp.add_parser("show"); p.add_argument("--family", required=True)
    a = ap.parse_args()
    {"n": cmd_n, "families": cmd_families, "closed": cmd_closed, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
