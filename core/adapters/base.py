"""市場無關的資料源介面。換市場 = 換 Adapter，因子/辯論流程不變。"""
from __future__ import annotations
from abc import ABC, abstractmethod


class MarketAdapter(ABC):
    name: str

    @abstractmethod
    def list_symbols(self) -> list[str]:
        """可交易/可研究的標的清單。"""

    @abstractmethod
    def ohlcv(self, symbol: str, timeframe: str, since: str | None = None) -> list[dict]:
        """回傳 [{ts, open, high, low, close, volume}, ...]，時間升冪。"""

    def fundamental(self, symbol: str) -> dict:
        """基本面 / 鏈上 / 法人籌碼，預設無。"""
        return {}

    def sentiment(self, symbol: str) -> dict:
        """社群情緒，預設無。"""
        return {}
