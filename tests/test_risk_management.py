"""Unit tests for Risk Management Agent — ส่วนสำคัญที่สุดของระบบ"""

from __future__ import annotations

import pytest

from agents.risk_management import RiskManagementAgent, RiskDecision


@pytest.fixture
def risk_agent() -> RiskManagementAgent:
    return RiskManagementAgent(
        risk_per_trade=0.01,          # 1% เพื่อให้คำนวณง่ายใน test
        max_daily_drawdown=0.03,
        max_open_positions=1,
        min_reward_risk=1.5,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=3.0,
    )


def test_approve_valid_buy(risk_agent: RiskManagementAgent):
    decision = risk_agent.calculate(
        equity=10000.0,
        entry_price=2650.0,
        direction="BUY",
        atr=10.0,
        current_daily_pnl=0.0,
        open_positions=0,
        point=0.01,
        tick_value=1.0,
    )
    assert isinstance(decision, RiskDecision)
    assert decision.approved is True
    assert decision.lot_size > 0
    assert decision.stop_loss < decision.take_profit
    assert decision.reward_risk_ratio >= 1.5


def test_reject_when_max_positions_reached(risk_agent: RiskManagementAgent):
    decision = risk_agent.calculate(
        equity=10000.0,
        entry_price=2650.0,
        direction="BUY",
        atr=10.0,
        open_positions=1,  # ถึงขีดจำกัดแล้ว
    )
    assert decision.approved is False
    assert "Position" in decision.reason


def test_reject_when_daily_drawdown_exceeded(risk_agent: RiskManagementAgent):
    decision = risk_agent.calculate(
        equity=10000.0,
        entry_price=2650.0,
        direction="SELL",
        atr=10.0,
        current_daily_pnl=-350.0,  # 3.5% > 3%
    )
    assert decision.approved is False
    assert "Drawdown" in decision.reason


def test_reject_invalid_direction(risk_agent: RiskManagementAgent):
    decision = risk_agent.calculate(
        equity=10000.0,
        entry_price=2650.0,
        direction="HOLD",
        atr=10.0,
    )
    assert decision.approved is False


def test_lot_size_scales_with_equity(risk_agent: RiskManagementAgent):
    d1 = risk_agent.calculate(equity=10000.0, entry_price=2650.0, direction="BUY", atr=10.0)
    d2 = risk_agent.calculate(equity=20000.0, entry_price=2650.0, direction="BUY", atr=10.0)
    assert d2.lot_size == pytest.approx(d1.lot_size * 2, rel=0.05)
