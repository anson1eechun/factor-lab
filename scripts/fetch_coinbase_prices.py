#!/usr/bin/env python3
"""抓 Coinbase Exchange 日線(公開 API,免 key),對齊 universe_1d.pkl 的幣清單,
供跨交易所溢價因子(SIM-2026-07-03-001 FSIM_XVENUE_PREM_GAP)用。
確定性:固定幣序、固定 alias 表、穩定去重;產出 QC json + pkl sha256。
跑: uv run --with "numpy>=2" --with pandas python scripts/fetch_coinbase_prices.py
"""
import urllib.request, urllib.error, json, time, pickle, hashlib, datetime as dt
import pandas as pd

ER = "/home/anson/factor-lab/empirical_runs/"
OUT_PKL = ER + "coinbase_1d.pkl"
OUT_QC = ER + "coinbase_1d_qc.json"
START = "2023-01-01T00:00:00Z"          # universe_1d 起點 ~2023-02-23,提早抓給 120d 基準暖機
GRAN = 86400
# 更名 alias(1:1 換轉):主 product 在前,重疊日以前者優先
ALIASES = {"POL": ["POL-USD", "MATIC-USD"], "MATIC": ["MATIC-USD"],
           "RENDER": ["RENDER-USD", "RNDR-USD"], "FTM": ["FTM-USD"], "S": ["S-USD"]}


def get(url, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "factor-lab/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=25))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def fetch_product(pid, start_iso):
    """分頁抓一個 product 全史日 K → DataFrame(timestamp ms/open/high/low/close/volume)。"""
    start = dt.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end = dt.datetime.now(dt.timezone.utc)
    rows = []
    cur_end = end
    while cur_end > start:
        cur_start = max(start, cur_end - dt.timedelta(days=299))
        url = (f"https://api.exchange.coinbase.com/products/{pid}/candles"
               f"?granularity={GRAN}&start={cur_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
               f"&end={cur_end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        data = get(url)
        if data is None:                      # 404 = product 不存在
            return None
        rows += data
        cur_end = cur_start - dt.timedelta(seconds=1)
        time.sleep(0.15)
    if not rows:
        return None
    # candle 格式 [time_s, low, high, open, close, volume];去重(穩定)+升冪
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates(subset="time", keep="first")
    df = df.sort_values("time", kind="mergesort").reset_index(drop=True)
    df["timestamp"] = df["time"].astype("int64") * 1000
    return df[["timestamp", "open", "high", "low", "close", "volume"]].astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float})


def main():
    uni = pickle.load(open(ER + "universe_1d.pkl", "rb"))
    coins = sorted(uni.keys())                # 固定序
    out, qc = {}, {"fetched_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "start": START, "mapping": {}, "excluded": [], "per_coin": {}}
    for c in coins:
        pids = ALIASES.get(c, [f"{c}-USD"])
        parts, used = [], []
        for pid in pids:
            df = fetch_product(pid, START)
            if df is not None and len(df) >= 60:
                parts.append(df); used.append(pid)
        if not parts:
            qc["excluded"].append(c)
            print(f"[skip] {c}: no coinbase product with >=60d", flush=True)
            continue
        # 重疊日以先列 product 優先(穩定 keep='first')
        merged = pd.concat(parts, ignore_index=True)
        merged = merged.drop_duplicates(subset="timestamp", keep="first")
        merged = merged.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        out[c] = merged
        span = (pd.to_datetime(merged["timestamp"].iloc[0], unit="ms").date().isoformat(),
                pd.to_datetime(merged["timestamp"].iloc[-1], unit="ms").date().isoformat())
        expected = (merged["timestamp"].iloc[-1] - merged["timestamp"].iloc[0]) // 86400000 + 1
        qc["mapping"][c] = used
        qc["per_coin"][c] = {"n": int(len(merged)), "first": span[0], "last": span[1],
                             "missing_days": int(expected - len(merged))}
        print(f"[ok] {c}: {used} n={len(merged)} {span[0]}→{span[1]} miss={expected-len(merged)}", flush=True)
    with open(OUT_PKL, "wb") as f:
        pickle.dump(out, f)
    qc["n_coins"] = len(out)
    qc["pkl_sha256"] = hashlib.sha256(open(OUT_PKL, "rb").read()).hexdigest()
    with open(OUT_QC, "w") as f:
        json.dump(qc, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(json.dumps({"n_coins": len(out), "excluded": qc["excluded"],
                      "sha256": qc["pkl_sha256"][:16]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
