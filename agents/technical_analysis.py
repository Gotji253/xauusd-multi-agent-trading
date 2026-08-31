"""Technical Analysis Agent — BTCUSDT W1+H4 stack + squeeze_or_pullback both sides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.indicators import ema, rsi, atr, adx
from core.price_action import last_pa_snapshot, combine_h1_h4
from core.ema_squeeze import h4_squeeze_breakout


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
    gate: str = ""
    w1_bias: str = "NEUTRAL"
    conf_buy: float = 0.0
    conf_sell: float = 0.0
    slope_atr: float = 0.0
    adx_h1: float = 0.0
    adx_h4: float = 0.0
    atr_pct: float = 0.0
    min_confluence: float = 0.0
    h1_bias: str = "NEUTRAL"
    pa_buy_score: float = 0.0
    pa_sell_score: float = 0.0
    pa_side: str = "NEUTRAL"
    pa_h4_side: str = "NEUTRAL"
    pa_strength: float = 0.0

    def features(self) -> dict:
        return {
            "conf_buy": round(float(self.conf_buy or 0), 4),
            "conf_sell": round(float(self.conf_sell or 0), 4),
            "slope_atr": round(float(self.slope_atr or 0), 4),
            "adx_h1": round(float(self.adx_h1 or 0), 2),
            "adx_h4": round(float(self.adx_h4 or 0), 2),
            "gate": self.gate or "",
            "pa_side": self.pa_side or "NEUTRAL",
            "pa_strength": round(float(self.pa_strength or 0), 4),
        }


class TechnicalAnalysisAgent:
    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        ema_trend: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        pullback_atr_mult: float = 0.70,
        min_confluence: float = 0.62,
        min_atr: float = 0.5,
        min_atr_pct: float = 0.0006,
        h1_bias_tolerance: float = 0.0015,
        h4_bias_tolerance: float = 0.0020,
        w1_bias_tolerance: float = 0.0030,
        require_h4: bool = True,
        require_w1: bool = False,
        w1_mode: str = "no_oppose",
        adx_period: int = 14,
        min_adx: float = 20.0,
        require_adx: bool = True,
        min_h4_adx: float = 25.0,
        require_h4_adx: bool = True,
        require_momentum: bool = True,
        momentum_slope_bars: int = 1,
        momentum_against_atr: float = 0.5,
        require_pa: bool = False,
        min_pa_score: float = 0.50,
        pa_h4_confirm: bool = True,
        pa_soft_bonus: float = 0.0,
        ema_mid: int = 100,
        require_ema_stack_buy: bool = True,
        ema_stack_bonus: float = 0.20,
        ema_stack_triggers_buy: bool = False,
        squeeze_breakout_bonus: float = 0.15,
        squeeze_pct: float = 0.018,
        primary_buy_mode: str = "squeeze_or_pullback",
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
        self.min_atr_pct = min_atr_pct
        self.h1_bias_tolerance = h1_bias_tolerance
        self.h4_bias_tolerance = h4_bias_tolerance
        self.w1_bias_tolerance = w1_bias_tolerance
        self.require_h4 = require_h4
        self.require_w1 = require_w1
        self.w1_mode = w1_mode
        self.adx_period = adx_period
        self.min_adx = min_adx
        self.require_adx = require_adx
        self.min_h4_adx = min_h4_adx
        self.require_h4_adx = require_h4_adx
        self.require_momentum = require_momentum
        self.momentum_slope_bars = momentum_slope_bars
        self.momentum_against_atr = momentum_against_atr
        self.require_pa = require_pa
        self.min_pa_score = min_pa_score
        self.pa_h4_confirm = pa_h4_confirm
        self.pa_soft_bonus = pa_soft_bonus
        self.ema_mid = ema_mid
        self.require_ema_stack_buy = require_ema_stack_buy
        self.ema_stack_bonus = ema_stack_bonus
        self.ema_stack_triggers_buy = ema_stack_triggers_buy
        self.squeeze_breakout_bonus = squeeze_breakout_bonus
        self.squeeze_pct = squeeze_pct
        self.primary_buy_mode = (primary_buy_mode or "squeeze_or_pullback").lower()

    def analyze(self, df_m15, df_h1, df_h4=None, df_w1=None):
        if df_m15 is None or len(df_m15) < max(self.ema_trend, 60):
            return self._none_signal("M15 insufficient", gate="DATA")
        if df_h1 is None or len(df_h1) < max(self.ema_trend, 60):
            return self._none_signal("H1 insufficient", gate="DATA")
        if self.require_h4 and (df_h4 is None or len(df_h4) < 60):
            return self._none_signal("H4 insufficient", gate="DATA")

        m15 = df_m15.copy()
        h1 = df_h1.copy()
        m15["ema_fast"] = ema(m15["close"], self.ema_fast)
        m15["ema_slow"] = ema(m15["close"], self.ema_slow)
        m15["rsi"] = rsi(m15["close"], self.rsi_period)
        m15["atr"] = atr(m15["high"], m15["low"], m15["close"], self.atr_period)
        h1["ema_fast"] = ema(h1["close"], self.ema_fast)
        h1["ema_slow"] = ema(h1["close"], self.ema_slow)
        h1["ema_trend"] = ema(h1["close"], self.ema_trend)
        h1["atr"] = atr(h1["high"], h1["low"], h1["close"], self.atr_period)

        last = m15.iloc[-1]
        prev = m15.iloc[-2]
        last_h1 = h1.iloc[-1]
        entry_price = float(last["close"])
        current_atr = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
        current_rsi = float(last["rsi"]) if not pd.isna(last["rsi"]) else 50.0
        atr_pct = current_atr / entry_price if entry_price > 0 else 0.0
        if current_atr < self.min_atr or atr_pct < self.min_atr_pct:
            return self._none_signal("ATR too low", gate="ATR")

        h1["adx"] = adx(h1["high"], h1["low"], h1["close"], self.adx_period)
        current_adx = float(h1["adx"].iloc[-1]) if not pd.isna(h1["adx"].iloc[-1]) else 0.0
        if self.require_adx and current_adx < self.min_adx:
            return self._none_signal(f"ADX H1 {current_adx:.1f}", gate="ADX")

        current_h4_adx = 0.0
        if self.require_h4_adx:
            h4_adx_s = adx(df_h4["high"], df_h4["low"], df_h4["close"], self.adx_period)
            current_h4_adx = float(h4_adx_s.iloc[-1]) if not pd.isna(h4_adx_s.iloc[-1]) else 0.0
            if current_h4_adx < self.min_h4_adx:
                return self._none_signal(f"ADX H4 {current_h4_adx:.1f}", gate="ADX_H4")

        w1_bias = self._compute_tf_bias(df_w1, self.w1_bias_tolerance, min_bars=30)
        h4_bias = self._compute_tf_bias(df_h4, self.h4_bias_tolerance, min_bars=60) if df_h4 is not None else "NEUTRAL"
        h1_bias = self._get_bias(last_h1, self.h1_bias_tolerance)
        if self.require_h4 and h4_bias == "NEUTRAL":
            return self._none_signal(f"H4 NEUTRAL H1={h1_bias} W1={w1_bias}", gate="H4_NEUTRAL", w1_bias=w1_bias)

        stack = self._h4_ema_stack(df_h4)
        squeeze = h4_squeeze_breakout(
            df_h4, ema_fast=self.ema_slow, ema_mid=self.ema_mid, ema_slow=self.ema_trend,
            squeeze_pct=self.squeeze_pct, adx_period=self.adx_period,
        )
        stack.update(squeeze)
        buy_score, buy_reasons = self._score_buy(last, prev, h1_bias, h4_bias, current_atr, w1_bias, stack)
        sell_score, sell_reasons = self._score_sell(last, prev, h1_bias, h4_bias, current_atr, w1_bias, stack)
        if squeeze.get("breakout_buy") and self.squeeze_breakout_bonus > 0:
            buy_score += self.squeeze_breakout_bonus
            buy_reasons.append("H4 squeeze-BO")
        if squeeze.get("breakout_sell") and self.squeeze_breakout_bonus > 0:
            sell_score += self.squeeze_breakout_bonus
            sell_reasons.append("H4 squeeze-BD")
        if squeeze.get("breakout_buy") and h4_bias != "BEARISH" and buy_score < self.min_confluence:
            buy_score = self.min_confluence
            buy_reasons.append("squeeze-BO trigger")
        if squeeze.get("breakout_sell") and h4_bias != "BULLISH" and sell_score < self.min_confluence:
            sell_score = self.min_confluence
            sell_reasons.append("squeeze-BD trigger")
        if self.ema_stack_triggers_buy and stack.get("above") and h4_bias != "BEARISH" and buy_score < self.min_confluence:
            buy_score = self.min_confluence

        primary_bias = h4_bias if self.require_h4 else h1_bias
        slope_atr = self._close_slope_atr(h1, bars=self.momentum_slope_bars)

        if buy_score >= self.min_confluence and buy_score > sell_score and primary_bias == "BULLISH":
            ok, why = self._primary_buy_ok(last, current_atr, squeeze)
            if not ok:
                return self._none_signal(f"SETUP {why}", gate="SETUP", w1_bias=w1_bias)
            if self.require_w1 and not self._w1_allows("BUY", w1_bias):
                return self._none_signal(f"W1 block BUY {w1_bias}", gate="W1_BLOCK", w1_bias=w1_bias)
            if self.require_momentum and slope_atr < -self.momentum_against_atr:
                return self._none_signal(f"MOM block BUY {slope_atr:+.2f}", gate="MOM", w1_bias=w1_bias)
            return Signal("BUY", round(min(buy_score, 1.0), 2), entry_price, round(current_atr, 4),
                          " | ".join(buy_reasons + [f"W1={w1_bias}"]), primary_bias, round(current_rsi, 1),
                          float(last["ema_fast"]), float(last["ema_slow"]), "", w1_bias)

        if sell_score >= self.min_confluence and sell_score > buy_score and primary_bias == "BEARISH":
            ok, why = self._primary_sell_ok(last, current_atr, squeeze)
            if not ok:
                return self._none_signal(f"SETUP {why}", gate="SETUP", w1_bias=w1_bias)
            if self.require_w1 and not self._w1_allows("SELL", w1_bias):
                return self._none_signal(f"W1 block SELL {w1_bias}", gate="W1_BLOCK", w1_bias=w1_bias)
            if self.require_momentum and slope_atr > self.momentum_against_atr:
                return self._none_signal(f"MOM block SELL {slope_atr:+.2f}", gate="MOM", w1_bias=w1_bias)
            return Signal("SELL", round(min(sell_score, 1.0), 2), entry_price, round(current_atr, 4),
                          " | ".join(sell_reasons + [f"W1={w1_bias}"]), primary_bias, round(current_rsi, 1),
                          float(last["ema_fast"]), float(last["ema_slow"]), "", w1_bias)

        gate = "CONF"
        if buy_score >= self.min_confluence and primary_bias != "BULLISH":
            gate = "H4_MISALIGN"
        elif sell_score >= self.min_confluence and primary_bias != "BEARISH":
            gate = "H4_MISALIGN"
        return self._none_signal(
            f"no confluence B={buy_score:.2f} S={sell_score:.2f} H4={h4_bias}", gate=gate, w1_bias=w1_bias
        )

    def _primary_buy_ok(self, last, atr_val: float, squeeze: dict) -> tuple[bool, str]:
        mode = self.primary_buy_mode
        if mode in ("", "off", "any"):
            return True, "any"
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        rsi_val = float(last["rsi"])
        pullback = abs(close - ema20) < float(atr_val) * self.pullback_atr_mult and close > ema20
        if squeeze.get("breakout_buy"):
            return True, "squeeze_breakout"
        if pullback and rsi_val <= 58:
            return True, "h1_pullback"
        return False, "need squeeze-BO or H1 pullback"

    def _primary_sell_ok(self, last, atr_val: float, squeeze: dict) -> tuple[bool, str]:
        mode = self.primary_buy_mode
        if mode in ("", "off", "any"):
            return True, "any"
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        rsi_val = float(last["rsi"])
        pullback = abs(close - ema20) < float(atr_val) * self.pullback_atr_mult and close < ema20
        if squeeze.get("breakout_sell"):
            return True, "squeeze_breakdown"
        if pullback and rsi_val >= 42:
            return True, "h1_pullback"
        return False, "need squeeze-BD or H1 pullback"

    def _h4_ema_stack(self, df_h4) -> dict:
        out = {"above": False, "below": False, "aligned": False, "aligned_down": False,
               "ema50": 0.0, "ema100": 0.0, "ema200": 0.0}
        if df_h4 is None or len(df_h4) < max(60, self.ema_trend):
            return out
        close = float(df_h4["close"].iloc[-1])
        e50 = float(ema(df_h4["close"], self.ema_slow).iloc[-1])
        e100 = float(ema(df_h4["close"], self.ema_mid).iloc[-1])
        e200 = float(ema(df_h4["close"], self.ema_trend).iloc[-1])
        if any(pd.isna(x) for x in (e50, e100, e200)):
            return out
        out.update(ema50=e50, ema100=e100, ema200=e200)
        out["above"] = close > e50 and close > e100 and close > e200
        out["below"] = close < e50 and close < e100 and close < e200
        out["aligned"] = e50 > e100 > e200
        out["aligned_down"] = e50 < e100 < e200
        return out

    def _close_slope_atr(self, h1: pd.DataFrame, bars: int = 1) -> float:
        if h1 is None or len(h1) < bars + 2:
            return 0.0
        close_now = float(h1["close"].iloc[-1])
        close_prev = float(h1["close"].iloc[-(bars + 1)])
        atr_val = float(h1["atr"].iloc[-1]) if "atr" in h1.columns and not pd.isna(h1["atr"].iloc[-1]) else 0.0
        if atr_val <= 0:
            try:
                atr_val = float(atr(h1["high"], h1["low"], h1["close"], self.atr_period).iloc[-1])
            except Exception:
                return 0.0
        if atr_val <= 0:
            return 0.0
        return (close_now - close_prev) / atr_val

    def _get_bias(self, last_bar, tolerance: float) -> str:
        close = float(last_bar["close"])
        ema50 = float(last_bar["ema_slow"])
        ema200 = float(last_bar["ema_trend"])
        if pd.isna(ema50) or pd.isna(ema200):
            return "NEUTRAL"
        if close > ema50 * (1.0 + tolerance) and ema50 > ema200:
            return "BULLISH"
        if close < ema50 * (1.0 - tolerance) and ema50 < ema200:
            return "BEARISH"
        return "NEUTRAL"

    def _compute_tf_bias(self, df_tf, tolerance: float, min_bars: int = 30) -> str:
        if df_tf is None or len(df_tf) < min_bars:
            return "NEUTRAL"
        tf = df_tf.copy()
        if len(tf) >= self.ema_trend:
            tf["ema_slow"] = ema(tf["close"], self.ema_slow)
            tf["ema_trend"] = ema(tf["close"], self.ema_trend)
        else:
            tf["ema_slow"] = ema(tf["close"], self.ema_fast)
            tf["ema_trend"] = ema(tf["close"], self.ema_slow)
        return self._get_bias(tf.iloc[-1], tolerance)

    def _w1_allows(self, direction: str, w1_bias: str) -> bool:
        if not self.require_w1:
            return True
        mode = (self.w1_mode or "no_oppose").lower()
        if mode == "align":
            return w1_bias == ("BULLISH" if direction == "BUY" else "BEARISH")
        if direction == "BUY" and w1_bias == "BEARISH":
            return False
        if direction == "SELL" and w1_bias == "BULLISH":
            return False
        return True

    def _score_buy(self, last, prev, h1_bias, h4_bias, atr_val, w1_bias="NEUTRAL", stack=None):
        score, reasons = 0.0, []
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        ema50 = float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val
        stack = stack or {}
        if stack.get("above"):
            score += self.ema_stack_bonus
            reasons.append("H4 px>EMA stack")
        if stack.get("aligned"):
            score += 0.08
            reasons.append("ribbon 50>100>200")
        if h4_bias == "BULLISH":
            score += 0.30
            reasons.append("H4 Bullish")
        if w1_bias == "BULLISH":
            score += 0.08
        if h1_bias == "BULLISH":
            score += 0.18
        if close > ema20:
            score += 0.10
        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close > ema20:
            score += 0.16
            reasons.append("Pullback EMA20")
        if prev_rsi < self.rsi_oversold and rsi_val > prev_rsi and rsi_val < 55:
            score += 0.18
        elif 40 <= rsi_val <= 58:
            score += 0.06
        if ema20 > ema50:
            score += 0.08
        return score, reasons

    def _score_sell(self, last, prev, h1_bias, h4_bias, atr_val, w1_bias="NEUTRAL", stack=None):
        score, reasons = 0.0, []
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        ema50 = float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val
        stack = stack or {}
        if stack.get("below"):
            score += self.ema_stack_bonus
            reasons.append("H4 px<EMA stack")
        if stack.get("aligned_down"):
            score += 0.08
            reasons.append("ribbon 50<100<200")
        if h4_bias == "BEARISH":
            score += 0.30
            reasons.append("H4 Bearish")
        if w1_bias == "BEARISH":
            score += 0.08
        if h1_bias == "BEARISH":
            score += 0.18
        if close < ema20:
            score += 0.10
        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close < ema20:
            score += 0.16
        if prev_rsi > self.rsi_overbought and rsi_val < prev_rsi and rsi_val > 45:
            score += 0.18
        if ema20 < ema50:
            score += 0.08
        return score, reasons

    def _none_signal(self, reason, gate="DATA", w1_bias="NEUTRAL"):
        return Signal("NONE", 0.0, 0.0, 0.0, reason, "NEUTRAL", gate=gate, w1_bias=w1_bias)

    def prepare_dataframe(self, df):
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.ema_fast)
        out["ema_slow"] = ema(out["close"], self.ema_slow)
        out["ema_trend"] = ema(out["close"], self.ema_trend)
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out["high"], out["low"], out["close"], self.atr_period)
        return out
