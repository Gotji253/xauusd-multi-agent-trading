"""Execution Agent — เชื่อมต่อ MetaTrader 5 สำหรับส่ง/ปิดออเดอร์"""

from __future__ import annotations

from typing import Any, Optional


class ExecutionAgent:
    """จัดการการส่งคำสั่งซื้อขายผ่าน MT5"""

    def __init__(self, mt5_connector: Any = None):
        self.mt5 = mt5_connector

    def place_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "XAUUSD-MultiAgent",
    ) -> dict:
        """ส่ง Market Order"""
        # TODO: Implement จริงด้วย MetaTrader5 API
        # Placeholder สำหรับ CI และโครงสร้าง
        return {
            "success": False,
            "ticket": None,
            "message": "Skeleton - รอเชื่อมต่อ MT5 จริง",
        }

    def close_position(self, ticket: int, percent: float = 1.0) -> dict:
        """ปิด Position (รองรับ Partial Close)"""
        return {
            "success": False,
            "message": "Skeleton - รอ implement",
        }

    def modify_sl_tp(self, ticket: int, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> dict:
        """แก้ไข SL / TP (ใช้สำหรับ Trailing)"""
        return {
            "success": False,
            "message": "Skeleton - รอ implement",
        }
