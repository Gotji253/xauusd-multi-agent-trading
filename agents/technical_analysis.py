"""Technical Analysis Agent — BTCUSDT focused with W1 + H4 bias stack.

Multi-timeframe:
  - W1  = higher-timeframe trend filter (must not fight weekly bias)
  - H4  = primary directional bias for entries (mandatory)
  - H1  = secondary bias / ADX / momentum
  - M15 = entry timing (EMA pullback + RSI recovery)

Indicators: EMA20/50/200, RSI(14), ATR(14), ADX(14)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.indicators import ema, rsi, atr, adx


@dataclass
class Signal:
    direction: str
    strength: float
    entry_price: float
    atr: float
    reason: str
    timeframe_bias: str = "NEUTRAL"  # reports H4 bias when available
    rsi_value: float = 50.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    # Structured gate when direction=NONE — for logging / forward analysis
    # DATA | ATR | ADX | W1_BLOCK | H4_NEUTRAL | H4_MISALIGN | MOM | CONF | NONE
    gate: str = ""
    w1_bias: str = "NEUTRAL"  # weekly higher-TF bias


class TechnicalAnalysisAgent:
    """Signal generator with W1 filter + mandatory H4 trend bias.

    Rules (strict):
      BUY  only if H4 == BULLISH, confluence OK, and W1 is not BEARISH
      SELL only if H4 == BEARISH, confluence OK, and W1 is not BULLISH
      H1 bias is scoring weight; ADX/MOM remain H1 gates
    """

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
        w1_bias_tolerance: float = 0.0030,  # weekly wider tolerance
        require_h4: bool = True,
        # W1 higher-TF filter (2026-08-24): block counter-weekly trades on H4 path
        require_w1: bool = True,
        w1_mode: str = "no_oppose",  # no_oppose | align (align = W1 must match H4)
        # ADX trend-strength filter (H1 primary + optional H4 confirm)
        adx_period: int = 14,
        min_adx: float = 20.0,  # H1 — BTC-tuned; 18~22 WF-tied
        require_adx: bool = True,
        # H4 ADX: confirm higher-TF trend strength (2026-08-24)
        # H4 med≈26; aligned 24h edge improves when H4 ADX≥30–40
        # default 25 = above median-ish, still allows ~53% of H4 bars
        min_h4_adx: float = 25.0,
        require_h4_adx: bool = True,
        # Momentum filter: block entry when short-term slope is strongly against
        # (research 2026-08-24: cs1 thr=0.5 ATR → WF avgPF 1.35 vs base 1.19)
        require_momentum: bool = True,
        momentum_slope_bars: int = 1,   # 1 = cs1, 3 = cs3
        momentum_against_atr: float = 0.5,  # block if slope against > this * ATR
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

    def analyze(self, df_m15, df_h1, df_h4=None, df_w1=None):
        if df_m15 is None or len(df_m15) < max(self.ema_trend, 60):
            return self._none_signal("ข้อมูล M15 ไม่เพียงพอ", gate="DATA")
        if df_h1 is None or len(df_h1) < max(self.ema_trend, 60):
            return self._none_signal("ข้อมูล H1 ไม่เพียงพอ", gate="DATA")

        if self.require_h4:
            # Need at least 60 H4 bars; EMA200 needs ~200 — fallback bias uses EMA20/50 when short
            if df_h4 is None or len(df_h4) < 60:
                return self._none_signal("ข้อมูล H4 ไม่เพียงพอ (บังคับใช้ H4 bias)", gate="DATA")

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

        if current_atr < self.min_atr:
            return self._none_signal(
                f"ATR ต่ำเกินไป ({current_atr:.4f} < {self.min_atr})", gate="ATR"
            )

        atr_pct = current_atr / entry_price if entry_price > 0 else 0.0
        if atr_pct < self.min_atr_pct:
            return self._none_signal(
                f"ATR% ต่ำเกินไป ({atr_pct*100:.3f}% < {self.min_atr_pct*100:.3f}%)",
                gate="ATR",
            )

        # --- ADX trend-strength filter (H1) ---
        h1["adx"] = adx(h1["high"], h1["low"], h1["close"], self.adx_period)
        current_adx = float(h1["adx"].iloc[-1]) if not pd.isna(h1["adx"].iloc[-1]) else 0.0
        if self.require_adx and current_adx < self.min_adx:
            return self._none_signal(
                f"ADX H1 ต่ำ — ไม่มีเทรนด์ชัด ({current_adx:.1f} < {self.min_adx})",
                gate="ADX",
            )

        # --- H4 ADX confirm (higher-TF trend strength) ---
        current_h4_adx = 0.0
        if self.require_h4_adx:
            if df_h4 is None or len(df_h4) < max(30, self.adx_period + 5):
                return self._none_signal(
                    "ข้อมูล H4 ไม่พอคำนวณ ADX H4", gate="DATA"
                )
            h4_adx_s = adx(df_h4["high"], df_h4["low"], df_h4["close"], self.adx_period)
            current_h4_adx = (
                float(h4_adx_s.iloc[-1]) if not pd.isna(h4_adx_s.iloc[-1]) else 0.0
            )
            if current_h4_adx < self.min_h4_adx:
                return self._none_signal(
                    f"ADX H4 ต่ำ — HTF เทรนด์ไม่แรง ({current_h4_adx:.1f} < {self.min_h4_adx})",
                    gate="ADX_H4",
                )

        # --- W1 higher-TF bias (optional hard filter) ---
        w1_bias = self._compute_tf_bias(df_w1, self.w1_bias_tolerance, min_bars=30)

        # --- H4 primary bias (mandatory gate for H4-path entries) ---
        h4_bias = "NEUTRAL"
        if df_h4 is not None and len(df_h4) >= 60:
            h4_bias = self._compute_tf_bias(df_h4, self.h4_bias_tolerance, min_bars=60)
        elif self.require_h4:
            return self._none_signal("H4 bias คำนวณไม่ได้", gate="H4_NEUTRAL", w1_bias=w1_bias)

        h1_bias = self._get_bias(last_h1, self.h1_bias_tolerance)

        # Hard gate: must align with H4 when require_h4=True
        if self.require_h4 and h4_bias == "NEUTRAL":
            return Signal(
                "NONE",
                0.0,
                entry_price,
                round(current_atr, 4),
                f"H4 NEUTRAL — ไม่เข้าไม้ (H1={h1_bias}, W1={w1_bias})",
                h4_bias,
                round(current_rsi, 1),
                float(last["ema_fast"]),
                float(last["ema_slow"]),
                "H4_NEUTRAL",
                w1_bias,
            )

        buy_score, buy_reasons = self._score_buy(
            last, prev, h1_bias, h4_bias, current_atr, w1_bias=w1_bias
        )
        sell_score, sell_reasons = self._score_sell(
            last, prev, h1_bias, h4_bias, current_atr, w1_bias=w1_bias
        )

        primary_bias = h4_bias if self.require_h4 else h1_bias

        # H1 close slope in ATR units (cs1 / cs3) — block catching falling knife
        slope_atr = self._close_slope_atr(h1, bars=self.momentum_slope_bars)

        if (
            buy_score >= self.min_confluence
            and buy_score > sell_score
            and primary_bias == "BULLISH"
        ):
            # W1 filter: do not BUY against weekly bearish (or require align)
            if self.require_w1 and not self._w1_allows("BUY", w1_bias):
                return Signal(
                    "NONE",
                    0.0,
                    entry_price,
                    round(current_atr, 4),
                    f"W1 block BUY (W1={w1_bias}, mode={self.w1_mode}) | H4={h4_bias}",
                    primary_bias,
                    round(current_rsi, 1),
                    float(last["ema_fast"]),
                    float(last["ema_slow"]),
                    "W1_BLOCK",
                    w1_bias,
                )
            if self.require_momentum and slope_atr < -self.momentum_against_atr:
                return Signal(
                    "NONE",
                    0.0,
                    entry_price,
                    round(current_atr, 4),
                    (
                        f"MOM block BUY: H1 slope={slope_atr:+.2f} ATR "
                        f"(thr=-{self.momentum_against_atr}) | " + " | ".join(buy_reasons)
                    ),
                    primary_bias,
                    round(current_rsi, 1),
                    float(last["ema_fast"]),
                    float(last["ema_slow"]),
                    "MOM",
                    w1_bias,
                )
            reasons = list(buy_reasons)
            reasons.append(f"W1={w1_bias}")
            if self.require_momentum:
                reasons.append(f"mom_ok slope={slope_atr:+.2f}")
            return Signal(
                "BUY",
                round(min(buy_score, 1.0), 2),
                entry_price,
                round(current_atr, 4),
                " | ".join(reasons),
                primary_bias,
                round(current_rsi, 1),
                float(last["ema_fast"]),
                float(last["ema_slow"]),
                "",
                w1_bias,
            )
        if (
            sell_score >= self.min_confluence
            and sell_score > buy_score
            and primary_bias == "BEARISH"
        ):
            if self.require_w1 and not self._w1_allows("SELL", w1_bias):
                return Signal(
                    "NONE",
                    0.0,
                    entry_price,
                    round(current_atr, 4),
                    f"W1 block SELL (W1={w1_bias}, mode={self.w1_mode}) | H4={h4_bias}",
                    primary_bias,
                    round(current_rsi, 1),
                    float(last["ema_fast"]),
                    float(last["ema_slow"]),
                    "W1_BLOCK",
                    w1_bias,
                )
            if self.require_momentum and slope_atr > self.momentum_against_atr:
                return Signal(
                    "NONE",
                    0.0,
                    entry_price,
                    round(current_atr, 4),
                    (
                        f"MOM block SELL: H1 slope={slope_atr:+.2f} ATR "
                        f"(thr=+{self.momentum_against_atr}) | " + " | ".join(sell_reasons)
                    ),
                    primary_bias,
                    round(current_rsi, 1),
                    float(last["ema_fast"]),
                    float(last["ema_slow"]),
                    "MOM",
                    w1_bias,
                )
            reasons = list(sell_reasons)
            reasons.append(f"W1={w1_bias}")
            if self.require_momentum:
                reasons.append(f"mom_ok slope={slope_atr:+.2f}")
            return Signal(
                "SELL",
                round(min(sell_score, 1.0), 2),
                entry_price,
                round(current_atr, 4),
                " | ".join(reasons),
                primary_bias,
                round(current_rsi, 1),
                float(last["ema_fast"]),
                float(last["ema_slow"]),
                "",
                w1_bias,
            )

        # Prefer H4_MISALIGN when scores exist but bias blocks; else CONF
        gate = "CONF"
        if self.require_h4 and primary_bias not in ("BULLISH", "BEARISH"):
            gate = "H4_NEUTRAL"
        elif buy_score >= self.min_confluence and primary_bias != "BULLISH":
            gate = "H4_MISALIGN"
        elif sell_score >= self.min_confluence and primary_bias != "BEARISH":
            gate = "H4_MISALIGN"

        return Signal(
            "NONE",
            0.0,
            entry_price,
            round(current_atr, 4),
            (
                f"ไม่มี confluence (Buy={buy_score:.2f}, Sell={sell_score:.2f}, "
                f"H4={h4_bias}, H1={h1_bias}, W1={w1_bias}, min={self.min_confluence}, "
                f"slope={slope_atr:+.2f})"
            ),
            primary_bias,
            round(current_rsi, 1),
            float(last["ema_fast"]),
            float(last["ema_slow"]),
            gate,
            w1_bias,
        )

    def _close_slope_atr(self, h1: pd.DataFrame, bars: int = 1) -> float:
        """(close_now - close_n_bars_ago) / ATR — positive = rising."""
        if h1 is None or len(h1) < bars + 2:
            return 0.0
        close_now = float(h1["close"].iloc[-1])
        close_prev = float(h1["close"].iloc[-(bars + 1)])
        atr_val = float(h1["atr"].iloc[-1]) if "atr" in h1.columns and not pd.isna(h1["atr"].iloc[-1]) else 0.0
        if atr_val <= 0:
            # compute on the fly if missing
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
        """EMA50/200 bias on any HTF frame; short history → EMA20/50 proxy."""
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
        """W1 gate for H4-path entries.

        no_oppose: block only counter-trend vs weekly (NEUTRAL allowed)
        align:     require W1 same side as trade direction
        """
        if not self.require_w1:
            return True
        mode = (self.w1_mode or "no_oppose").lower()
        if mode == "align":
            if direction == "BUY":
                return w1_bias == "BULLISH"
            if direction == "SELL":
                return w1_bias == "BEARISH"
            return False
        # default no_oppose
        if direction == "BUY" and w1_bias == "BEARISH":
            return False
        if direction == "SELL" and w1_bias == "BULLISH":
            return False
        return True

    def _score_buy(self, last, prev, h1_bias, h4_bias, atr_val, w1_bias: str = "NEUTRAL"):
        score, reasons = 0.0, []
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        ema50 = float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val

        # H4 trend alignment (highest weight — already hard-gated, still scores)
        if h4_bias == "BULLISH":
            score += 0.30
            reasons.append("H4 Bullish")

        if w1_bias == "BULLISH":
            score += 0.08
            reasons.append("W1 Bullish")

        if h1_bias == "BULLISH":
            score += 0.18
            reasons.append("H1 Bullish")

        if close > ema20:
            score += 0.10
            reasons.append("Close > EMA20")

        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close > ema20:
            score += 0.16
            reasons.append("Pullback EMA20")

        if prev_rsi < self.rsi_oversold and rsi_val > prev_rsi and rsi_val < 55:
            score += 0.18
            reasons.append(f"RSI recovery ({prev_rsi:.0f}->{rsi_val:.0f})")
        elif 40 <= rsi_val <= 58:
            score += 0.06
            reasons.append("RSI neutral-zone")

        if ema20 > ema50:
            score += 0.08
            reasons.append("EMA20 > EMA50")

        return score, reasons

    def _score_sell(self, last, prev, h1_bias, h4_bias, atr_val, w1_bias: str = "NEUTRAL"):
        score, reasons = 0.0, []
        close = float(last["close"])
        ema20 = float(last["ema_fast"])
        ema50 = float(last["ema_slow"])
        rsi_val = float(last["rsi"])
        prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi_val

        if h4_bias == "BEARISH":
            score += 0.30
            reasons.append("H4 Bearish")

        if w1_bias == "BEARISH":
            score += 0.08
            reasons.append("W1 Bearish")

        if h1_bias == "BEARISH":
            score += 0.18
            reasons.append("H1 Bearish")

        if close < ema20:
            score += 0.10
            reasons.append("Close < EMA20")

        if abs(close - ema20) < atr_val * self.pullback_atr_mult and close < ema20:
            score += 0.16
            reasons.append("Pullback EMA20")

        if prev_rsi > self.rsi_overbought and rsi_val < prev_rsi and rsi_val > 45:
            score += 0.18
            reasons.append(f"RSI rejection ({prev_rsi:.0f}->{rsi_val:.0f})")
        elif 42 <= rsi_val <= 60:
            score += 0.06
            reasons.append("RSI neutral-zone")

        if ema20 < ema50:
            score += 0.08
            reasons.append("EMA20 < EMA50")

        return score, reasons

    def _none_signal(self, reason, gate: str = "DATA", w1_bias: str = "NEUTRAL"):
        return Signal("NONE", 0.0, 0.0, 0.0, reason, "NEUTRAL", gate=gate, w1_bias=w1_bias)

    def prepare_dataframe(self, df):
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.ema_fast)
        out["ema_slow"] = ema(out["close"], self.ema_slow)
        out["ema_trend"] = ema(out["close"], self.ema_trend)
        out["rsi"] = rsi(out["close"], self.rsi_period)
        out["atr"] = atr(out["high"], out["low"], out["close"], self.atr_period)
        return out
