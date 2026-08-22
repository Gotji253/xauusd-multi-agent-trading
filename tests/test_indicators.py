"""Tests for indicator calculations."""

from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from core.indicators import ema, rsi, atr


def test_ema_basic():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = ema(series, period=3)
    assert len(result) == 5
    assert result.iloc[-1] > result.iloc[0]


def test_rsi_range(sample_ohlcv: pd.DataFrame):
    result = rsi(sample_ohlcv["close"], period=14)
    assert result.min() >= 0
    assert result.max() <= 100


def test_atr_positive(sample_ohlcv: pd.DataFrame):
    result = atr(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"], period=14)
    assert (result.dropna() > 0).all()
