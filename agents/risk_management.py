"""Risk Management Agent — หัวใจของระบบทำกำไรระยะยาว

คำนวณ Position Size, SL, TP และควบคุม Drawdown อย่างเข้มงวด
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskDecision:
    approved: bool
    lot_size: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    risk_percent: float
    reason: str
    reward_risk_ratio: float = 0.0


class RiskManagementAgent:
    """จัดการความเสี่ยงทั้งหมดของระบบ"""

    def __init__(
        self,
        risk_per_trade: float = 0.0075,          # 0.75%
        max_daily_drawdown: float = 0.035,       # 3.5%
        max_open_positions: int = 1,
        min_reward_risk: float = 1.8,
        atr_sl_multiplier: float = 1.8,
        atr_tp_multiplier: float = 3.2,
    ):
        self.risk_per_trade = risk_per_trade
        self.max_daily_drawdown = max_daily_drawdown
        self.max_open_positions = max_open_positions
        self.min_reward_risk = min_reward_risk
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

    def calculate(
        self,
        equity: float,
        entry_price: float,
        direction: str,
        atr: float,
        current_daily_pnl: float = 0.0,
        open_positions: int = 0,
        point: float = 0.01,          # XAUUSD point
        tick_value: float = 1.0,      # ปรับตาม broker
    ) -> RiskDecision:
        """คำนวณ Lot Size + SL + TP และตรวจสอบกฎความเสี่ยง"""

        # 1. ตรวจสอบจำนวน Position ที่เปิดอยู่
        if open_positions >= self.max_open_positions:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_amount=0.0,
                risk_percent=0.0,
                reason=f"เกินจำนวน Position สูงสุด ({self.max_open_positions})",
            )

        # 2. ตรวจสอบ Daily Drawdown
        daily_dd_pct = abs(min(current_daily_pnl, 0.0)) / equity if equity > 0 else 0.0
        if daily_dd_pct >= self.max_daily_drawdown:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_amount=0.0,
                risk_percent=0.0,
                reason=f"Daily Drawdown ถึงขีดจำกัด ({self.max_daily_drawdown*100:.1f}%)",
            )

        # 3. คำนวณ SL / TP จาก ATR
        if direction.upper() == "BUY":
            stop_loss = entry_price - (atr * self.atr_sl_multiplier)
            take_profit = entry_price + (atr * self.atr_tp_multiplier)
        elif direction.upper() == "SELL":
            stop_loss = entry_price + (atr * self.atr_sl_multiplier)
            take_profit = entry_price - (atr * self.atr_tp_multiplier)
        else:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_amount=0.0,
                risk_percent=0.0,
                reason="ทิศทางไม่ถูกต้อง (ต้องเป็น BUY หรือ SELL)",
            )

        # 4. คำนวณระยะ SL เป็น points
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_amount=0.0,
                risk_percent=0.0,
                reason="ระยะ Stop Loss ไม่ถูกต้อง",
            )

        # 5. คำนวณ Lot Size
        risk_amount = equity * self.risk_per_trade
        # สำหรับ XAUUSD โดยทั่วไป: 1 lot ≈ $1 ต่อ $0.01 (ปรับตาม broker จริง)
        # สูตรทั่วไป: lot = risk_amount / (sl_distance / point * tick_value)
        lot_size = risk_amount / (sl_distance / point * tick_value)
        lot_size = max(0.01, round(lot_size, 2))  # minimum 0.01

        # 6. Reward:Risk
        tp_distance = abs(take_profit - entry_price)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0.0

        if rr < self.min_reward_risk:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_amount=risk_amount,
                risk_percent=self.risk_per_trade,
                reason=f"Reward:Risk ต่ำเกินไป ({rr:.2f} < {self.min_reward_risk})",
                reward_risk_ratio=rr,
            )

        return RiskDecision(
            approved=True,
            lot_size=lot_size,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_amount=round(risk_amount, 2),
            risk_percent=self.risk_per_trade,
            reason="ผ่านเกณฑ์ความเสี่ยงทั้งหมด",
            reward_risk_ratio=round(rr, 2),
        )
