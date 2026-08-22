"""LINE Thai Notifier Agent

ส่งข้อความแจ้งเตือนเป็นภาษาไทยที่อ่านง่าย ชัดเจน และเป็นมืออาชีพ
"""

from __future__ import annotations

from typing import Optional

import requests


class LineNotifierAgent:
    """แจ้งเตือนผ่าน LINE Messaging API / Notify"""

    def __init__(self, channel_access_token: str = "", user_id: str = ""):
        self.token = channel_access_token
        self.user_id = user_id
        self.api_url = "https://api.line.me/v2/bot/message/push"

    def send_message(self, message: str) -> bool:
        """ส่งข้อความดิบ"""
        if not self.token or not self.user_id:
            # ในโหมด development / test จะไม่ส่งจริง
            print(f"[LINE MOCK] {message}")
            return True

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        payload = {
            "to": self.user_id,
            "messages": [{"type": "text", "text": message}],
        }
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"[LINE ERROR] {e}")
            return False

    def notify_open_order(
        self,
        direction: str,
        symbol: str,
        entry_price: float,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        risk_percent: float,
        rr: float,
        reason: str,
    ) -> bool:
        emoji = "🟢" if direction.upper() == "BUY" else "🔴"
        msg = (
            f"{emoji} เปิด {direction.upper()} {symbol}\n"
            f"ราคาเข้า: {entry_price:.2f}\n"
            f"Lot: {lot_size}\n"
            f"SL: {stop_loss:.2f}\n"
            f"TP: {take_profit:.2f}\n"
            f"Risk: {risk_percent*100:.2f}% | R:R = 1:{rr:.2f}\n"
            f"เหตุผล: {reason}"
        )
        return self.send_message(msg)

    def notify_close_order(
        self,
        direction: str,
        symbol: str,
        pnl: float,
        r_multiple: float,
        duration: str,
        equity: float,
    ) -> bool:
        emoji = "💰" if pnl >= 0 else "💸"
        sign = "+" if pnl >= 0 else ""
        msg = (
            f"{emoji} ปิด {direction.upper()} {symbol}\n"
            f"PnL: {sign}${pnl:.2f} ({sign}{r_multiple:.2f}R)\n"
            f"ระยะเวลา: {duration}\n"
            f"Equity ปัจจุบัน: ${equity:,.2f}"
        )
        return self.send_message(msg)

    def notify_daily_summary(
        self,
        total_trades: int,
        win_trades: int,
        total_pnl: float,
        max_dd: float,
        equity: float,
    ) -> bool:
        winrate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
        sign = "+" if total_pnl >= 0 else ""
        msg = (
            f"📊 สรุปผลประจำวัน XAUUSD\n"
            f"จำนวนออเดอร์: {total_trades}\n"
            f"ชนะ: {win_trades} ({winrate:.1f}%)\n"
            f"PnL สุทธิ: {sign}${total_pnl:.2f}\n"
            f"Max Drawdown: {max_dd*100:.2f}%\n"
            f"Equity: ${equity:,.2f}"
        )
        return self.send_message(msg)

    def notify_system_alert(self, title: str, detail: str) -> bool:
        msg = f"⚠️ {title}\n{detail}"
        return self.send_message(msg)
