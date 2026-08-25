"""Execution Agent — multi-broker: mock | oanda | binance (+ OCO TP/SL)"""

from __future__ import annotations

from typing import Any, Optional, Union

from core.oanda_client import OandaClient
from core.binance_client import BinanceClient
from core.binance_orders import BinanceOrderExt
from utils.trade_log import get_trade_logger


class ExecutionAgent:
    """ส่ง/ปิดออเดอร์ผ่าน broker ที่เลือก

    Binance Spot flow:
      MARKET entry → (optional) OCO TP/SL
    """

    def __init__(
        self,
        oanda_client: Optional[OandaClient] = None,
        binance_client: Optional[Union[BinanceClient, BinanceOrderExt]] = None,
        mode: str = "auto",
        default_units_scale: float = 1.0,
        default_symbol: str = "BTCUSDT",
        attach_oco: bool = True,
    ):
        self.oanda = oanda_client
        self.binance = binance_client
        self.default_units_scale = default_units_scale
        self.default_symbol = default_symbol
        self.attach_oco = attach_oco

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

    @staticmethod
    def _filled_qty(market_result: dict, fallback_qty: float) -> float:
        """Prefer executed qty from fills when available."""
        fills = market_result.get("fills") or []
        if fills:
            try:
                total = sum(float(f.get("qty", 0) or 0) for f in fills)
                if total > 0:
                    return total
            except (TypeError, ValueError):
                pass
        raw = market_result.get("raw") or {}
        for key in ("executedQty", "origQty", "quantity"):
            if raw.get(key):
                try:
                    v = float(raw[key])
                    if v > 0:
                        return v
                except (TypeError, ValueError):
                    pass
        q = market_result.get("quantity")
        if q is not None:
            try:
                v = float(q)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        return float(fallback_qty)

    def _attach_oco(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict[str, Any]:
        """Place protective OCO after a successful MARKET fill."""
        if not isinstance(self.binance, BinanceOrderExt):
            return {
                "success": False,
                "message": "ต้องการ BinanceOrderExt เพื่อวาง OCO (ตอนนี้เป็น BinanceClient ธรรมดา)",
            }
        if stop_loss <= 0 or take_profit <= 0:
            return {
                "success": False,
                "message": "ต้องมีทั้ง stop_loss และ take_profit เพื่อวาง OCO",
            }

        if direction == "BUY":
            return self.binance.place_oco_sell_tp_sl(
                symbol=symbol,
                quantity=quantity,
                take_profit_price=take_profit,
                stop_loss_price=stop_loss,
            )
        # SELL entry → BUY OCO (cover)
        return self.binance.place_oco_buy_tp_sl(
            symbol=symbol,
            quantity=quantity,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
        )

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "MultiAgent",
        attach_oco: Optional[bool] = None,
        client_order_id: Optional[str] = None,
        order_key: Optional[str] = None,
    ) -> dict:
        direction = direction.upper().strip()
        if direction not in ("BUY", "SELL"):
            return {"success": False, "ticket": None, "message": "direction ต้องเป็น BUY หรือ SELL"}

        qty = abs(float(lot_size)) * float(self.default_units_scale)
        if qty <= 0:
            return {"success": False, "ticket": None, "message": "quantity ต้องมากกว่า 0"}

        symbol = symbol or self.default_symbol
        use_oco = self.attach_oco if attach_oco is None else bool(attach_oco)

        if self.mode == "mock":
            oco_mock = None
            if use_oco and stop_loss and take_profit:
                oco_mock = {
                    "success": True,
                    "message": "Mock OCO TP/SL accepted",
                    "order_list_id": "MOCK-OCO-1",
                    "tp_price": take_profit,
                    "sl_price": stop_loss,
                    "quantity": qty,
                }
            return {
                "success": True,
                "ticket": "MOCK-BTC-0001",
                "message": "Mock order accepted (ไม่ได้ส่งจริง)"
                + (" + OCO" if oco_mock else ""),
                "mode": "mock",
                "symbol": symbol,
                "direction": direction,
                "quantity": qty,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "oco": oco_mock,
                "oco_failed": False,
                "client_order_id": client_order_id,
                "order_key": order_key,
            }

        if self.mode == "binance":
            if self.binance is None:
                return {"success": False, "ticket": None, "message": "ไม่มี BinanceClient"}

            # Safety: live order ต้องเปิด ALLOW_LIVE_BINANCE=true (gate ใน client)
            result = self.binance.place_market_order(
                symbol=symbol,
                side=direction,
                quantity=qty,
                client_order_id=client_order_id,
                test_only=False,
                allow_live=False,
            )
            result["mode"] = "binance"
            result["direction"] = direction
            result["quantity"] = qty
            result["stop_loss"] = stop_loss
            result["take_profit"] = take_profit
            result["oco"] = None
            result["oco_failed"] = False
            result["client_order_id"] = client_order_id
            result["order_key"] = order_key

            # Binance duplicate clientOrderId → treat as idempotent skip
            if not result.get("success") and client_order_id:
                msg = str(result.get("message") or "").lower()
                raw = str(result.get("raw") or "").lower()
                is_dup = (
                    "duplicate" in msg
                    or "already exists" in msg
                    or "clientorderid" in msg and "exist" in msg
                    or "client order" in msg and "duplicate" in msg
                    or '"code":-2010' in raw and "duplicate" in raw
                )
                if is_dup:
                    result["success"] = True
                    result["skipped"] = True
                    result["idempotent_duplicate"] = True
                    result["message"] = (
                        f"idempotent: clientOrderId already used ({client_order_id})"
                    )

            if not result.get("success"):
                try:
                    get_trade_logger("execution").log_order_result(result, context="place_order")
                except Exception:
                    pass
                return result

            # MARKET สำเร็จ → วาง OCO ถ้าเปิดใช้และมี SL/TP
            if use_oco and stop_loss and take_profit:
                fill_qty = self._filled_qty(result, qty)
                oco = self._attach_oco(
                    symbol=symbol,
                    direction=direction,
                    quantity=fill_qty,
                    stop_loss=float(stop_loss),
                    take_profit=float(take_profit),
                )
                result["oco"] = oco
                if oco.get("success"):
                    result["message"] = (
                        f"{result.get('message', 'order accepted')} + OCO TP/SL"
                    )
                    result["oco_order_list_id"] = oco.get("order_list_id")
                else:
                    result["oco_failed"] = True
                    result["message"] = (
                        "MARKET สำเร็จ แต่ OCO ล้ม — ถือไม้ไม่มี SL/TP: "
                        + str(oco.get("message", "unknown"))
                    )
            elif stop_loss or take_profit:
                result["note"] = (
                    "มี SL/TP แต่ attach_oco=False — ไม่ได้วาง OCO"
                )

            try:
                get_trade_logger("execution").log_order_result(result, context="place_order")
            except Exception:
                pass
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
            "message": "modify_sl_tp ยังไม่ implement สำหรับโหมดนี้ — ใช้ cancel OCO แล้ววางใหม่",
            "mode": self.mode,
        }
