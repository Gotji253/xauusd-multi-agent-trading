"""Tests for OANDA helpers and ExecutionAgent mock mode."""

from __future__ import annotations

from core.oanda_client import OandaClient
from agents.execution import ExecutionAgent


def test_instrument_mapping():
    assert OandaClient.to_oanda_instrument("XAUUSD") == "XAU_USD"
    assert OandaClient.to_oanda_instrument("XAU_USD") == "XAU_USD"
    assert OandaClient.to_oanda_instrument("EURUSD") == "EUR_USD"


def test_client_not_configured():
    c = OandaClient(api_key="", account_id="")
    assert c.is_configured is False
    assert c.test_connection()["success"] is False


def test_execution_mock_place_order():
    agent = ExecutionAgent(oanda_client=None, mode="mock")
    r = agent.place_order("XAU_USD", "BUY", 1.0, 2500.0, 2600.0)
    assert r["success"] is True
    assert r["mode"] == "mock"


def test_execution_mock_sell_units_sign():
    agent = ExecutionAgent(mode="mock", default_units_scale=1.0)
    r = agent.place_order("XAUUSD", "SELL", 2.0, 2600.0, 2500.0)
    assert r["success"] is True
    assert r["units"] == -2.0


def test_execution_auto_without_key_is_mock():
    client = OandaClient(api_key="", account_id="")
    agent = ExecutionAgent(oanda_client=client, mode="auto")
    assert agent.mode == "mock"
