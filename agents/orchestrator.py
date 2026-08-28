"""Orchestrator — S1 primary (squeeze_or_pullback) + optional RegimeRouter."""

from __future__ import annotations

from typing import Any, Optional

from agents.technical_analysis import TechnicalAnalysisAgent, Signal
from agents.mean_reversion import MeanReversionAgent
from agents.regime_router import RegimeRouter
from agents.risk_management import RiskManagementAgent, RiskDecision
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent
from agents.early_alert import EarlyAlertAgent
from config import settings


class Orchestrator:
    def __init__(
        self,
        ta_agent: Optional[TechnicalAnalysisAgent] = None,
        mr_agent: Optional[MeanReversionAgent] = None,
        risk_agent: Optional[RiskManagementAgent] = None,
        exec_agent: Optional[ExecutionAgent] = None,
        notifier: Optional[LineNotifierAgent] = None,
        router: Optional[RegimeRouter] = None,
        use_regime_router: bool = True,
        symbol: Optional[str] = None,
        early_alert: Optional[EarlyAlertAgent] = None,
    ):
        self.use_regime_router = use_regime_router
        self.symbol = symbol or getattr(settings, "SYMBOL", "BTCUSDT")
        self.ta = ta_agent or TechnicalAnalysisAgent(
            require_h4=True,
            require_w1=True,
            w1_mode="no_oppose",
            require_adx=True,
            min_adx=20.0,
            require_h4_adx=True,
            min_h4_adx=25.0,
            min_confluence=0.62,
            require_ema_stack_buy=True,
            ema_stack_triggers_buy=False,
            squeeze_breakout_bonus=0.15,
            primary_buy_mode="squeeze_or_pullback",
        )
        self.mr = mr_agent or MeanReversionAgent(
            max_adx=20.0, require_low_adx=True, min_score=0.70, require_bb_width=True
        )
        self.risk = risk_agent or RiskManagementAgent(
            risk_per_trade=getattr(settings, "RISK_PER_TRADE", 0.005),
            max_daily_drawdown=getattr(settings, "MAX_DAILY_DRAWDOWN", 0.03),
            max_open_positions=getattr(settings, "MAX_OPEN_POSITIONS", 1),
        )
        self.router = router or RegimeRouter(
            trend_agent=self.ta,
            mr_agent=self.mr,
            adx_trend_threshold=20.0,
            hysteresis_band=2.0,
            use_hysteresis=True,
            enable_s2=False,
            s2_mode="off",
        )
        self.execution = exec_agent or ExecutionAgent()
        self.notifier = notifier or LineNotifierAgent()
        self.early_alert = early_alert or EarlyAlertAgent()
        self.is_halted = False
        self.halt_reason = ""

    def run_cycle(self, market_data: dict[str, Any], account_info: dict[str, Any]) -> dict[str, Any]:
        if self.is_halted:
            return {"status": "HALTED", "reason": self.halt_reason}

        analyzer = self.router if self.use_regime_router else self.ta
        try:
            signal: Signal = analyzer.analyze(
                df_m15=market_data.get("m15"),
                df_h1=market_data.get("h1"),
                df_h4=market_data.get("h4"),
                df_w1=market_data.get("w1"),
            )
        except TypeError:
            signal = analyzer.analyze(
                market_data.get("m15"), market_data.get("h1"), market_data.get("h4")
            )

        if signal.direction == "NONE":
            return {"status": "NO_SIGNAL", "signal": signal, "gate": getattr(signal, "gate", "")}

        risk_agent = self.router.get_risk_agent() if self.use_regime_router else self.risk
        decision: RiskDecision = risk_agent.calculate(
            equity=account_info.get("equity", 0.0),
            entry_price=signal.entry_price,
            direction=signal.direction,
            atr=signal.atr,
            current_daily_pnl=account_info.get("daily_pnl", 0.0),
            open_positions=account_info.get("open_positions", 0),
        )
        if not decision.approved:
            return {"status": "RISK_REJECTED", "reason": decision.reason, "signal": signal}

        try:
            self.notifier.notify_open_order(
                direction=signal.direction,
                symbol=self.symbol,
                entry_price=signal.entry_price,
                lot_size=decision.lot_size,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                risk_percent=decision.risk_percent,
                rr=decision.reward_risk_ratio,
                reason=signal.reason,
            )
        except Exception:
            pass

        return {"status": "ORDER_PREPARED", "signal": signal, "risk_decision": decision}

    def halt(self, reason: str) -> None:
        self.is_halted = True
        self.halt_reason = reason
        try:
            self.notifier.notify_system_alert("ระบบหยุดทำงาน (Halt)", reason)
        except Exception:
            pass

    def resume(self) -> None:
        self.is_halted = False
        self.halt_reason = ""
        try:
            self.notifier.notify_system_alert("ระบบกลับมาทำงานปกติ", "Resume")
        except Exception:
            pass
