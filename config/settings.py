"""Central settings loaded from environment."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ---- Broker selection ----
# auto | mock | binance | oanda
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "auto")
BROKER = os.getenv("BROKER", "binance")  # preferred when auto

# ---- Binance (BTC) ----
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
# testnet | live
BINANCE_ENVIRONMENT = os.getenv("BINANCE_ENVIRONMENT", "testnet")
# quantity scale: lot_size * scale = BTC amount (เริ่มเล็ก เช่น 0.001)
BINANCE_QTY_SCALE = float(os.getenv("BINANCE_QTY_SCALE", "0.001"))
BINANCE_BASE_URL = os.getenv("BINANCE_BASE_URL", "")  # optional override

# ---- OANDA (optional / gold) ----
OANDA_API_KEY = os.getenv("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")
OANDA_UNITS_SCALE = float(os.getenv("OANDA_UNITS_SCALE", "1.0"))

# ---- Legacy MT5 ----
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0") or "0")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
MT5_PATH = os.getenv("MT5_PATH", "")

# ---- LINE ----
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")

# ---- Trading ----
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
MAX_DAILY_DRAWDOWN = float(os.getenv("MAX_DAILY_DRAWDOWN", "0.03"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
