"""加密貨幣 Adapter。優先用 ccxt；未安裝時退回 Binance 公開 REST（標準庫）。"""
from __future__ import annotations
import json, time, urllib.request
from .base import MarketAdapter

try:
    import ccxt  # type: ignore
    _HAS_CCXT = True
except ImportError:
    _HAS_CCXT = False

_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000,
    "1d": 86_400_000, "1w": 604_800_000,
}

_BINANCE_MAX_LIMIT = 1000  # Binance klines per-request cap


class CryptoAdapter(MarketAdapter):
    name = "crypto"

    def __init__(self, exchange="binance", universe=None):
        self.universe = universe or ["BTC/USDT", "ETH/USDT"]
        self.exchange_id = exchange
        self._ex = getattr(ccxt, exchange)() if _HAS_CCXT else None

    def list_symbols(self) -> list[str]:
        return self.universe

    def ohlcv(self, symbol, timeframe="1d", since=None) -> list[dict]:
        if _HAS_CCXT:
            rows = self._ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=500)
        else:
            rows = self._binance_rest(symbol, timeframe)
        return [dict(zip(("ts", "open", "high", "low", "close", "volume"), r)) for r in rows]

    def _binance_rest(self, symbol, timeframe, limit=500, end_ms=None):
        sym = symbol.replace("/", "")
        interval = {"1d": "1d", "1h": "1h", "4h": "4h",
                    "1w": "1w", "15m": "15m", "5m": "5m", "1m": "1m"}.get(timeframe, "1d")
        params = f"symbol={sym}&interval={interval}&limit={limit}"
        if end_ms is not None:
            params += f"&endTime={int(end_ms)}"
        url = f"https://api.binance.com/api/v3/klines?{params}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
        # Binance kline: [openTime, open, high, low, close, volume, ...]
        return [[k[0], float(k[1]), float(k[2]), float(k[3]),
                 float(k[4]), float(k[5])] for k in data]

    # ------------------------------------------------------------------
    # DataFrame helper used by backtests / midweek_refresh
    # ------------------------------------------------------------------
    def get_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 500):
        """
        回傳 pandas DataFrame，欄位：timestamp(int ms), open, high, low, close, volume。

        symbol 接受 'BTC/USDT' 或 'BTCUSDT'。limit 可超過 1000，會自動分頁回填。
        """
        import pandas as pd

        # 規範 symbol：若已是 'BTCUSDT' 形式則維持
        norm_symbol = symbol if "/" in symbol else symbol

        all_rows: list[list] = []
        remaining = int(limit)
        end_ms: int | None = None

        if _HAS_CCXT:
            # ccxt 路徑：直接用 fetch_ohlcv，盡量遵守 limit
            # 為避免複雜分頁，這裡單次抓 min(limit, 1500)
            try:
                ex_symbol = symbol if "/" in symbol else self._to_ccxt_symbol(symbol)
                rows = self._ex.fetch_ohlcv(ex_symbol, timeframe=timeframe, limit=min(remaining, 1500))
                all_rows = [list(r[:6]) for r in rows]
            except Exception:
                # ccxt 失敗則退回 REST
                all_rows = []

        if not all_rows:
            # REST 分頁：往後抓直到湊滿 limit 或回傳空
            while remaining > 0:
                batch_size = min(remaining, _BINANCE_MAX_LIMIT)
                rows = self._binance_rest(norm_symbol, timeframe,
                                          limit=batch_size, end_ms=end_ms)
                if not rows:
                    break
                # 合併（更早資料放前面）
                all_rows = rows + all_rows
                # 下一頁的 endTime = 本批最早一根 - 1ms
                earliest_ts = rows[0][0]
                end_ms = earliest_ts - 1
                remaining -= len(rows)
                if len(rows) < batch_size:
                    break  # 已沒有更早資料
                time.sleep(0.2)  # 禮貌限速

        df = pd.DataFrame(
            all_rows,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        # 去重 + 排序
        if not df.empty:
            df = df.drop_duplicates(subset=["timestamp"], keep="last")
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    @staticmethod
    def _to_ccxt_symbol(sym: str) -> str:
        """BTCUSDT → BTC/USDT (僅支援常見 quote)。"""
        for quote in ("USDT", "USDC", "BUSD", "BTC", "ETH"):
            if sym.endswith(quote) and len(sym) > len(quote):
                return f"{sym[:-len(quote)]}/{quote}"
        return sym
