"""Entry point ของ XAUUSD Multi-Agent Trading System"""

from __future__ import annotations

from utils.logger import setup_logger
from agents.orchestrator import Orchestrator
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent
from config import settings


def main() -> None:
    setup_logger(level=settings.LOG_LEVEL)

    print("=" * 60)
    print("XAUUSD Multi-Agent AI Trading System")
    print("Focus: Risk-Adjusted Return & Drawdown Control")
    print("=" * 60)
    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Symbol      : {settings.SYMBOL}")
    print(f"Risk/Trade  : {settings.RISK_PER_TRADE * 100:.2f}%")
    print("=" * 60)

    # สร้าง Agents
    ta_agent = TechnicalAnalysisAgent()
    risk_agent = RiskManagementAgent(
        risk_per_trade=settings.RISK_PER_TRADE,
        max_daily_drawdown=settings.MAX_DAILY_DRAWDOWN,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
    )
    exec_agent = ExecutionAgent()
    notifier = LineNotifierAgent(
        channel_access_token=settings.LINE_CHANNEL_ACCESS_TOKEN,
        user_id=settings.LINE_USER_ID,
    )

    orchestrator = Orchestrator(
        ta_agent=ta_agent,
        risk_agent=risk_agent,
        exec_agent=exec_agent,
        notifier=notifier,
    )

    print("\nระบบพร้อม (Skeleton mode)")
    print("ขั้นตอนถัดไป: implement Technical Analysis logic + เชื่อม MT5 จริง")
    print("รัน pytest เพื่อตรวจสอบว่า Unit Tests ผ่านก่อนพัฒนาต่อ")


if __name__ == "__main__":
    main()
