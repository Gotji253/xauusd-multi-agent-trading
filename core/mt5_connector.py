"""MT5 Connector with clear interface for both Live and Mock."""

from __future__ import annotations

from typing import Any, Optional


class MT5Connector:
    """Interface สำหรับเชื่อมต่อ MetaTrader 5"""

    def __init__(self):
        self.connected = False

    def connect(self, login: int, password: str, server: str, path: Optional[str] = None) -> bool:
        """เชื่อมต่อ MT5 Terminal"""
        # TODO: implement with MetaTrader5 package
        self.connected = False
        return False

    def disconnect(self) -> None:
        self.connected = False

    def get_account_info(self) -> dict[str, Any]:
        return {}

    def get_rates(self, symbol: str, timeframe: int, count: int) -> Any:
        return None

    def order_send(self, request: dict) -> Any:
        return None
