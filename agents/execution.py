"""Execution Agent — multi-broker: mock | oanda | binance"""

from __future__ import annotations

from typing import Any, Optional

from core.oanda_client import OandaClient
from core.binance_client import BinanceClient


class ExecutionAgent:
    """ส่ง/ปิดออเดอร์ผ่าน broker ที่เลือก"""

    def __init__(
        self,
        oanda_client: Optional[OandaClient] = None,
        binance_client: Optional[BinanceClient] = None,
        mode: str = "auto",
        default_units_scale: float = 1.0,
        default_symbol: str = "BTCUSDT",
    ):
        self.oanda = oanda_client
        self.binance = binance_client
        self.default_units_scale = default_units_scale
        self.default_symbol = default_symbol

        if mode == "auto":
            if binance_client is not None and binance_client.is_configured:
                self.mode = "binance"
            elif oanda_client is not None and oanda_client.is_configured:
                self.mode = "oanda"
            else:
                self.mode = "mock"
        else:
            self.mode = mode.lower().strip()

    def test_connection(self) -> dict:
        if self.mode == "mock":
            return {
                "success": True,
                "mode": "mock",
                "message": "Mock mode — ไม่ได้เชื่อม broker จริง",
            }
        if self.mode == "binance":
            if self.binance is None:
                return {"success": False, "mode": "binance", "message": "ไม่มี BinanceClient"}
            result = self.binance.test_connection()
            result["mode"] = "binance"
            return result
        if self.mode == "oanda":
            if self.oanda is None:
                return {"success": False, "mode": "oanda", "message": "ไม่มี OandaClient"}
            result = self.oanda.test_connection()
            result["mode"] = "oanda"
            return result
        return {"success": False, "mode": self.mode, "message": f"โหมดไม่รองรับ: {self.mode}"}

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "MultiAgent",
    ) -> dict:
        direction = direction.upper().strip()
        if direction not in ("BUY", "SELL"):
            return {"success": False, "ticket": None, "message": "direction ต้องเป็น BUY หรือ SELL"}

        qty = abs(float(lot_size)) * float(self.default_units_scale)
        if qty <= 0:
            return {"success": False, "ticket": None, "message": "quantity ต้องมากกว่า 0"}

        symbol = symbol or self.default_symbol

        if self.mode == "mock":
            return {
                "success": True,
                "ticket": "MOCK-BTC-0001",
                "message": "Mock order accepted (ไม่ได้ส่งจริง)",
                "mode": "mock",
                "symbol": symbol,
                "direction": direction,
                "quantity": qty,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }

        if self.mode == "binance":
            if self.binance is None:
                return {"success": False, "ticket": None, "message": "ไม่มี BinanceClient"}
            result = self.binance.place_market_order(
                symbol=symbol,
                side=direction,
                quantity=qty,
                client_order_id=None,
            )
            result["mode"] = "binance"
            result["direction"] = direction
            result["quantity"] = qty
            if stop_loss or take_profit:
                result["note"] = (
                    "Binance Spot MARKET ไม่ติด SL/TP ในออเดอร์เดียว — "
                    "ใช้ OCO/monitor แยกในขั้นถัดไป"
                )
            return result

        if self.mode == "oanda":
            if self.oanda is None:
                return {"success": False, "ticket": None, "message": "ไม่มี OandaClient"}
            units = qty if direction == "BUY" else -qty
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

        return {"success": False, "ticket": None, "message": f"โหมดไม่รองรับ: {self.mode}"}

    def close_position(self, ticket: Any, percent: float = 1.0) -> dict:
        if self.mode == "mock":
            return {
                "success": True,
                "message": f"Mock close ticket={ticket} percent={percent}",
                "mode": "mock",
            }
        if self.mode == "binance":
            return {
                "success": False,
                "message": "ปิด position บน Spot ใช้ SELL/BUY กลับด้าน — เรียก place_order แทน",
                "mode": "binance",
            }
        if self.mode == "oanda" and self.oanda is not None:
            return self.oanda.close_trade(str(ticket), units="ALL")
        return {"success": False, "message": "close ไม่รองรับในโหมดนี้", "mode": self.mode}

    def modify_sl_tp(
        self,
        ticket: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        if self.mode == "mock":
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
            "message": "modify_sl_tp ยังไม่ implement สำหรับโหมดนี้",
            "mode": self.mode,
        }
