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
        *,
        exit_reason: str = "",
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        lot_size: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        usdt_free: float = 0.0,
        btc_free: float = 0.0,
    ) -> bool:
        """แจ้งปิดไม้ — รองรับ SL/TP + ยอดเงินคงเหลือ"""
        reason = (exit_reason or "").upper()
        if reason in ("TP", "TAKE_PROFIT"):
            emoji = "🎯"
            tag = "TP"
        elif reason in ("SL", "STOP_LOSS"):
            emoji = "🛑"
            tag = "SL"
        else:
            emoji = "💰" if pnl >= 0 else "💸"
            tag = reason or "CLOSE"
        sign = "+" if pnl >= 0 else ""
        lines = [
            f"{emoji} ปิด {direction.upper()} {symbol} ({tag})",
        ]
        if entry_price > 0:
            lines.append(f"ราคาเข้า: {entry_price:.2f}")
        if exit_price > 0:
            lines.append(f"ราคาออก: {exit_price:.2f}")
        if lot_size > 0:
            lines.append(f"Lot: {lot_size}")
        lines.append(f"PnL: {sign}${pnl:.2f} ({sign}{r_multiple:.2f}R)")
        if stop_loss > 0 or take_profit > 0:
            lines.append(f"SL: {stop_loss:.2f} | TP: {take_profit:.2f}")
        if duration:
            lines.append(f"ระยะเวลา: {duration}")
        if usdt_free > 0 or equity > 0:
            bal = usdt_free if usdt_free > 0 else equity
            lines.append(f"ยอดคงเหลือ USDT: ${bal:,.2f}")
        if btc_free > 0:
            lines.append(f"BTC free: {btc_free:.6f}")
        elif equity > 0 and usdt_free <= 0:
            lines.append(f"Equity: ${equity:,.2f}")
        return self.send_message("\n".join(lines))

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

    def notify_early_alert(self, kind: str, detail: str, price: float = 0.0) -> bool:
        """Watch-only: CAPITULATION_WATCH / EXHAUSTION_WATCH — never an entry."""
        if kind == "CAPITULATION_WATCH":
            emoji = "🔻"
            title = "CAPITULATION_WATCH (ไม่เข้าไม้)"
        elif kind == "EXHAUSTION_WATCH":
            emoji = "🔺"
            title = "EXHAUSTION_WATCH (ไม่เข้าไม้)"
        else:
            emoji = "👀"
            title = kind or "EARLY_ALERT"
        px = f"\nราคา: {price:.2f}" if price else ""
        msg = f"{emoji} {title}\n{detail}{px}\n(Alert เท่านั้น — ระบบไม่เปิดออเดอร์จากสัญญาณนี้)"
        return self.send_message(msg)
