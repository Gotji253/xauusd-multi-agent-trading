"""H4 EMA 50/100/200 stack → BUY preference."""

from __future__ import annotations

import numpy as np
import pandas as pd

from agents.technical_analysis import TechnicalAnalysisAgent


def _uptrend_ohlc(n=250, start=100.0):
    close = start * np.exp(np.cumsum(np.full(n, 0.004)))
    high = close * 1.004
    low = close * 0.996
    open_ = np.roll(close, 1)
    open_[0] = start
    idx = pd.date_range("2026-01-01", periods=n, freq="4h")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def test_h4_stack_detects_price_above_emas():
    ta = TechnicalAnalysisAgent()
    h4 = _uptrend_ohlc()
    stack = ta._h4_ema_stack(h4)
    assert stack["above"] is True
    assert stack["aligned"] is True


def test_stack_lifts_buy_score():
    ta = TechnicalAnalysisAgent(ema_stack_bonus=0.20)
    last = pd.Series({"close": 120.0, "ema_fast": 119.0, "ema_slow": 118.0, "rsi": 55.0})
    prev = pd.Series({"rsi": 52.0})
    score_on, _ = ta._score_buy(last, prev, "BULLISH", "BULLISH", 1.0, stack={"above": True, "aligned": True})
    score_off, _ = ta._score_buy(last, prev, "BULLISH", "BULLISH", 1.0, stack={"above": False, "aligned": False})
    assert score_on > score_off
