#!/usr/bin/env python3
"""paper_trade.py — base coinbase premium 的 forward paper-trade（凍結規格、即時 premium、逐日記錄）。

誠實前提：規格凍結於 strategies/coinbase_premium_base.yaml，**不得再調參**；此後每日訊號才是真 OOS。
premium 即時自算 = Coinbase BTC-USD spot − Binance BTCUSDT spot（符合 factor 定義）。

  run    : 抓即時 premium+BTC，算今日目標部位，記進 paper_trades/...jsonl（同日覆寫）
  status : 用 lag=1 重建 forward 淨值，對照凍結 expectation，並誠實標示「離統計顯著還很遠」

每日固定一個時間跑一次 run。跑:
  uv run --with "numpy>=2" --with pandas --with pyyaml python scripts/paper_trade.py run
  uv run --with "numpy>=2" --with pandas --with pyyaml python scripts/paper_trade.py status
"""
import sys, os, json, math, urllib.request
import datetime as dt
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "strategies" / "coinbase_premium_base.yaml"
LOG = ROOT / "paper_trades" / "coinbase_premium_base.jsonl"
ANN = math.sqrt(365)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "factor-lab/paper-trade"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _live():
    cb = float(_get("https://api.coinbase.com/v2/prices/BTC-USD/spot")["data"]["amount"])
    bn = float(_get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")["price"])
    return cb - bn, cb, bn


def _load_log():
    return [json.loads(x) for x in LOG.read_text().splitlines() if x.strip()] if LOG.exists() else []


def _pnl(rows, cost_bps):
    """lag=1 重建 forward 日淨報酬：今日持倉 = 昨日訊號；扣換手成本。純函數，可測。"""
    rows = sorted(rows, key=lambda r: r["date"])
    net, held_prev = [], 0.0
    for i in range(1, len(rows)):
        held = float(rows[i - 1].get("target_position", 0.0))
        ret = rows[i]["btc_close"] / rows[i - 1]["btc_close"] - 1.0
        net.append(held * ret - abs(held - held_prev) * cost_bps / 1e4)
        held_prev = held
    return net


def run(spec):
    import pandas as pd
    from core.data import load
    from core.signal_models import sign_flow
    today = dt.date.today().isoformat()
    prem, cb, bn = _live()

    rows = [r for r in _load_log() if r["date"] != today]  # 同日覆寫
    rows.append({"date": today, "ts": dt.datetime.now().isoformat(timespec="seconds"),
                 "premium": round(prem, 3), "coinbase_px": cb, "binance_px": bn, "btc_close": bn})

    hist = load(spec["factor"])  # JSON 歷史 premium（到 2026-06-06）
    fwd = pd.Series({pd.Timestamp(r["date"]): r["premium"] for r in rows})
    series = pd.concat([hist[~hist.index.isin(fwd.index)], fwd]).sort_index()
    pos = sign_flow(series, w=int(spec["window"]), direction=int(spec["direction"]))
    rows[-1]["target_position"] = round(float(pos.reindex([pd.Timestamp(today)]).iloc[0]), 4)

    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    print(json.dumps({"date": today, "premium": round(prem, 2), "btc": round(bn, 1),
                      "target_position": rows[-1]["target_position"], "forward_days": len(rows),
                      "note": "明日持倉 = 今日訊號(lag=1)；請每日固定時間跑一次。"}, ensure_ascii=False, indent=2))


def status(spec):
    rows = sorted(_load_log(), key=lambda r: r["date"])
    print(f"# forward paper-trade — {spec['name']}（凍結 {spec['frozen_at']}）")
    if len(rows) < 2:
        print(f"forward 紀錄 {len(rows)} 天（需 ≥2 天才算得出 P&L）。今日目標部位："
              f"{rows[-1]['target_position'] if rows else 'n/a'}")
        return
    net = _pnl(rows, float(spec["cost_bps"]))
    n = len(net)
    mu = sum(net) / n
    sd = (sum((x - mu) ** 2 for x in net) / (n - 1)) ** 0.5 if n > 1 else 0.0
    sharpe = mu / sd * ANN if sd else 0.0
    t = mu / (sd / math.sqrt(n)) if sd else 0.0
    cum = 1.0
    for x in net:
        cum *= (1 + x)
    exp = spec.get("expectation", {})
    s_proj = sharpe if abs(sharpe) > 0.2 else float(exp.get("oos_holdout_sharpe", 0.71))
    days_t2 = int((2 / s_proj) ** 2 * 365) if s_proj else None
    print(f"- forward 天數 {len(rows)}（P&L {n} 天）｜目前目標部位 {rows[-1]['target_position']:+.3f}")
    print(f"- 累計淨報酬 {(cum - 1) * 100:+.2f}%｜年化 Sharpe(暫) {sharpe:+.2f}｜t={t:+.2f}")
    print(f"- 凍結 expectation：OOS Sharpe {exp.get('oos_holdout_sharpe')}、permutation p={exp.get('permutation_p')}")
    print(f"- ⚠ N={n} 太小、目前 Sharpe 無統計意義。把 {s_proj:.2f} 的 Sharpe 證到 t=2 約需 "
          f"**{days_t2} 天(~{days_t2 / 365:.1f} 年)** forward → 早期只看『仍正/未崩/與 expectation 同向』。")


def main():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"run": run, "status": status}.get(cmd, status)(spec)


if __name__ == "__main__":
    main()
