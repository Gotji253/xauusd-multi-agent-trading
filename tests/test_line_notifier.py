"""Tests for LINE Thai Notifier (mock mode)."""

from __future__ import annotations

from agents.line_notifier import LineNotifierAgent


def test_notify_open_order_mock(capsys):
    notifier = LineNotifierAgent(channel_access_token="", user_id="")  # mock mode
    success = notifier.notify_open_order(
        direction="BUY",
        symbol="XAUUSD",
        entry_price=2654.80,
        lot_size=0.12,
        stop_loss=2648.20,
        take_profit=2666.50,
        risk_percent=0.0075,
        rr=1.77,
        reason="H1 Bullish + M15 Pullback",
    )
    assert success is True
    captured = capsys.readouterr()
    assert "เปิด BUY XAUUSD" in captured.out
    assert "2654.80" in captured.out


def test_notify_close_order_mock(capsys):
    notifier = LineNotifierAgent()
    success = notifier.notify_close_order(
        direction="SELL",
        symbol="XAUUSD",
        pnl=87.40,
        r_multiple=1.12,
        duration="2 ชม. 18 นาที",
        equity=12450.30,
    )
    assert success is True
    captured = capsys.readouterr()
    assert "ปิด SELL" in captured.out
    assert "87.40" in captured.out
