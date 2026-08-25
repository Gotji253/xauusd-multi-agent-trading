"""Persistent runtime state for order safety (idempotency + position tracking).

Stored as JSON so the bot can recover after restart without redis.
Default path: logs/runtime_state.json
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RuntimeState:
    """Thread-safe JSON state: sent order keys, open tickets, OCO ids."""

    def __init__(self, path: str | Path | None = None):
        root = Path(__file__).resolve().parent.parent
        self.path = Path(path) if path else root / "logs" / "runtime_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._default()
        self.load()

    @staticmethod
    def _default() -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": None,
            "sent_orders": {},
            "open_positions": {},
            "last_cycle": {},
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self._data = self._default()
                return dict(self._data)
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raw = {}
            except (json.JSONDecodeError, OSError):
                raw = {}
            data = self._default()
            data.update({k: v for k, v in raw.items() if k in data or k in raw})
            for k, v in self._default().items():
                if k not in data:
                    data[k] = v
            if not isinstance(data.get("sent_orders"), dict):
                data["sent_orders"] = {}
            if not isinstance(data.get("open_positions"), dict):
                data["open_positions"] = {}
            self._data = data
            return dict(self._data)

    def save(self) -> None:
        with self._lock:
            self._data["updated_at"] = _utc_now()
            payload = json.dumps(self._data, ensure_ascii=False, indent=2, default=str)
            fd, tmp = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=".runtime_state_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, self.path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, default=str))

    @staticmethod
    def make_order_key(
        symbol: str,
        direction: str,
        strategy: str,
        bar_ts: str | None = None,
        extra: str = "",
    ) -> str:
        parts = [
            (symbol or "").upper(),
            (direction or "").upper(),
            (strategy or "NA").upper(),
            str(bar_ts or "NA"),
            str(extra or ""),
        ]
        return "|".join(parts)

    @staticmethod
    def to_client_order_id(order_key: str, prefix: str = "MA") -> str:
        import hashlib
        import re

        raw = f"{prefix}-{order_key}"
        safe = re.sub(r"[^a-zA-Z0-9-_]", "", raw.replace("|", "-").replace(":", ""))
        if len(safe) <= 36:
            return safe or prefix
        digest = hashlib.sha1(order_key.encode("utf-8")).hexdigest()[:10]
        head = safe[: 36 - 1 - len(digest)]
        return f"{head}-{digest}"[:36]

    def has_sent(self, order_key: str) -> bool:
        with self._lock:
            return order_key in (self._data.get("sent_orders") or {})

    def get_sent(self, order_key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return dict((self._data.get("sent_orders") or {}).get(order_key) or {}) or None

    def mark_sent(
        self,
        order_key: str,
        *,
        ticket: Any = None,
        oco_id: Any = None,
        symbol: str = "",
        direction: str = "",
        quantity: float = 0.0,
        status: str = "",
        message: str = "",
    ) -> None:
        with self._lock:
            sent = self._data.setdefault("sent_orders", {})
            sent[order_key] = {
                "at": _utc_now(),
                "ticket": ticket,
                "oco_id": oco_id,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "status": status,
                "message": message,
            }
            if len(sent) > 500:
                keys = sorted(sent.keys(), key=lambda k: sent[k].get("at") or "")
                for k in keys[: len(sent) - 500]:
                    sent.pop(k, None)
        self.save()

    def clear_sent(self, order_key: str) -> None:
        with self._lock:
            (self._data.get("sent_orders") or {}).pop(order_key, None)
        self.save()

    def set_open_position(
        self,
        symbol: str,
        *,
        direction: str,
        quantity: float,
        ticket: Any = None,
        oco_id: Any = None,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        strategy: str = "",
        protected: bool = False,
    ) -> None:
        symbol = (symbol or "").upper()
        with self._lock:
            self._data.setdefault("open_positions", {})[symbol] = {
                "at": _utc_now(),
                "direction": direction,
                "quantity": quantity,
                "ticket": ticket,
                "oco_id": oco_id,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "strategy": strategy,
                "protected": bool(protected),
            }
        self.save()

    def get_open_position(self, symbol: str) -> Optional[dict[str, Any]]:
        symbol = (symbol or "").upper()
        with self._lock:
            pos = (self._data.get("open_positions") or {}).get(symbol)
            return dict(pos) if pos else None

    def clear_open_position(self, symbol: str) -> None:
        symbol = (symbol or "").upper()
        with self._lock:
            (self._data.get("open_positions") or {}).pop(symbol, None)
        self.save()

    def list_unprotected(self) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for sym, pos in (self._data.get("open_positions") or {}).items():
                if pos and not pos.get("protected"):
                    row = dict(pos)
                    row["symbol"] = sym
                    out.append(row)
            return out

    def set_last_cycle(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._data["last_cycle"] = {
                "at": _utc_now(),
                **{k: v for k, v in payload.items() if k != "at"},
            }
        self.save()


_state: Optional[RuntimeState] = None


def get_runtime_state(path: str | Path | None = None) -> RuntimeState:
    global _state
    if _state is None or (path is not None and Path(path) != _state.path):
        _state = RuntimeState(path=path)
    return _state
