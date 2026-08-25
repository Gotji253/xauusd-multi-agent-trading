"""Binance Spot REST API client (BTCUSDT focus).

Docs: https://binance-docs.github.io/apidocs/spot/en/
Auth: API Key header + HMAC SHA256 signature (query string)

Testnet: https://testnet.binance.vision
Live:    https://api.binance.com
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests


class BinanceClient:
    """Minimal Binance Spot client for connectivity + market orders."""

    LIVE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        environment: str = "testnet",
        timeout: float = 15.0,
        base_url: str | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.api_secret = (api_secret or "").strip()
        env = (environment or "testnet").lower().strip()
        if base_url:
            self.base_url = base_url.rstrip("/")
            self.environment = env if env else "custom"
        elif env in ("live", "mainnet", "prod", "production"):
            self.base_url = self.LIVE_URL
            self.environment = "live"
        else:
            self.base_url = self.TESTNET_URL
            self.environment = "testnet"
        self.timeout = timeout
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _sign(self, params: dict[str, Any]) -> str:
        query = urlencode(params, True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        params = dict(params or {})
        if signed:
            if not self.is_configured:
                return {
                    "ok": False,
                    "error": "Binance API key/secret ยังไม่ถูกตั้งค่า",
                    "status_code": 0,
                    "data": None,
                }
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign(params)

        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, params=params, timeout=self.timeout)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            if resp.status_code >= 400:
                if isinstance(data, dict):
                    err = data.get("msg") or data.get("message") or str(data)
                else:
                    err = str(data)
                return {"ok": False, "error": err, "status_code": resp.status_code, "data": data}
            return {"ok": True, "error": None, "status_code": resp.status_code, "data": data}
        except requests.RequestException as e:
            return {"ok": False, "error": f"network error: {e}", "status_code": 0, "data": None}

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/api/v3/ping")

    def get_server_time(self) -> dict[str, Any]:
        return self._request("GET", "/api/v3/time")

    def get_ticker_price(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        return self._request(
            "GET", "/api/v3/ticker/price", params={"symbol": self.to_binance_symbol(symbol)}
        )

    def get_exchange_info(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        return self._request(
            "GET", "/api/v3/exchangeInfo", params={"symbol": self.to_binance_symbol(symbol)}
        )

    def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "15m",
        limit: int = 1000,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.to_binance_symbol(symbol),
            "interval": interval,
            "limit": min(int(limit), 1000),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)
        return self._request("GET", "/api/v3/klines", params=params, signed=False)

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/api/v3/account", signed=True)

    def test_connection(self) -> dict[str, Any]:
        pub = self.ping()
        if not pub["ok"]:
            return {
                "success": False,
                "message": f"ping ล้มเหลว: {pub['error']}",
                "environment": self.environment,
            }
        if not self.is_configured:
            return {
                "success": False,
                "message": "ขาด BINANCE_API_KEY หรือ BINANCE_API_SECRET",
                "environment": self.environment,
            }
        acc = self.get_account()
        if not acc["ok"]:
            return {
                "success": False,
                "message": f"API auth ไม่ผ่าน: {acc['error']}",
                "environment": self.environment,
                "status_code": acc["status_code"],
            }
        data = acc["data"] or {}
        balances = data.get("balances") or []
        interesting = {}
        watch = ("BTC", "USDT", "USDC", "BNB", "FDUSD", "ETH")
        for b in balances:
            free = float(b.get("free") or 0)
            locked = float(b.get("locked") or 0)
            if free > 0 or locked > 0:
                if b.get("asset") in watch:
                    interesting[b["asset"]] = {"free": free, "locked": locked}
        ticker = self.get_ticker_price("BTCUSDT")
        price = None
        if ticker.get("ok"):
            price = (ticker.get("data") or {}).get("price")
        return {
            "success": True,
            "message": "เชื่อมต่อ Binance สำเร็จ (BTCUSDT)",
            "environment": self.environment,
            "can_trade": data.get("canTrade"),
            "account_type": data.get("accountType"),
            "balances": interesting,
            "btcusdt_price": price,
            "last_price": price,
        }

    @staticmethod
    def to_binance_symbol(symbol: str) -> str:
        s = symbol.upper().replace("/", "").replace("-", "").replace("_", "")
        if s in ("BTC", "BTCUSD", "BTCUSDT"):
            return "BTCUSDT"
        return s

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        client_order_id: Optional[str] = None,
        test_only: bool = False,
        allow_live: bool = False,
    ) -> dict[str, Any]:
        import os

        symbol = self.to_binance_symbol(symbol)
        side = side.upper().strip()
        if side not in ("BUY", "SELL"):
            return {"success": False, "ticket": None, "message": "side ต้องเป็น BUY หรือ SELL"}
        if quantity <= 0:
            return {"success": False, "ticket": None, "message": "quantity ต้องมากกว่า 0"}

        if self.environment == "live" and not test_only:
            env_allow = os.getenv("ALLOW_LIVE_BINANCE", "").lower() in ("1", "true", "yes")
            if not (allow_live or env_allow):
                return {
                    "success": False,
                    "ticket": None,
                    "message": "LIVE mode ถูกบล็อก — ตั้ง ALLOW_LIVE_BINANCE=true",
                    "environment": self.environment,
                }

        qty_str = f"{quantity:.8f}".rstrip("0").rstrip(".")
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
            "raw": data,
            "environment": self.environment,
        }

    def get_open_orders(self, symbol: str = "BTCUSDT") -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v3/openOrders",
            params={"symbol": self.to_binance_symbol(symbol)},
            signed=True,
        )

    def get_my_trades(
        self,
        symbol: str = "BTCUSDT",
        limit: int = 20,
        start_time: int | None = None,
    ) -> dict[str, Any]:
        """Recent account trades for symbol (signed)."""
        params: dict[str, Any] = {
            "symbol": self.to_binance_symbol(symbol),
            "limit": max(1, min(int(limit), 1000)),
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        return self._request("GET", "/api/v3/myTrades", params=params, signed=True)

    def get_balances_map(self) -> dict[str, dict[str, float]]:
        """Return {asset: {free, locked}} for non-zero balances."""
        acc = self.get_account()
        out: dict[str, dict[str, float]] = {}
        if not acc.get("ok"):
            return out
        for b in (acc.get("data") or {}).get("balances") or []:
            free = float(b.get("free") or 0)
            locked = float(b.get("locked") or 0)
            if free > 0 or locked > 0:
                out[str(b.get("asset", "")).upper()] = {"free": free, "locked": locked}
        return out
