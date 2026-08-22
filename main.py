"""Entry point — multi-broker (Binance BTC / OANDA / mock)"""

from __future__ import annotations

from utils.logger import setup_logger
from agents.orchestrator import Orchestrator
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent
from core.oanda_client import OandaClient
from core.binance_client import BinanceClient
from config import settings


def build_execution_agent() -> ExecutionAgent:
    binance = BinanceClient(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        environment=settings.BINANCE_ENVIRONMENT,
        base_url=settings.BINANCE_BASE_URL or None,
    )
    oanda = OandaClient(
        api_key=settings.OANDA_API_KEY,
        account_id=settings.OANDA_ACCOUNT_ID,
        environment=settings.OANDA_ENVIRONMENT,
    )
    mode = settings.EXECUTION_MODE
    if mode == "auto":
        preferred = (settings.BROKER or "binance").lower()
        if preferred == "binance" and binance.is_configured:
            mode = "binance"
        elif preferred == "oanda" and oanda.is_configured:
            mode = "oanda"
        elif binance.is_configured:
            mode = "binance"
        elif oanda.is_configured:
            mode = "oanda"
        else:
            mode = "mock"

    scale = (
        settings.BINANCE_QTY_SCALE
        if mode == "binance"
        else settings.OANDA_UNITS_SCALE
    )
    return ExecutionAgent(
        oanda_client=oanda,
        binance_client=binance,
        mode=mode,
        default_units_scale=scale,
        default_symbol=settings.SYMBOL,
    )


def main() -> None:
    setup_logger(level=settings.LOG_LEVEL)
    print("=" * 60)
    print("Multi-Agent AI Trading System")
    print("Brokers: Binance (BTC) | OANDA | mock")
    print("=" * 60)
    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Symbol      : {settings.SYMBOL}")
    print(f"Risk/Trade  : {settings.RISK_PER_TRADE * 100:.2f}%")
    print(f"Broker pref : {settings.BROKER}")
    print("=" * 60)

    exec_agent = build_execution_agent()
    conn = exec_agent.test_connection()
    print(f"\nExecution mode : {exec_agent.mode}")
    print(f"Connection     : {conn.get('message')}")
    if conn.get("btcusdt_price"):
        print(f"BTCUSDT        : {conn.get('btcusdt_price')}")
    if conn.get("balances"):
        print(f"Balances       : {conn.get('balances')}")
    if conn.get("balance") is not None:
        print(f"OANDA balance  : {conn.get('balance')} {conn.get('currency')}")

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
    print("ทดสอบ Binance: python scripts/test_binance_connection.py")
    print("ทดสอบ OANDA  : python scripts/test_oanda_connection.py")


if __name__ == "__main__":
    main()
