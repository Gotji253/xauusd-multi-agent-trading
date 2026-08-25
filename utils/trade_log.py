"""Structured trade / order cycle logging (stdout + optional file).

Works without loguru so scripts and agents can log in minimal environments.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class TradeLogger:
    """Append-only JSONL + human-readable lines."""

    def __init__(
        self,
        name: str = "trade",
        log_dir: str | Path = "logs",
        also_print: bool = True,
    ):
        self.name = name
        self.also_print = also_print
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.jsonl_path = self.log_dir / f"{name}_{day}.jsonl"
        self.text_path = self.log_dir / f"{name}_{day}.log"

    def _write(self, level: str, event: str, data: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "ts": _ts(),
            "level": level,
            "event": event,
            "data": data or {},
        }
        line_json = json.dumps(payload, ensure_ascii=False, default=str)
        data_s = ""
        if data:
            parts = [f"{k}={v}" for k, v in data.items()]
            data_s = " | " + " ".join(parts)
        line_text = f"{payload['ts']} | {level:<5} | {event}{data_s}"

        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(line_json + "\n")
        with open(self.text_path, "a", encoding="utf-8") as f:
            f.write(line_text + "\n")

        if self.also_print:
            print(f"[LOG {level}] {event}{data_s}")

    def info(self, event: str, **data: Any) -> None:
        self._write("INFO", event, data)

    def warn(self, event: str, **data: Any) -> None:
        self._write("WARN", event, data)

    def error(self, event: str, **data: Any) -> None:
        self._write("ERROR", event, data)

    def log_event(self, event: str, data: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        """Paper/orchestrator helper: log_event(\"SIGNAL_NONE\", record_dict)."""
        payload: dict[str, Any] = {}
        if isinstance(data, dict):
            payload.update(data)
        if kwargs:
            payload.update(kwargs)
        self._write("INFO", event, payload)

    def section(self, title: str) -> None:
        self.info("section", title=title)

    def log_order_result(self, result: dict[str, Any], context: str = "order") -> None:
        """Detailed dump of ExecutionAgent / OCO result."""
        oco = result.get("oco") or {}
        self.info(
            f"{context}.summary",
            success=result.get("success"),
            ticket=result.get("ticket"),
            direction=result.get("direction"),
            quantity=result.get("quantity"),
            mode=result.get("mode"),
            oco_failed=result.get("oco_failed"),
            oco_success=oco.get("success"),
            oco_list_id=result.get("oco_order_list_id") or oco.get("order_list_id"),
            message=result.get("message"),
        )
        if oco:
            self.info(
                f"{context}.oco_detail",
                success=oco.get("success"),
                side=oco.get("side"),
                tp=oco.get("tp_price"),
                sl=oco.get("sl_price"),
                sl_limit=oco.get("sl_limit_price"),
                qty=oco.get("quantity"),
                message=oco.get("message"),
                raw_keys=list((oco.get("raw") or {}).keys()) if isinstance(oco.get("raw"), dict) else None,
            )
        if result.get("oco_failed"):
            self.error(
                f"{context}.oco_failed",
                ticket=result.get("ticket"),
                message=result.get("message"),
                oco_message=oco.get("message"),
            )
        if result.get("success") is False:
            self.error(
                f"{context}.market_failed",
                message=result.get("message"),
                raw=str(result.get("raw") or "")[:300],
            )


# Process-wide helper for agents (optional)
_default: Optional[TradeLogger] = None


def get_trade_logger(name: str = "trade") -> TradeLogger:
    global _default
    if _default is None:
        _default = TradeLogger(name=name)
    return _default
