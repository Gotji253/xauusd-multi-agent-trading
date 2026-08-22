"""Pytest fixtures — Mock MetaTrader5 ทั้งหมดเพื่อให้รันบน CI ได้"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """สร้างข้อมูล OHLCV จำลองสำหรับทดสอบ"""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2025-01-01", periods=n, freq="15min")
    close = 2650 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 2
    low = close - np.random.rand(n) * 2
    open_ = close + np.random.randn(n) * 0.3
    volume = np.random.randint(100, 1000, n)

    return pd.DataFrame(
        {
            "time": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": volume,
        }
    )


@pytest.fixture
def mock_mt5(monkeypatch):
    """Mock ตัว MetaTrader5 package ทั้งหมด"""
    mock = MagicMock()
    mock.initialize.return_value = True
    mock.shutdown.return_value = None
    mock.account_info.return_value = MagicMock(
        balance=10000.0,
        equity=10000.0,
        margin=0.0,
        margin_free=10000.0,
    )
    mock.symbol_info_tick.return_value = MagicMock(bid=2650.50, ask=2650.80)
    mock.last_error.return_value = (0, "Success")

    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", mock)
    return mock
