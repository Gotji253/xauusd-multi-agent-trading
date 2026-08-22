"""Execution Agent — ส่ง/ปิดออเดอร์ผ่าน OANDA v20 API (หรือ mock)"""

from __future__ import annotations

from typing import Any, Optional

from core.oanda_client import OandaClient


class ExecutionAgent:
    def __init__(
        self,
        oanda_client: Optional[OandaClient] = None,
        mode: str = "auto",
        default_units_scale: float = 1.0,
    ):
        self.oanda = oanda_client
        self.default_units_scale = default_units_scale
        if mode == "auto":
            if oanda_client is not None and oanda_client.is_configured:
                self.mode = "oanda"
            else:
                self.mode = "mock"
        else:
            self.mode = mode

    def test_connection(self) -> dict:
        if self.mode == "mock" or self.oanda is None:
            return {
                "success": True,
                "mode": "mock",
                "message": "Mock mode — ไม่ได้เชื่อม OANDA จริง (ใส่ API key เพื่อสลับเป็น oanda)",
            }
        result = self.oanda.test_connection()
        result["mode"] = "oanda"
        return result

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "XAUUSD-MultiAgent",
    ) -> dict:
        direction = direction.upper().strip()
        if direction not in ("BUY", "SELL"):
            return {"success": False, "ticket": None, "message": "direction ต้องเป็น BUY หรือ SELL"}
        units = abs(float(lot_size)) * float(self.default_units_scale)
        if units <= 0:
            return {"success": False, "ticket": None, "message": "units ต้องมากกว่า 0"}
        if direction == "SELL":
            units = -units
        if self.mode == "mock" or self.oanda is None:
            return {
                "success": True,
                "ticket": "MOCK-0001",
                "message": "Mock order accepted (ไม่ได้ส่งจริง)",
                "mode": "mock",
                "symbol": symbol,
                "direction": direction,
                "units": units,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        result = self.oanda.place_market_order(
            instrument=symbol,
            units=units,
            stop_loss=stop_loss if stop_loss else None,
            take_profit=take_profit if take_profit else None,
            client_comment=comment,
        )
        result["mode"] = "oanda"
        result["direction"] = direction
        result["units"] = units
        return result

    def close_position(self, ticket: Any, percent: float = 1.0) -> dict:
        if self.mode == "mock" or self.oanda is None:
            return {
                "success": True,
                "message": f"Mock close ticket={ticket} percent={percent}",
                "mode": "mock",
            }
        return self.oanda.close_trade(str(ticket), units="ALL")

    def modify_sl_tp(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        if self.mode == "mock" or self.oanda is None:
            return {
                "success": True,
                "message": "Mock modify SL/TP",
                "mode": "mock",
                "ticket": ticket,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        return {
            "success": False,
            "message": "modify_sl_tp สำหรับ OANDA ยังไม่ implement ในรอบนี้",
            "mode": "oanda",
        }
