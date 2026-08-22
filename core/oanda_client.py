"""OANDA v20 REST API client for XAU_USD trading.

Docs: https://developer.oanda.com/rest-live-v20/introduction/
- Practice: https://api-fxpractice.oanda.com
- Live:     https://api-fxtrade.oanda.com

Auth: Bearer <API token> from OANDA account (Manage API Access)
"""

from __future__ import annotations

from typing import Any, Optional
import requests


class OandaClient:
    """Thin wrapper around OANDA v20 REST endpoints used by ExecutionAgent."""

    PRACTICE_URL = "https://api-fxpractice.oanda.com"
    LIVE_URL = "https://api-fxtrade.oanda.com"

    def __init__(
        self,
        api_key: str,
        account_id: str,
        environment: str = "practice",
        timeout: float = 15.0,
    ):
        self.api_key = (api_key or "").strip()
        self.account_id = (account_id or "").strip()
        env = (environment or "practice").lower().strip()
        if env in ("live", "fxtrade", "real"):
            self.base_url = self.LIVE_URL
            self.environment = "live"
        else:
            self.base_url = self.PRACTICE_URL
            self.environment = "practice"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept-Datetime-Format": "RFC3339",
            }
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.account_id)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "ok": False,
                "error": "OANDA API key หรือ account_id ยังไม่ถูกตั้งค่า",
                "status_code": 0,
                "data": None,
            }
        try:
            resp = self.session.request(
                method, self._url(path), timeout=self.timeout, **kwargs
            )
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            if resp.status_code >= 400:
                err = data.get("errorMessage") or data.get("message") or str(data)
                return {"ok": False, "error": err, "status_code": resp.status_code, "data": data}
            return {"ok": True, "error": None, "status_code": resp.status_code, "data": data}
        except requests.RequestException as e:
            return {"ok": False, "error": f"network error: {e}", "status_code": 0, "data": None}

    def get_accounts(self) -> dict[str, Any]:
        return self._request("GET", "/v3/accounts")

    def get_account_summary(self) -> dict[str, Any]:
        return self._request("GET", f"/v3/accounts/{self.account_id}/summary")

    def test_connection(self) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "success": False,
                "message": "ขาด OANDA_API_KEY หรือ OANDA_ACCOUNT_ID",
                "environment": self.environment,
            }
        accounts = self.get_accounts()
        if not accounts["ok"]:
            return {
                "success": False,
                "message": f"API key ไม่ผ่าน: {accounts['error']}",
                "environment": self.environment,
                "status_code": accounts["status_code"],
            }
        summary = self.get_account_summary()
        if not summary["ok"]:
            return {
                "success": False,
                "message": f"account_id ไม่ผ่าน: {summary['error']}",
                "environment": self.environment,
                "status_code": summary["status_code"],
            }
        acc = (summary["data"] or {}).get("account", {})
        return {
            "success": True,
            "message": "เชื่อมต่อ OANDA สำเร็จ",
            "environment": self.environment,
            "account_id": acc.get("id", self.account_id),
            "currency": acc.get("currency"),
            "balance": acc.get("balance"),
            "nav": acc.get("NAV"),
            "open_trade_count": acc.get("openTradeCount"),
            "margin_available": acc.get("marginAvailable"),
        }

    def get_pricing(self, instruments: list[str]) -> dict[str, Any]:
        params = {"instruments": ",".join(instruments)}
        return self._request(
            "GET", f"/v3/accounts/{self.account_id}/pricing", params=params
        )

    @staticmethod
    def to_oanda_instrument(symbol: str) -> str:
        s = symbol.upper().replace("/", "_").replace("-", "_")
        if s == "XAUUSD":
            return "XAU_USD"
        if s == "XAGUSD":
            return "XAG_USD"
        if "_" not in s and len(s) == 6:
            return f"{s[:3]}_{s[3:]}"
        return s

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        client_comment: str = "XAUUSD-MultiAgent",
    ) -> dict[str, Any]:
        instrument = self.to_oanda_instrument(instrument)
        units_str = str(int(units)) if float(units).is_integer() else f"{units:.2f}"
        order: dict[str, Any] = {
            "type": "MARKET",
            "instrument": instrument,
            "units": units_str,
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "clientExtensions": {"comment": client_comment[:128], "tag": "multi-agent"},
        }
        if stop_loss is not None and stop_loss > 0:
            order["stopLossOnFill"] = {"price": f"{stop_loss:.3f}"}
        if take_profit is not None and take_profit > 0:
            order["takeProfitOnFill"] = {"price": f"{take_profit:.3f}"}
        result = self._request(
            "POST", f"/v3/accounts/{self.account_id}/orders", json={"order": order}
        )
        if not result["ok"]:
            return {
                "success": False,
                "ticket": None,
                "message": result["error"],
                "raw": result["data"],
            }
        data = result["data"] or {}
        fill = data.get("orderFillTransaction") or {}
        create = data.get("orderCreateTransaction") or {}
        ticket = fill.get("id") or create.get("id")
        return {
            "success": True,
            "ticket": ticket,
            "message": "order accepted",
            "instrument": instrument,
            "units": units_str,
            "price": fill.get("price"),
            "raw": data,
        }

    def close_trade(self, trade_id: str, units: str = "ALL") -> dict[str, Any]:
        result = self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/trades/{trade_id}/close",
            json={"units": units},
        )
        if not result["ok"]:
            return {"success": False, "message": result["error"], "raw": result["data"]}
        return {"success": True, "message": "trade closed", "raw": result["data"]}

    def list_open_trades(self) -> dict[str, Any]:
        return self._request("GET", f"/v3/accounts/{self.account_id}/openTrades")
