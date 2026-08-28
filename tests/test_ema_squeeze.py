from core.ema_squeeze import h4_squeeze_breakout
from agents.technical_analysis import TechnicalAnalysisAgent
import pandas as pd
import numpy as np


def test_squeeze_empty():
    out = h4_squeeze_breakout(None)
    assert out["breakout_buy"] is False


def test_ta_accepts_squeeze_param():
    ta = TechnicalAnalysisAgent(squeeze_breakout_bonus=0.15)
    assert ta.squeeze_breakout_bonus == 0.15


def test_primary_buy_rejects_chase():
    ta = TechnicalAnalysisAgent(primary_buy_mode="squeeze_or_pullback")
    last = pd.Series({"close": 200.0, "ema_fast": 180.0, "rsi": 72.0})
    ok, why = ta._primary_buy_ok(last, atr_val=2.0, squeeze={"breakout_buy": False})
    assert ok is False


def test_primary_buy_allows_squeeze():
    ta = TechnicalAnalysisAgent(primary_buy_mode="squeeze_or_pullback")
    last = pd.Series({"close": 200.0, "ema_fast": 180.0, "rsi": 72.0})
    ok, why = ta._primary_buy_ok(last, atr_val=2.0, squeeze={"breakout_buy": True})
    assert ok is True
    assert why == "squeeze_breakout"
