"""Extended Binance order helpers: MARKET test mode + OCO TP/SL.

Used by scripts/test_binance_tpsl.py and GitHub Action.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

from core.binance_client import BinanceClient


def _fmt_qty(qty: float, step: str = "0.00001") -> str:
    d = Decimal(str(qty))
    step_d = Decimal(step)
    q = (d / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d
    s = f"{q:f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _fmt_price(price: float, tick: str = "0.01") -> str:
    d = Decimal(str(price))
    tick_d = Decimal(tick)
    p = (d / tick_d).to_integral_value(rounding=ROUND_DOWN) * tick_d
    return f"{p:.2f}"


class BinanceOrderExt(BinanceClient):
    """BinanceClient + order test + OCO TP/SL + cancel helpers."""

    def get_symbol_filters(self, symbol: str = "BTCUSDT") -> dict[str, str]:
        info = self.get_exchange_info(symbol)
        tick, step = "0.01", "0.00001"
        if not info.get("ok"):
            return {"tickSize": tick, "stepSize": step}
        symbols = (info.get("data") or {}).get("symbols") or []
        if not symbols:
            return {"tickSize": tick, "stepSize": step}
        for f in symbols[0].get("filters") or []:
            if f.get("filterType") == "PRICE_FILTER":
                tick = f.get("tickSize") or tick
            if f.get("filterType") == "LOT_SIZE":
                step = f.get("stepSize") or step
        return {"tickSize": tick, "stepSize": step}

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: Optional[str] = None,
        test_only: bool = False,
    ) -> dict[str, Any]:
        symbol = self.to_binance_symbol(symbol)
        side = side.upper().strip()
        if side not in ("BUY", "SELL"):
            return {"success": False, "ticket": None, "message": "side ต้องเป็น BUY หรือ SELL"}
        if quantity <= 0:
            return {"success": False, "ticket": None, "message": "quantity ต้องมากกว่า 0"}

        filters = self.get_symbol_filters(symbol)
        qty_str = _fmt_qty(quantity, filters["stepSize"])
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": qty_str,
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id[:36]

        path = "/api/v3/order/test" if test_only else "/api/v3/order"
        result = self._request("POST", path, params=params, signed=True)
        if not result["ok"]:
            return {
                "success": False,
                "ticket": None,
                "message": result["error"],
                "raw": result["data"],
                "test_only": test_only,
            }
        data = result["data"] or {}
        if test_only:
            return {
                "success": True,
                "ticket": None,
                "message": "order test OK (ไม่ได้ส่งจริง)",
                "symbol": symbol,
                "side": side,
                "quantity": qty_str,
                "test_only": True,
                "raw": data,
            }
        return {
            "success": True,
            "ticket": str(data.get("orderId")),
            "message": "order accepted",
            "symbol": symbol,
            "side": side,
            "quantity": qty_str,
            "status": data.get("status"),
            "fills": data.get("fills"),
            "test_only": False,
            "raw": data,
        }

    def place_oco_sell_tp_sl(
        self,
        symbol: str,
        quantity: float,
        take_profit_price: float,
        stop_loss_price: float,
        stop_limit_price: Optional[float] = None,
    ) -> dict[str, Any]:
        symbol = self.to_binance_symbol(symbol)
        filters = self.get_symbol_filters(symbol)
        tick = filters["tickSize"]
        step = filters["stepSize"]
        qty_str = _fmt_qty(quantity, step)
        tp = _fmt_price(take_profit_price, tick)
        sl = _fmt_price(stop_loss_price, tick)
        if stop_limit_price is None:
            stop_limit_price = float(sl) * 0.999
        sl_limit = _fmt_price(stop_limit_price, tick)

        if float(tp) <= float(sl):
            return {
                "success": False,
                "message": "take_profit ต้องสูงกว่า stop_loss สำหรับ SELL OCO หลัง BUY",
            }

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": "SELL",
            "quantity": qty_str,
            "price": tp,
            "stopPrice": sl,
            "stopLimitPrice": sl_limit,
            "stopLimitTimeInForce": "GTC",
        }
        result = self._request("POST", "/api/v3/order/oco", params=params, signed=True)
        if not result["ok"]:
            alt = self._place_oco_order_list(symbol, qty_str, tp, sl, sl_limit)
            if alt.get("success"):
                return alt
            return {
                "success": False,
                "message": result["error"],
                "raw": result["data"],
                "fallback": alt,
            }

        data = result["data"] or {}
        return {
            "success": True,
            "message": "OCO TP/SL placed",
            "order_list_id": data.get("orderListId"),
            "orders": data.get("orders") or data.get("orderReports"),
            "tp_price": tp,
            "sl_price": sl,
            "sl_limit_price": sl_limit,
            "quantity": qty_str,
            "raw": data,
        }

    def _place_oco_order_list(
        self,
        symbol: str,
        quantity: str,
        take_profit_price: str,
        stop_loss_price: str,
        stop_limit_price: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": "SELL",
            "quantity": quantity,
            "aboveType": "TAKE_PROFIT_LIMIT",
            "abovePrice": take_profit_price,
            "aboveStopPrice": take_profit_price,
            "aboveTimeInForce": "GTC",
            "belowType": "STOP_LOSS_LIMIT",
            "belowPrice": stop_limit_price,
            "belowStopPrice": stop_loss_price,
            "belowTimeInForce": "GTC",
        }
        result = self._request("POST", "/api/v3/orderList/oco", params=params, signed=True)
        if not result["ok"]:
            return {"success": False, "message": result["error"], "raw": result["data"]}
        data = result["data"] or {}
        return {
            "success": True,
            "message": "OCO TP/SL placed (orderList)",
            "order_list_id": data.get("orderListId"),
            "orders": data.get("orders") or data.get("orderReports"),
            "tp_price": take_profit_price,
            "sl_price": stop_loss_price,
            "sl_limit_price": stop_limit_price,
            "quantity": quantity,
            "raw": data,
        }

    def cancel_order_list(self, symbol: str, order_list_id: int) -> dict[str, Any]:
        params = {
            "symbol": self.to_binance_symbol(symbol),
            "orderListId": order_list_id,
        }
        result = self._request("DELETE", "/api/v3/orderList", params=params, signed=True)
        if not result["ok"]:
            return {"success": False, "message": result["error"], "raw": result["data"]}
        return {"success": True, "message": "order list cancelled", "raw": result["data"]}

    def cancel_all_open_orders(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        result = self._request(
            "DELETE",
            "/api/v3/openOrders",
            params={"symbol": self.to_binance_symbol(symbol)},
            signed=True,
        )
        if not result["ok"]:
            return {"success": False, "message": result["error"], "raw": result["data"]}
        return {"success": True, "message": "open orders cancelled", "raw": result["data"]}
