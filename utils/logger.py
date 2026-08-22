"""Logging setup with loguru."""

from __future__ import annotations

import sys
from loguru import logger


def setup_logger(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )
    logger.add(
        "logs/trading_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level=level,
        encoding="utf-8",
    )
