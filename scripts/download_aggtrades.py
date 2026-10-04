"""Download aggTrades one month at a time, extend the TFI cache."""
import sys, time, io, zipfile, urllib.request
from pathlib import Path
import pandas as pd
import numpy as np

CACHE_DIR = Path("/home/anson/factor-lab/data/aggTrades")
CACHE_FILE = CACHE_DIR / "daily_tfi.parquet"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Load existing cache
existing = pd.read_parquet(CACHE_FILE) if CACHE_FILE.exists() else pd.DataFrame()
existing_dates = set(existing["date"].dt.strftime("%Y-%m-%d")) if not existing.empty else set()
print(f"Existing cache: {len(existing)} days", flush=True)

# Individual months to download (each ~300-500MB)
MISSING = [
    (2025, 3), (2025, 4), (2025, 5),
    (2025, 6), (2025, 7), (2025, 8),
    (2025, 9), (2025, 10), (2025, 11), (2025, 12),
    (2026, 1), (2026, 2),
]

# We already have 2026-03 to 2026-05 from before
# These are all post-2025, so timestamp is microseconds

downloaded = 0
failed = 0

for year, month in MISSING:
    ym = f"{year}-{month:02d}"
    url = f"https://data.binance.vision/data/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{ym}.zip"
    
    t0 = time.time()
    sys.stdout.write(f"[{ym}] downloading ... ")
    sys.stdout.flush()
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "factor-lab/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            zip_bytes = r.read()
    except Exception as e:
        print(f"FAILED: {e}", flush=True)
        failed += 1
        continue
    
    t1 = time.time()
    print(f"{len(zip_bytes)/1024/1024:.0f}MB ({t1-t0:.0f}s), parsing ...", flush=True)
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            csv_name = [n for n in names if n.endswith(".csv")]
            if not csv_name:
                print(f"  no CSV", flush=True)
                failed += 1
                continue
            with zf.open(csv_name[0]) as f:
                df = pd.read_csv(
                    f, header=None,
                    names=["id","price","qty","ftid","ltid","ts_us","maker","best"],
                )
    except Exception as e:
        print(f"  parse FAILED: {e}", flush=True)
        failed += 1
        continue
    
    t2 = time.time()
    
    # timestamp: microseconds (post-2025 format)
    df["date"] = pd.to_datetime(df["ts_us"], unit="us").dt.date
    is_sell = df["maker"].astype(str).str.lower() == "true"
    df["buy_vol"] = np.where(is_sell, 0.0, df["qty"].astype(float))
    df["sell_vol"] = np.where(is_sell, df["qty"].astype(float), 0.0)
    
    daily = df.groupby("date").agg(
        buy_vol=("buy_vol", "sum"),
        sell_vol=("sell_vol", "sum"),
        trade_count=("id", "count"),
    ).reset_index()
    
    daily["total_vol"] = daily["buy_vol"] + daily["sell_vol"]
    daily["tfi_raw"] = (daily["buy_vol"] - daily["sell_vol"]) / daily["total_vol"].replace(0, np.nan)
    daily["date"] = pd.to_datetime(daily["date"])
    
    t3 = time.time()
    ndays = len(daily)
    print(f"  done ({t3-t0:.0f}s): {ndays}d, vol={daily['total_vol'].sum()/1e6:.0f}M BTC, TFI={daily['tfi_raw'].mean():+.4f}", flush=True)
    
    # Append to existing and save incrementally
    existing = pd.concat([existing, daily[["date","buy_vol","sell_vol","total_vol","trade_count","tfi_raw"]]], ignore_index=True)
    existing = existing.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    existing.to_parquet(CACHE_FILE, index=False)
    downloaded += 1

print(f"\nDone: {downloaded} months added, {failed} failed", flush=True)
print(f"Total cache: {len(existing)} days ({existing['date'].min().strftime('%Y-%m-%d')} to {existing['date'].max().strftime('%Y-%m-%d')})", flush=True)
print(f"TFI stats: mean={existing['tfi_raw'].mean():+.5f}, std={existing['tfi_raw'].std():.5f}", flush=True)
