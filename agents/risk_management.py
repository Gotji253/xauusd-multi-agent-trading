"""Risk Management Agent — หัวใจของระบบทำกำไรระยะยาว

คำนวณ Position Size, SL, TP และควบคุม Drawdown / Loss Streak อย่างเข้มงวด
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
    risk_scale: float = 1.0          # 1.0 = full, 0.5 = halved after streak
    consecutive_losses: int = 0


class RiskManagementAgent:
    """จัดการความเสี่ยงทั้งหมดของระบบ

    Streak control (2026-08-24):
      - แพ้ติด ≥ streak_reduce_at  → ลด risk เหลือ risk_scale_on_streak
      - แพ้ติด ≥ streak_halt_at    → ปฏิเสธไม้ใหม่จนกว่าจะ reset
      - ชนะ 1 ไม้                  → รีเซ็ต streak
      - Daily DD ≥ max_daily_drawdown → หยุดวันนั้น (มีอยู่แล้ว)
    """

    def __init__(
        self,
        risk_per_trade: float = 0.005,           # 0.5% — conservative for BTC
        max_daily_drawdown: float = 0.03,        # 3% hard stop
        max_open_positions: int = 1,
        min_reward_risk: float = 1.8,
        # BTC noise is higher → slightly wider SL, keep R:R ≥ ~1.8
        atr_sl_multiplier: float = 2.0,
        atr_tp_multiplier: float = 3.6,
        # --- Loss streak controls ---
        # Research 2026-08-24: hard halt ทำลาย recovery → ใช้ ladder scale แทน
        #   แพ้ติด ≥ reduce_at → x risk_scale_on_streak (default 0.5)
        #   แพ้ติด ≥ deep_at   → x risk_scale_deep (default 0.25)
        #   hard_halt=False โดย default (ยังเปิดไม้ได้แต่ไซส์เล็กมาก)
        streak_reduce_at: int = 3,
        streak_deep_at: int = 5,
        risk_scale_on_streak: float = 0.5,
        risk_scale_deep: float = 0.25,
        enable_streak_control: bool = True,
        hard_halt_on_deep_streak: bool = False,  # True = ปฏิเสธไม้เมื่อ deep streak
    ):
        self.risk_per_trade = risk_per_trade
        self.max_daily_drawdown = max_daily_drawdown
        self.max_open_positions = max_open_positions
        self.min_reward_risk = min_reward_risk
        self.atr_sl_multiplier = atr_sl_multiplier
        self.atr_tp_multiplier = atr_tp_multiplier

        self.streak_reduce_at = streak_reduce_at
        self.streak_deep_at = streak_deep_at
        self.streak_halt_at = streak_deep_at  # alias เดิมสำหรับ test/compat
        self.risk_scale_on_streak = risk_scale_on_streak
        self.risk_scale_deep = risk_scale_deep
        self.enable_streak_control = enable_streak_control
        self.hard_halt_on_deep_streak = hard_halt_on_deep_streak

        # Runtime state (call record_trade_result after each closed trade)
        self.consecutive_losses: int = 0
        self.consecutive_wins: int = 0
        self.total_trades_recorded: int = 0

    # ------------------------------------------------------------------
    # Streak API
    # ------------------------------------------------------------------
    def record_trade_result(self, won: bool) -> None:
        """อัปเดต loss/win streak หลังปิดไม้ — เรียกจาก Orchestrator / Backtest / Paper"""
        self.total_trades_recorded += 1
        if won:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

    def reset_streak(self) -> None:
        self.consecutive_losses = 0
        self.consecutive_wins = 0

    def current_risk_scale(self) -> float:
        if not self.enable_streak_control:
            return 1.0
        if self.consecutive_losses >= self.streak_deep_at:
            return float(self.risk_scale_deep)
        if self.consecutive_losses >= self.streak_reduce_at:
            return float(self.risk_scale_on_streak)
        return 1.0

    def is_halted_by_streak(self) -> bool:
        if not self.enable_streak_control or not self.hard_halt_on_deep_streak:
            return False
        return self.consecutive_losses >= self.streak_deep_at

    def effective_risk_per_trade(self) -> float:
        return self.risk_per_trade * self.current_risk_scale()

    # ------------------------------------------------------------------
    # Core sizing
    # ------------------------------------------------------------------
    def calculate(
        self,
        equity: float,
        entry_price: float,
        direction: str,
        atr: float,
        current_daily_pnl: float = 0.0,
        open_positions: int = 0,
        point: float = 1.0,           # BTC Spot: ใช้ 1.0 → lot ≈ risk_amount / sl_distance (หน่วย BTC)
        tick_value: float = 1.0,      # ปรับตาม broker (Spot USDT คู่ = 1.0)
    ) -> RiskDecision:
        """คำนวณ Lot Size + SL + TP และตรวจสอบกฎความเสี่ยง

        สำหรับ Binance Spot BTCUSDT:
          - ตั้ง point=1.0, tick_value=1.0
          - lot_size ≈ risk_amount / |entry - SL|  (หน่วย BTC)
          - จากนั้นคูณ BINANCE_QTY_SCALE ใน ExecutionAgent
        """

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
                consecutive_losses=self.consecutive_losses,
            )

        # 2. ตรวจสอบ Daily Drawdown (hard kill)
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
                consecutive_losses=self.consecutive_losses,
            )

        # 3. Loss streak hard halt (optional — default off; prefer deep scale)
        if self.is_halted_by_streak():
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                risk_amount=0.0,
                risk_percent=0.0,
                reason=(
                    f"Loss streak hard halt ({self.consecutive_losses} ≥ {self.streak_deep_at}) "
                    f"— หยุดเปิดไม้จนกว่าจะชนะหรือ reset"
                ),
                consecutive_losses=self.consecutive_losses,
                risk_scale=0.0,
            )

        # 4. คำนวณ SL / TP จาก ATR
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
                consecutive_losses=self.consecutive_losses,
            )

        # 5. คำนวณระยะ SL เป็น points
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
                consecutive_losses=self.consecutive_losses,
            )

        # 6. Risk scale จาก streak
        scale = self.current_risk_scale()
        eff_risk_pct = self.risk_per_trade * scale
        risk_amount = equity * eff_risk_pct

        # 7. Lot Size
        # BTC Spot (point=1, tick=1): lot = risk_amount / sl_distance  → หน่วย BTC
        lot_size = risk_amount / (sl_distance / point * tick_value)
        lot_size = max(0.0001, round(lot_size, 6))

        # 8. Reward:Risk
        tp_distance = abs(take_profit - entry_price)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0.0

        if rr < self.min_reward_risk:
            return RiskDecision(
                approved=False,
                lot_size=0.0,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_amount=risk_amount,
                risk_percent=eff_risk_pct,
                reason=f"Reward:Risk ต่ำเกินไป ({rr:.2f} < {self.min_reward_risk})",
                reward_risk_ratio=rr,
                risk_scale=scale,
                consecutive_losses=self.consecutive_losses,
            )

        reason = "ผ่านเกณฑ์ความเสี่ยงทั้งหมด"
        if scale < 1.0:
            reason = (
                f"ผ่าน (streak={self.consecutive_losses} → risk x{scale:.2f} "
                f"= {eff_risk_pct*100:.2f}%)"
            )

        return RiskDecision(
            approved=True,
            lot_size=lot_size,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_amount=round(risk_amount, 2),
            risk_percent=eff_risk_pct,
            reason=reason,
            reward_risk_ratio=round(rr, 2),
            risk_scale=scale,
            consecutive_losses=self.consecutive_losses,
        )
