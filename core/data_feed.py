"""Data Feed abstraction."""

from __future__ import annotations

from typing import Any, Optional


class DataFeed:
    def __init__(self, connector: Any = None):
        self.connector = connector

    def get_ohlcv(self, symbol: str, timeframe: str, count: int = 500) -> Optional[Any]:
        """ดึงข้อมูล OHLCV"""
        return None
