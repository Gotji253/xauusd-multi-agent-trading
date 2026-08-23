"""Unit tests for Binance qty/price formatting and OCO validation helpers."""

from __future__ import annotations

from core.binance_client import BinanceClient


def test_fmt_qty_rounds_down():
    assert BinanceClient._fmt_qty(0.001234, "0.00001") == "0.00123"
    assert BinanceClient._fmt_qty(1.0, "0.001") == "1"


def test_fmt_price_two_decimals_default():
    assert BinanceClient._fmt_price(97500.129, "0.01") == "97500.12"


def test_oco_rejects_tp_below_sl():
    c = BinanceClient("k", "s", environment="testnet")
    r = c.place_oco_sell_tp_sl("BTCUSDT", 0.001, take_profit_price=100.0, stop_loss_price=110.0)
    assert r["success"] is False
    assert "take_profit" in r["message"].lower() or "TP" in r["message"] or "สูง" in r["message"]
