"""Mean Reversion Agent — Strategy 2 for sideways / low-ADX regimes.

Complementary to Multi-TF Trend Pullback:
  - Trend strategy  → trades when ADX is HIGH (trending)
  - Mean Reversion  → trades when ADX is LOW  (sideways)

Logic (H1 primary):
  Regime gate : ADX(14) < max_adx  (default 22 — aligned with RegimeRouter threshold)
  Vol gate    : ATR / SMA(ATR,20) <= max_atr_ratio (default 1.3)
  BUY  : RSI oversold + close at/below lower Bollinger + optional reclaim
  SELL : RSI overbought + close at/above upper Bollinger + optional reclaim
  Target : mean (BB mid) / fixed R:R ~1.2–1.5 (handled by Risk agent)

Does NOT require H4 trend bias — H4 strong trend is a soft skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from core.indicators import ema, rsi, atr, adx, bollinger
from agents.technical_analysis import Signal


class MeanReversionAgent:
    """Sideways mean-reversion signal generator for BTCUSDT."""

    def __init__(
        self,
        rsi_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        bb_period: int = 20,
        bb_std: float = 2.0,
        # Sideways gate — aligned with RegimeRouter threshold (was 20)
        max_adx: float = 22.0,
        require_low_adx: bool = True,
        # RSI extremes — deeper for higher quality
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        # Require price at/beyond BB (not just near mid)
        require_band_extremes: bool = True,
        # Soft skip if H4 shows strong EMA stack trend
        skip_strong_h4_trend: bool = True,
        h4_trend_tolerance: float = 0.0025,
        min_atr_pct: float = 0.0005,
        # Higher bar for entry quality (was 0.60)
        min_score: float = 0.70,
        # BB width filter: skip dead/squeeze or explosive bands
        # width = (upper-lower)/mid
        min_bb_width: float = 0.012,   # ~1.2% — avoid ultra-tight squeeze noise
        max_bb_width: float = 0.080,   # ~8% — avoid post-breakout wide bands
        require_bb_width: bool = True,
        # ATR expansion filter: pause MR when volatility spikes
        # atr_ratio = ATR_now / SMA(ATR, atr_ma_period)
        atr_ma_period: int = 20,
        max_atr_ratio: float = 1.3,    # block if ATR > 1.3x its recent average (tightened from 1.5)
        require_atr_filter: bool = True,
    ):
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.max_adx = max_adx
        self.require_low_adx = require_low_adx
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.require_band_extremes = require_band_extremes
        self.skip_strong_h4_trend = skip_strong_h4_trend
        self.h4_trend_tolerance = h4_trend_tolerance
        self.min_atr_pct = min_atr_pct
        self.min_score = min_score
        self.min_bb_width = min_bb_width
        self.max_bb_width = max_bb_width
        self.require_bb_width = require_bb_width
        self.atr_ma_period = atr_ma_period
        self.max_atr_ratio = max_atr_ratio
        self.require_atr_filter = require_atr_filter

    def analyze(self, df_m15, df_h1, df_h4=None) -> Signal:
        """Same interface as TechnicalAnalysisAgent.analyze."""
        # Prefer H1 as primary TF for MR; fall back to m15 if needed
        primary = df_h1 if df_h1 is not None and len(df_h1) >= 80 else df_m15
        if primary is None or len(primary) < 80:
            return self._none("ข้อมูลไม่เพียงพอสำหรับ Mean Reversion")

        df = primary.copy()
        df["rsi"] = rsi(df["close"], self.rsi_period)
        df["atr"] = atr(df["high"], df["low"], df["close"], self.atr_period)
        df["adx"] = adx(df["high"], df["low"], df["close"], self.adx_period)
        mid, upper, lower = bollinger(df["close"], self.bb_period, self.bb_std)
        df["bb_mid"] = mid
        df["bb_upper"] = upper
        df["bb_lower"] = lower

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        entry = float(last["close"])
        current_atr = float(last["atr"]) if pd.notna(last["atr"]) else 0.0
        current_rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
        current_adx = float(last["adx"]) if pd.notna(last["adx"]) else 25.0
        bb_mid = float(last["bb_mid"]) if pd.notna(last["bb_mid"]) else entry
        bb_up = float(last["bb_upper"]) if pd.notna(last["bb_upper"]) else entry
        bb_lo = float(last["bb_lower"]) if pd.notna(last["bb_lower"]) else entry

        if current_atr <= 0 or entry <= 0:
            return self._none("ATR/ราคาไม่พร้อม")

        atr_pct = current_atr / entry
        if atr_pct < self.min_atr_pct:
            return self._none(f"ATR% ต่ำเกินไป ({atr_pct*100:.3f}%)")

        # --- ATR expansion filter (pause when vol spikes) ---
        if self.require_atr_filter:
            atr_ma = df["atr"].rolling(window=self.atr_ma_period, min_periods=self.atr_ma_period).mean()
            atr_avg = float(atr_ma.iloc[-1]) if pd.notna(atr_ma.iloc[-1]) else 0.0
            if atr_avg > 0:
                atr_ratio = current_atr / atr_avg
                if atr_ratio > self.max_atr_ratio:
                    return self._none(
                        f"ATR expansion — vol พุ่ง ({atr_ratio:.2f}x > {self.max_atr_ratio}x)",
                        rsi_value=current_rsi,
                        atr=current_atr,
                        entry=entry,
                    )

        # --- Regime: must be sideways ---
        if self.require_low_adx and current_adx >= self.max_adx:
            return self._none(
                f"ADX สูง — ไม่ใช่ sideway ({current_adx:.1f} >= {self.max_adx})",
                rsi_value=current_rsi,
                atr=current_atr,
                entry=entry,
            )

        # --- BB width regime (avoid squeeze noise & breakout expansion) ---
        bb_width = (bb_up - bb_lo) / bb_mid if bb_mid > 0 else 0.0
        if self.require_bb_width:
            if bb_width < self.min_bb_width:
                return self._none(
                    f"BB width แคบเกินไป (squeeze) {bb_width*100:.2f}% < {self.min_bb_width*100:.1f}%",
                    rsi_value=current_rsi, atr=current_atr, entry=entry,
                )
            if bb_width > self.max_bb_width:
                return self._none(
                    f"BB width กว้างเกินไป (expansion) {bb_width*100:.2f}% > {self.max_bb_width*100:.1f}%",
                    rsi_value=current_rsi, atr=current_atr, entry=entry,
                )

        # --- Soft skip: strong H4 trend ---
        h4_bias = "NEUTRAL"
        if self.skip_strong_h4_trend and df_h4 is not None and len(df_h4) >= 60:
            h4 = df_h4.copy()
            h4["ema50"] = ema(h4["close"], 50)
            trend_len = 200 if len(h4) >= 200 else 50
            h4["ema_trend"] = ema(h4["close"], trend_len)
            row = h4.iloc[-1]
            if pd.notna(row["ema50"]) and pd.notna(row["ema_trend"]):
                diff = (float(row["ema50"]) - float(row["ema_trend"])) / float(row["ema_trend"])
                if diff > self.h4_trend_tolerance:
                    h4_bias = "BULLISH"
                elif diff < -self.h4_trend_tolerance:
                    h4_bias = "BEARISH"

        # --- Score BUY (fade oversold) ---
        buy_score = 0.0
        buy_reasons: list[str] = []

        if current_rsi <= self.rsi_oversold:
            buy_score += 0.35
            buy_reasons.append(f"RSI oversold ({current_rsi:.1f})")
        elif current_rsi <= self.rsi_oversold + 5:
            buy_score += 0.15
            buy_reasons.append(f"RSI near OS ({current_rsi:.1f})")

        at_lower = entry <= bb_lo * 1.001
        was_outside = float(prev["low"]) < float(prev["bb_lower"]) if pd.notna(prev.get("bb_lower", float("nan"))) else False
        if at_lower:
            buy_score += 0.40
            buy_reasons.append("ที่/ใต้ Lower BB")
        elif was_outside:
            buy_score += 0.25
            buy_reasons.append("reclaim จากนอก Lower BB")
        elif entry < bb_mid and (bb_mid - entry) / current_atr >= 1.2:
            buy_score += 0.10
            buy_reasons.append("ต่ำกว่า mid >1.2 ATR")

        # Strict: must touch/reclaim band when require_band_extremes
        if self.require_band_extremes and not at_lower and not was_outside:
            buy_score = min(buy_score, self.min_score - 0.01)

        # RSI turning up
        if current_rsi > float(prev["rsi"]) if pd.notna(prev["rsi"]) else False:
            if current_rsi <= self.rsi_oversold + 8:
                buy_score += 0.15
                buy_reasons.append("RSI เริ่มฟื้น")

        # Prefer fade against mild H4 bias only if not strongly bullish
        if h4_bias == "BEARISH":
            buy_score += 0.05  # buy dip in soft down is ok in range
        elif h4_bias == "BULLISH" and self.skip_strong_h4_trend:
            buy_score -= 0.15  # don't fade hard H4 up

        # --- Score SELL (fade overbought) ---
        sell_score = 0.0
        sell_reasons: list[str] = []

        if current_rsi >= self.rsi_overbought:
            sell_score += 0.35
            sell_reasons.append(f"RSI overbought ({current_rsi:.1f})")
        elif current_rsi >= self.rsi_overbought - 5:
            sell_score += 0.15
            sell_reasons.append(f"RSI near OB ({current_rsi:.1f})")

        at_upper = entry >= bb_up * 0.999
        was_out_up = float(prev["high"]) > float(prev["bb_upper"]) if pd.notna(prev.get("bb_upper", float("nan"))) else False
        if at_upper:
            sell_score += 0.40
            sell_reasons.append("ที่/เหนือ Upper BB")
        elif was_out_up:
            sell_score += 0.25
            sell_reasons.append("reclaim จากนอก Upper BB")
        elif entry > bb_mid and (entry - bb_mid) / current_atr >= 1.2:
            sell_score += 0.10
            sell_reasons.append("สูงกว่า mid >1.2 ATR")

        if self.require_band_extremes and not at_upper and not was_out_up:
            sell_score = min(sell_score, self.min_score - 0.01)

        if current_rsi < float(prev["rsi"]) if pd.notna(prev["rsi"]) else False:
            if current_rsi >= self.rsi_overbought - 8:
                sell_score += 0.15
                sell_reasons.append("RSI เริ่มอ่อน")

        if h4_bias == "BULLISH":
            sell_score += 0.05
        elif h4_bias == "BEARISH" and self.skip_strong_h4_trend:
            sell_score -= 0.15

        buy_score = max(0.0, min(buy_score, 1.0))
        sell_score = max(0.0, min(sell_score, 1.0))

        if buy_score >= self.min_score and buy_score > sell_score:
            return Signal(
                direction="BUY",
                strength=round(buy_score, 2),
                entry_price=entry,
                atr=current_atr,
                reason="MR | " + ", ".join(buy_reasons) + f" | ADX={current_adx:.1f}",
                timeframe_bias=h4_bias,
                rsi_value=round(current_rsi, 2),
                ema_fast=bb_mid,
                ema_slow=bb_lo,
            )

        if sell_score >= self.min_score and sell_score > buy_score:
            return Signal(
                direction="SELL",
                strength=round(sell_score, 2),
                entry_price=entry,
                atr=current_atr,
                reason="MR | " + ", ".join(sell_reasons) + f" | ADX={current_adx:.1f}",
                timeframe_bias=h4_bias,
                rsi_value=round(current_rsi, 2),
                ema_fast=bb_mid,
                ema_slow=bb_up,
            )

        return Signal(
            direction="NONE",
            strength=0.0,
            entry_price=entry,
            atr=current_atr,
            reason=(
                f"MR ไม่ครบเกณฑ์ (Buy={buy_score:.2f}, Sell={sell_score:.2f}, "
                f"ADX={current_adx:.1f}, RSI={current_rsi:.1f})"
            ),
            timeframe_bias=h4_bias,
            rsi_value=round(current_rsi, 2),
        )

    def _none(
        self,
        reason: str,
        rsi_value: float = 50.0,
        atr: float = 0.0,
        entry: float = 0.0,
    ) -> Signal:
        return Signal(
            direction="NONE",
            strength=0.0,
            entry_price=entry,
            atr=atr,
            reason=reason,
            timeframe_bias="NEUTRAL",
            rsi_value=rsi_value,
        )
