"""Regime Router — selects Strategy 1 (Trend) or Strategy 2 (Mean Reversion) by ADX.

Rules:
  ADX >= adx_trend_threshold  →  Trend Pullback (S1)
  ADX <  adx_trend_threshold  →  Mean Reversion (S2)  [if enable_s2]

Modes:
  enable_s2=False  → S1 only (RANGE also uses S1 or flat NONE via s2_soft)
  s2_mode="off"    → never call S2
  s2_mode="soft"   → S2 only when ADX < s2_max_adx (stricter than trend threshold)
  s2_mode="full"   → original behaviour (ADX < trend threshold → S2)

Default production: enable_s2=False (S1 primary) until S2 confirm-entry passes OOS.
"""

from __future__ import annotations

from typing import Literal, Optional

import pandas as pd

from core.indicators import adx
from agents.technical_analysis import TechnicalAnalysisAgent, Signal
from agents.mean_reversion import MeanReversionAgent
from agents.risk_management import RiskManagementAgent


RegimeName = Literal["TREND", "RANGE", "UNKNOWN"]
S2Mode = Literal["off", "soft", "full"]


class RegimeRouter:
    """ADX-based strategy selector with optional hysteresis and S2 soft/off."""

    def __init__(
        self,
        trend_agent: Optional[TechnicalAnalysisAgent] = None,
        mr_agent: Optional[MeanReversionAgent] = None,
        risk_trend: Optional[RiskManagementAgent] = None,
        risk_mr: Optional[RiskManagementAgent] = None,
        adx_period: int = 14,
        adx_trend_threshold: float = 20.0,
        hysteresis_band: float = 2.0,
        use_hysteresis: bool = True,
        # S2 control (research conclusion 2026-08-24: S1 primary)
        enable_s2: bool = False,
        s2_mode: S2Mode = "off",
        s2_max_adx: float = 18.0,
    ):
        self.trend_agent = trend_agent or TechnicalAnalysisAgent(
            require_h4=True,
            require_w1=True,
            w1_mode="no_oppose",
            require_adx=True,
            min_adx=20.0,
            require_h4_adx=True,
            min_h4_adx=25.0,
            min_confluence=0.62,
        )
        self.mr_agent = mr_agent or MeanReversionAgent(
            max_adx=20.0,
            require_low_adx=True,
            min_score=0.70,
            require_bb_width=True,
            max_atr_ratio=1.3,
            require_atr_filter=True,
        )
        # Risk profiles matched to each strategy
        self.risk_trend = risk_trend or RiskManagementAgent(
            risk_per_trade=0.005,
            max_daily_drawdown=0.03,
            max_open_positions=1,
            min_reward_risk=1.8,
            atr_sl_multiplier=2.0,
            atr_tp_multiplier=3.6,
        )
        self.risk_mr = risk_mr or RiskManagementAgent(
            risk_per_trade=0.003,  # tighter: 0.3% per MR trade
            max_daily_drawdown=0.03,
            max_open_positions=1,
            min_reward_risk=1.2,
            atr_sl_multiplier=1.5,
            atr_tp_multiplier=2.0,
        )
        self.adx_period = adx_period
        self.adx_trend_threshold = adx_trend_threshold
        self.hysteresis_band = hysteresis_band
        self.use_hysteresis = use_hysteresis
        self.enable_s2 = enable_s2
        # s2_mode overrides enable_s2 if set explicitly via soft/full
        self.s2_mode: S2Mode = s2_mode if enable_s2 or s2_mode != "off" else "off"
        if not enable_s2:
            self.s2_mode = "off"
        self.s2_max_adx = s2_max_adx
        self._last_regime: RegimeName = "UNKNOWN"
        self.last_adx: float = 0.0
        self.last_regime: RegimeName = "UNKNOWN"
        self.last_strategy: str = "NONE"

    def compute_adx(self, df_h1) -> float:
        if df_h1 is None or len(df_h1) < self.adx_period + 5:
            return 0.0
        series = adx(df_h1["high"], df_h1["low"], df_h1["close"], self.adx_period)
        val = series.iloc[-1]
        if pd.isna(val):
            return 0.0
        return float(val)

    def detect_regime(self, current_adx: float) -> RegimeName:
        """Map ADX → regime with hysteresis."""
        thr = self.adx_trend_threshold
        band = self.hysteresis_band if self.use_hysteresis else 0.0
        prev = self._last_regime

        if prev == "TREND":
            # stay in TREND until ADX falls clearly below threshold
            regime: RegimeName = "TREND" if current_adx >= (thr - band) else "RANGE"
        elif prev == "RANGE":
            # stay in RANGE until ADX rises clearly above threshold
            regime = "RANGE" if current_adx < (thr + band) else "TREND"
        else:
            regime = "TREND" if current_adx >= thr else "RANGE"

        self._last_regime = regime
        self.last_regime = regime
        self.last_adx = current_adx
        return regime

    def select_agents(self, regime: RegimeName, current_adx: float = 0.0):
        """Choose S1 or S2 according to regime + s2_mode."""
        if regime == "TREND":
            self.last_strategy = "S1_TREND"
            return self.trend_agent, self.risk_trend

        # RANGE regime
        if self.s2_mode == "off":
            # S1 primary: still allow S1 to evaluate (pullback may appear in mild range)
            self.last_strategy = "S1_TREND"
            return self.trend_agent, self.risk_trend

        if self.s2_mode == "soft":
            # S2 only in deeper range (ADX clearly low)
            if current_adx < self.s2_max_adx:
                self.last_strategy = "S2_MR"
                return self.mr_agent, self.risk_mr
            self.last_strategy = "S1_TREND"
            return self.trend_agent, self.risk_trend

        # full
        self.last_strategy = "S2_MR"
        return self.mr_agent, self.risk_mr

    def analyze(self, df_m15, df_h1, df_h4=None, df_w1=None) -> Signal:
        """Drop-in replacement for TA analyze() — routes to S1 or S2."""
        current_adx = self.compute_adx(df_h1)
        regime = self.detect_regime(current_adx)
        agent, _risk = self.select_agents(regime, current_adx)
        # Pass W1 through when agent supports it (S1 TA); S2 ignores extra kw if needed
        try:
            signal = agent.analyze(df_m15, df_h1, df_h4, df_w1=df_w1)
        except TypeError:
            signal = agent.analyze(df_m15, df_h1, df_h4)

        # Tag reason with regime for logs / backtest
        if signal.direction != "NONE":
            tag = f"[{self.last_strategy}|ADX={current_adx:.1f}|s2={self.s2_mode}] "
            if not signal.reason.startswith("["):
                signal.reason = tag + signal.reason
        else:
            if "ADX" not in signal.reason:
                signal.reason = (
                    f"[{self.last_strategy}|ADX={current_adx:.1f}|{regime}|s2={self.s2_mode}] "
                    f"{signal.reason}"
                )
        return signal

    def get_risk_agent(self) -> RiskManagementAgent:
        """Risk profile matching the last selected strategy."""
        if self.last_strategy == "S2_MR":
            return self.risk_mr
        return self.risk_trend

    def status(self) -> dict:
        return {
            "regime": self.last_regime,
            "strategy": self.last_strategy,
            "adx": round(self.last_adx, 2),
            "threshold": self.adx_trend_threshold,
            "hysteresis_band": self.hysteresis_band if self.use_hysteresis else 0.0,
            "enable_s2": self.enable_s2,
            "s2_mode": self.s2_mode,
            "s2_max_adx": self.s2_max_adx,
        }
