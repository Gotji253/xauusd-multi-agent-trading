"""Central settings loaded from environment and yaml."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# MT5
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
MT5_PATH = os.getenv("MT5_PATH", "")

# LINE
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID = os.getenv("LINE_USER_ID", "")

# Trading
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.0075"))
MAX_DAILY_DRAWDOWN = float(os.getenv("MAX_DAILY_DRAWDOWN", "0.035"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
