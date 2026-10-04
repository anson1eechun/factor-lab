#!/usr/bin/env python3
"""Test max available data for 15M and 5M from Binance"""
import sys
sys.path.insert(0, '/home/anson/factor-lab')
import pandas as pd
from core.adapters.crypto import CryptoAdapter

adapter = CryptoAdapter()

for tf, limits in [('15m', [5000, 10000, 15000]), ('5m', [5000, 10000, 15000])]:
    for limit in limits:
        try:
            raw = adapter.get_ohlcv("BTCUSDT", tf, limit=limit)
            raw['dt'] = pd.to_datetime(raw['timestamp'], unit='ms', utc=True)
            df = raw.set_index('dt').sort_index()
            days = (df.index[-1] - df.index[0]).days
            print(f"{tf} limit={limit}: {len(df)} bars, {df.index[0]} → {df.index[-1]}, {days}d")
        except Exception as e:
            print(f"{tf} limit={limit}: ERROR {e}")
