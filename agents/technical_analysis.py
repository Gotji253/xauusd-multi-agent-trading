"""Technical Analysis Agent for XAUUSD.

วิเคราะห์แนวโน้ม Multi-timeframe, Indicators (EMA, RSI, ATR) และ Price Action
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    direction: str  # "BUY" | "SELL" | "NONE"
    strength: float  # 0.0 - 1.0
    entry_price: float
    atr: float
    reason: str
    timeframe_bias: str = "NEUTRAL"


class TechnicalAnalysisAgent:
    """วิเคราะห์ข้อมูลราคาและสร้าง Trading Signal คุณภาพสูง"""

    def __init__(self, ema_fast: int = 20, ema_slow: int = 50, ema_trend: int = 200, rsi_period: int = 14, atr_period: int = 14):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.rsi_period = rsi_period
        self.atr_period = atr_period

    def analyze(self, df_m15: pd.DataFrame, df_h1: pd.DataFrame, df_h4: Optional[pd.DataFrame] = None) -> Signal:
        """สร้าง Signal จาก Multi-timeframe analysis"""
        # TODO: Implement full logic (Phase 2)
        # Placeholder เพื่อให้โครงสร้างพร้อมและผ่าน CI
        return Signal(
            direction="NONE",
            strength=0.0,
            entry_price=0.0,
            atr=0.0,
            reason="Skeleton - รอ implement logic จริง",
            timeframe_bias="NEUTRAL",
        )

    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
