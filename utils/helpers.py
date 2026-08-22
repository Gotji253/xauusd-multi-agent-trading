"""Common helper functions."""

from __future__ import annotations


def format_price(price: float, digits: int = 2) -> str:
    return f"{price:.{digits}f}"


def calculate_r_multiple(entry: float, exit_price: float, stop_loss: float, direction: str) -> float:
    risk = abs(entry - stop_loss)
    if risk == 0:
        return 0.0
    if direction.upper() == "BUY":
        return (exit_price - entry) / risk
    else:
        return (entry - exit_price) / risk
