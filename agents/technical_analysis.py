"""Technical Analysis Agent for XAUUSD.

Multi-timeframe analysis with stricter confluence for higher signal quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.indicators import ema, rsi, atr


@dataclass
class Signal:
    direction: str
    strength: float
    entry_price: float
    atr: float
    reason: str
    timeframe_bias: str = "NEUTRAL"
    rsi_value: float = 50.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0


class TechnicalAnalysisAgent:
    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        rsi_oversold: float = 32.0,
        rsi_overbought: float = 68.0,
        pullback_atr_mult: float = 0.5,
        min_confluence: float = 0.62,
        min_atr: float = 1.5,
    ):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.pullback_atr_mult = pullback_atr_mult
        self.min_confluence = min_confluence
        self.min_atr = min_atr

    def analyze(self, df_m15, df_h1, df_h4=None):
        if df_m15 is None or len(df_m15) < max(self.ema_trend, 60):
            return self._none_signal("ข้อมูล M15 ไม่เพียงพอ")
        if df_h1 is None or len(df_h1) < max(self.ema_trend, 60):
            return self._none_signal("ข้อมูล H1 ไม่เพียงพอ")

        m15 = df_m15.copy()
        h1 = df_h1.copy()
        m15["ema_fast"] = ema(m15["close"], self.ema_fast)
        m15["ema_slow"] = ema(m15["close"], self.ema_slow)
        m15["rsi"] = rsi(m15["close"], self.rsi_period)
        m15["atr"] = atr(m15["high"], m15["low"], m15["close"], self.atr_period)
        h1["ema_fast"] = ema(h1["close"], self.ema_fast)
        h1["ema_slow"] = ema(h1["close"], self.ema_slow)
        h1["ema_trend"] = ema(h1["close"], self.ema_trend)

        last = m15.iloc[-1]
        prev = m15.iloc[-2]
        last_h1 = h1.iloc[-1]
        entry_price = float(last["close"])
        current_atr = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
        current_rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50.0

        if current_atr < self.min_atr:
            return self._none_signal(f"ATR ต่ำเกินไป ({current_atr:.2f} < {self.min_atr})")

        h1_bias = self._get_h1_bias(last_h1)
        buy_score, buy_reasons = self._score_buy(last, prev, h1_bias, current_atr)
        sell_score, sell_reasons = self._score_sell(last, prev, h1_bias, current_atr)

        if buy_score >= self.min_confluence and buy_score > sell_score and h1_bias == "BULLISH":
            return Signal("BUY", round(min(buy_score, 1.0), 2), entry_price, round(current_atr, 2), " | ".join(buy_reasons), h1_bias, round(current_rsi, 1), float(last["ema_fast"]), float(last["ema_slow"]))
        if sell_score >= self.min_confluence and sell_score > buy_score and h1_bias == "BEARISH":
            return Signal("SELL", round(min(sell_score, 1.0), 2), entry_price, round(current_atr, 2), " | ".join(sell_reasons), h1_bias, round(current_rsi, 1), float(last["ema_fast"]), float(last["ema_slow"]))

        return Signal("NONE", 0.0, entry_price, round(current_atr, 2), f"ไม่มี confluence (Buy={buy_score:.2f}, Sell={sell_score:.2f}, Bias={h1_bias}, min={self.min_confluence})", h1_bias, round(current_rsi, 1), float(last["ema_fast"]), float(last["ema_slow"]))

    def _get_h1_bias(self, last_h1):
        close = float(last_h1["close"])
        ema50 = float(last_h1["ema_slow"])
        ema200 = float(last_h1["ema_trend"])
        if pd.isna(ema50) or pd.isna(ema200):
            return "NEUTRAL"
        if close > ema50 * 1.0005 and ema50 > ema200:
            return "BULLISH"
        if close < ema50 * 0.9995 and ema50 < ema200:
            return "BEARISH"
        return "NEUTRAL"

    def _score_buy(self, last, prev, h1_bias, atr_val):
        score, reasons = 0.0, []
        close, ema20, ema50 = float(last["close"]), float(last["ema_fast"]), float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val
        if h1_bias == "BULLISH":
            score += 0.38; reasons.append("H1 Bullish")
        if close > ema20:
            score += 0.14; reasons.append("Close > EMA20")
        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close > ema20:
            score += 0.16; reasons.append("Pullback EMA20")
        if prev_rsi < self.rsi_oversold and rsi_val > prev_rsi and rsi_val < 55:
            score += 0.22; reasons.append(f"RSI recovery ({prev_rsi:.0f}->{rsi_val:.0f})")
        elif 42 <= rsi_val <= 58:
            score += 0.06; reasons.append("RSI neutral")
        if ema20 > ema50:
            score += 0.10; reasons.append("EMA20 > EMA50")
        return score, reasons

    def _score_sell(self, last, prev, h1_bias, atr_val):
        score, reasons = 0.0, []
        close, ema20, ema50 = float(last["close"]), float(last["ema_fast"]), float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val
        if h1_bias == "BEARISH":
            score += 0.38; reasons.append("H1 Bearish")
        if close < ema20:
            score += 0.14; reasons.append("Close < EMA20")
        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close < ema20:
            score += 0.16; reasons.append("Pullback EMA20")
        if prev_rsi > self.rsi_overbought and rsi_val < prev_rsi and rsi_val > 45:
            score += 0.22; reasons.append(f"RSI rejection ({prev_rsi:.0f}->{rsi_val:.0f})")
        elif 42 <= rsi_val <= 58:
            score += 0.06; reasons.append("RSI neutral")
        if ema20 < ema50:
            score += 0.10; reasons.append("EMA20 < EMA50")
        return score, reasons

    def _none_signal(self, reason):
        return Signal("NONE", 0.0, 0.0, 0.0, reason, "NEUTRAL")

    def prepare_dataframe(self, df):
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.ema_fast)
        out["ema_slow"] = ema(out["close"], self.ema_slow)
        out["ema_trend"] = ema(out["close"], self.ema_trend)
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out["high"], out["low"], out["close"], self.atr_period)
        return out
