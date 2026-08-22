"""Unit tests for Backtest Engine."""

from __future__ import annotations

from backtest.engine import BacktestEngine, generate_synthetic_xauusd, BacktestResult
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent


def test_generate_synthetic():
    m15, h1 = generate_synthetic_xauusd(n_bars=600, seed=1)
    assert len(m15) == 600
    assert len(h1) > 0


def test_backtest_runs_without_error():
    m15, h1 = generate_synthetic_xauusd(n_bars=1200, seed=7)
    engine = BacktestEngine(
        ta_agent=TechnicalAnalysisAgent(min_confluence=0.55, min_atr=0.5),
        risk_agent=RiskManagementAgent(risk_per_trade=0.01, min_reward_risk=1.5),
        initial_equity=10000.0,
        spread_points=20.0,
        slippage_points=3.0,
    )
    result = engine.run(m15, h1, data_source="synthetic-test")
    assert isinstance(result, BacktestResult)
    assert result.initial_equity == 10000.0
    assert len(result.equity_curve) > 0
