"""Entry point — OANDA v20 execution"""

from __future__ import annotations

from utils.logger import setup_logger
from agents.orchestrator import Orchestrator
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent
from core.oanda_client import OandaClient
from config import settings


def main() -> None:
    setup_logger(level=settings.LOG_LEVEL)
    print("=" * 60)
    print("XAUUSD Multi-Agent AI Trading System")
    print("Execution: OANDA v20 REST API")
    print("=" * 60)
    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Symbol      : {settings.SYMBOL}")
    print(f"Risk/Trade  : {settings.RISK_PER_TRADE * 100:.2f}%")
    print(f"OANDA env   : {settings.OANDA_ENVIRONMENT}")
    print("=" * 60)

    oanda = OandaClient(
        api_key=settings.OANDA_API_KEY,
        account_id=settings.OANDA_ACCOUNT_ID,
        environment=settings.OANDA_ENVIRONMENT,
    )
    exec_agent = ExecutionAgent(
        oanda_client=oanda,
        mode=settings.EXECUTION_MODE,
        default_units_scale=settings.OANDA_UNITS_SCALE,
    )
    conn = exec_agent.test_connection()
    print(f"\nExecution mode : {exec_agent.mode}")
    print(f"Connection     : {conn.get('message')}")
    if conn.get("balance") is not None:
        print(f"Balance        : {conn.get('balance')} {conn.get('currency')}")

    ta_agent = TechnicalAnalysisAgent()
    risk_agent = RiskManagementAgent(
        risk_per_trade=settings.RISK_PER_TRADE,
        max_daily_drawdown=settings.MAX_DAILY_DRAWDOWN,
        max_open_positions=settings.MAX_OPEN_POSITIONS,
    )
    notifier = LineNotifierAgent(
        channel_access_token=settings.LINE_CHANNEL_ACCESS_TOKEN,
        user_id=settings.LINE_USER_ID,
    )
    Orchestrator(
        ta_agent=ta_agent,
        risk_agent=risk_agent,
        exec_agent=exec_agent,
        notifier=notifier,
    )
    print("\nระบบพร้อม")
    print("ทดสอบ: python scripts/test_oanda_connection.py")


if __name__ == "__main__":
    main()
