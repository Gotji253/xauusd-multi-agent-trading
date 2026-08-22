"""Tests for Binance client helpers and ExecutionAgent binance/mock modes."""

from __future__ import annotations

from core.binance_client import BinanceClient
from agents.execution import ExecutionAgent


def test_symbol_mapping():
    assert BinanceClient.to_binance_symbol("BTC") == "BTCUSDT"
    assert BinanceClient.to_binance_symbol("BTCUSDT") == "BTCUSDT"
    assert BinanceClient.to_binance_symbol("btc/usdt") == "BTCUSDT"


def test_client_not_configured():
    c = BinanceClient(api_key="", api_secret="")
    assert c.is_configured is False
    r = c.test_connection()
    assert r["success"] is False


def test_execution_auto_prefers_binance():
    b = BinanceClient(api_key="k", api_secret="s", environment="testnet")
    agent = ExecutionAgent(binance_client=b, mode="auto")
    assert agent.mode == "binance"


def test_execution_mock_btc_order():
    agent = ExecutionAgent(mode="mock", default_units_scale=0.001)
    r = agent.place_order("BTCUSDT", "BUY", 1.0)
    assert r["success"] is True
    assert r["mode"] == "mock"
    assert r["quantity"] == 0.001


def test_execution_mock_sell():
    agent = ExecutionAgent(mode="mock", default_units_scale=0.002)
    r = agent.place_order("BTCUSDT", "SELL", 1.0)
    assert r["success"] is True
    assert r["direction"] == "SELL"
    assert r["quantity"] == 0.002
