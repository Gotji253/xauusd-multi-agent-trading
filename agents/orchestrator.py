"""Orchestrator (Supervisor Agent)

ควบคุมจังหวะการทำงานของทุก Agent และจัดการ State ของระบบ
"""

from __future__ import annotations

from typing import Any, Optional

from agents.technical_analysis import TechnicalAnalysisAgent, Signal
from agents.risk_management import RiskManagementAgent, RiskDecision
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent


class Orchestrator:
    """ตัวกลางควบคุม Multi-Agent System"""

    def __init__(
        self,
        ta_agent: Optional[TechnicalAnalysisAgent] = None,
        risk_agent: Optional[RiskManagementAgent] = None,
        exec_agent: Optional[ExecutionAgent] = None,
        notifier: Optional[LineNotifierAgent] = None,
    ):
        self.ta = ta_agent or TechnicalAnalysisAgent()
        self.risk = risk_agent or RiskManagementAgent()
        self.execution = exec_agent or ExecutionAgent()
        self.notifier = notifier or LineNotifierAgent()
        self.is_halted = False
        self.halt_reason = ""

    def run_cycle(self, market_data: dict[str, Any], account_info: dict[str, Any]) -> dict[str, Any]:
        """รันหนึ่งรอบของระบบ (เรียกทุก 1–5 นาที หรือ on-tick)"""
        if self.is_halted:
            return {"status": "HALTED", "reason": self.halt_reason}

        # 1. วิเคราะห์ Technical
        signal: Signal = self.ta.analyze(
            df_m15=market_data.get("m15"),
            df_h1=market_data.get("h1"),
            df_h4=market_data.get("h4"),
        )

        if signal.direction == "NONE":
            return {"status": "NO_SIGNAL", "signal": signal}

        # 2. ตรวจสอบความเสี่ยง
        decision: RiskDecision = self.risk.calculate(
            equity=account_info.get("equity", 0.0),
            entry_price=signal.entry_price,
            direction=signal.direction,
            atr=signal.atr,
            current_daily_pnl=account_info.get("daily_pnl", 0.0),
            open_positions=account_info.get("open_positions", 0),
        )

        if not decision.approved:
            return {"status": "RISK_REJECTED", "reason": decision.reason, "signal": signal}

        # 3. ส่งออเดอร์ (ในอนาคต)
        # order_result = self.execution.place_order(...)

        # 4. แจ้งเตือน LINE
        self.notifier.notify_open_order(
            direction=signal.direction,
            symbol="XAUUSD",
            entry_price=signal.entry_price,
            lot_size=decision.lot_size,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            risk_percent=decision.risk_percent,
            rr=decision.reward_risk_ratio,
            reason=signal.reason,
        )

        return {
            "status": "ORDER_PREPARED",
            "signal": signal,
            "risk_decision": decision,
        }

    def halt(self, reason: str) -> None:
        self.is_halted = True
        self.halt_reason = reason
        self.notifier.notify_system_alert("ระบบหยุดทำงาน (Halt)", reason)

    def resume(self) -> None:
        self.is_halted = False
        self.halt_reason = ""
        self.notifier.notify_system_alert("ระบบกลับมาทำงานปกติ", "Resume สำเร็จ")
