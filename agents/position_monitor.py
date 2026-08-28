"""Position Monitor — detect unprotected holdings and stale OCO orders."""

from __future__ import annotations

from typing import Any, Optional, Union

from agents.line_notifier import LineNotifierAgent
from core.binance_client import BinanceClient
from core.binance_orders import BinanceOrderExt
from utils.runtime_state import RuntimeState, get_runtime_state
from utils.trade_log import get_trade_logger


class PositionMonitor:
    def __init__(
        self,
        binance_client: Optional[Union[BinanceClient, BinanceOrderExt]] = None,
        notifier: Optional[LineNotifierAgent] = None,
        state: Optional[RuntimeState] = None,
        symbol: str = "BTCUSDT",
        min_base_qty: float = 1e-6,
        flatten_unprotected: bool = False,
        cancel_orphan_orders: bool = True,
    ):
        self.binance = binance_client
        self.notifier = notifier or LineNotifierAgent()
        self.state = state or get_runtime_state()
        self.symbol = symbol.upper()
        self.min_base_qty = min_base_qty
        self.flatten_unprotected = flatten_unprotected
        self.cancel_orphan_orders = cancel_orphan_orders
        self.log = get_trade_logger("position_monitor")

    @staticmethod
    def _base_asset(symbol: str) -> str:
        s = symbol.upper()
        for quote in ("USDT", "BUSD", "USD", "BTC", "ETH"):
            if s.endswith(quote) and len(s) > len(quote):
                return s[: -len(quote)]
        return s

    def _base_balance(self) -> tuple[float, dict[str, Any]]:
        if self.binance is None:
            return 0.0, {"ok": False, "message": "no binance client"}
        if hasattr(self.binance, "get_account_summary"):
            summary = self.binance.get_account_summary()
            if summary.get("success") or summary.get("ok"):
                base = self._base_asset(self.symbol)
                for b in summary.get("balances") or []:
                    if str(b.get("asset", "")).upper() == base:
                        free = float(b.get("free") or 0)
                        locked = float(b.get("locked") or 0)
                        return free + locked, {"source": "summary", "base": base, "free": free, "locked": locked}
        acc = self.binance.get_account()
        if not acc.get("ok"):
            return 0.0, {"ok": False, "error": acc.get("error")}
        data = acc.get("data") or {}
        base = self._base_asset(self.symbol)
        total = free = locked = 0.0
        for b in data.get("balances") or []:
            if str(b.get("asset", "")).upper() == base:
                free = float(b.get("free") or 0)
                locked = float(b.get("locked") or 0)
                total = free + locked
                break
        return total, {"ok": True, "base": base, "free": free, "locked": locked}

    def _open_orders(self) -> tuple[list[dict], dict[str, Any]]:
        if self.binance is None:
            return [], {"ok": False, "message": "no binance client"}
        res = self.binance.get_open_orders(self.symbol)
        if not res.get("ok"):
            return [], {"ok": False, "error": res.get("error")}
        data = res.get("data") or []
        if not isinstance(data, list):
            data = []
        return data, {"ok": True, "count": len(data)}

    def _has_protective_order(self, open_orders: list[dict], local: Optional[dict]) -> bool:
        if local and local.get("protected") and local.get("oco_id"):
            return bool(open_orders)
        protective_types = {
            "STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT",
            "STOP", "STOP_MARKET", "TAKE_PROFIT_MARKET",
        }
        for o in open_orders:
            t = str(o.get("type") or "").upper()
            if t in protective_types:
                return True
            if o.get("orderListId") not in (None, "", 0, "0"):
                return True
        return False

    def check(self, use_exchange: bool = True) -> dict[str, Any]:
        report: dict[str, Any] = {
            "symbol": self.symbol,
            "local_position": self.state.get_open_position(self.symbol),
            "base_qty": 0.0,
            "open_orders_count": 0,
            "protected": True,
            "issues": [],
            "actions": [],
        }
        local = report["local_position"]
        open_orders: list[dict] = []
        base_qty = 0.0
        if use_exchange and self.binance is not None:
            base_qty, bal_meta = self._base_balance()
            open_orders, ord_meta = self._open_orders()
            report["base_qty"] = base_qty
            report["balance_meta"] = bal_meta
            report["open_orders_count"] = len(open_orders)
            report["orders_meta"] = ord_meta
        elif local:
            base_qty = float(local.get("quantity") or 0)
            report["base_qty"] = base_qty
        has_position = base_qty >= self.min_base_qty
        if not has_position and local and float(local.get("quantity") or 0) >= self.min_base_qty:
            has_position = True
        if not has_position:
            has_protection = True
        elif use_exchange and self.binance is not None:
            has_protection = self._has_protective_order(open_orders, local)
        else:
            has_protection = bool(local and local.get("protected"))
        if local and not local.get("protected") and float(local.get("quantity") or 0) >= self.min_base_qty:
            has_position = True
            has_protection = False if not open_orders else has_protection
        report["protected"] = bool(has_protection or not has_position)
        if has_position and not has_protection:
            report["issues"].append("UNPROTECTED_POSITION")
            self._alert_unprotected(report, local)
            if self.flatten_unprotected:
                act = self._flatten(base_qty if base_qty > 0 else float((local or {}).get("quantity") or 0))
                report["actions"].append(act)
        if (not has_position) and open_orders and self.cancel_orphan_orders:
            report["issues"].append("ORPHAN_OPEN_ORDERS")
            act = self._cancel_orphans()
            report["actions"].append(act)
            try:
                self.state.clear_open_position(self.symbol)
            except Exception:
                pass
        elif not has_position and local:
            try:
                self.state.clear_open_position(self.symbol)
                report["actions"].append({"action": "clear_local_position", "success": True})
            except Exception as e:
                report["actions"].append({"action": "clear_local_position", "success": False, "error": str(e)})
        self.log.info(
            "monitor.check",
            symbol=self.symbol,
            base_qty=report["base_qty"],
            open_orders=report["open_orders_count"],
            protected=report["protected"],
            issues=report["issues"],
        )
        return report

    def _alert_unprotected(self, report: dict[str, Any], local: Optional[dict]) -> None:
        detail = (
            f"{self.symbol} qty≈{report.get('base_qty')}\n"
            f"open_orders={report.get('open_orders_count')}\n"
            f"local={local}\nflatten={self.flatten_unprotected}"
        )
        self.log.error("monitor.unprotected", detail=detail)
        try:
            self.notifier.notify_system_alert("UNPROTECTED POSITION", detail)
        except Exception:
            pass

    def _flatten(self, qty: float) -> dict[str, Any]:
        if self.binance is None or qty < self.min_base_qty:
            return {"action": "flatten", "success": False, "message": "no client or qty"}
        self.log.warn("monitor.flatten", qty=qty, symbol=self.symbol)
        try:
            res = self.binance.place_market_order(self.symbol, "SELL", qty, test_only=False, allow_live=False)
            if res.get("success"):
                try:
                    self.state.clear_open_position(self.symbol)
                except Exception:
                    pass
                try:
                    self.notifier.notify_system_alert("EMERGENCY FLATTEN", f"SELL {self.symbol} qty={qty} ticket={res.get('ticket')}")
                except Exception:
                    pass
            return {"action": "flatten", **res}
        except Exception as e:
            return {"action": "flatten", "success": False, "message": str(e)}

    def _cancel_orphans(self) -> dict[str, Any]:
        if self.binance is None:
            return {"action": "cancel_orphans", "success": False, "message": "no client"}
        self.log.warn("monitor.cancel_orphans", symbol=self.symbol)
        if hasattr(self.binance, "cancel_all_open_orders"):
            res = self.binance.cancel_all_open_orders(self.symbol)
        else:
            res = {"success": False, "message": "cancel_all_open_orders not available"}
        try:
            self.notifier.notify_system_alert("ORPHAN ORDERS CANCELLED", f"{self.symbol}: {res}")
        except Exception:
            pass
        return {"action": "cancel_orphans", **(res if isinstance(res, dict) else {"result": res})}
