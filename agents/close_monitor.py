"""Close-position monitor: detect OCO TP/SL fills and notify LINE + balance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agents.line_notifier import LineNotifierAgent
from agents.risk_management import RiskManagementAgent

try:
    from utils.runtime_state import get_runtime_state
except Exception:  # pragma: no cover
    get_runtime_state = None  # type: ignore

SYMBOL = "BTCUSDT"
PROTECTIVE_TYPES = {
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_LIMIT",
    "STOP",
    "STOP_MARKET",
    "TAKE_PROFIT_MARKET",
}


def _has_protective_orders(open_orders: list) -> bool:
    for o in open_orders or []:
        t = str(o.get("type") or "").upper()
        if t in PROTECTIVE_TYPES:
            return True
        if o.get("orderListId") not in (None, "", 0, "0"):
            return True
    return False


def _parse_iso_ms(iso_ts: str) -> int:
    if not iso_ts:
        return 0
    try:
        s = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def _classify_exit(exit_price: float, stop_loss: float, take_profit: float, direction: str) -> str:
    if exit_price <= 0:
        return "CLOSE"
    d = (direction or "BUY").upper()
    dist_sl = abs(exit_price - stop_loss) if stop_loss else 1e18
    dist_tp = abs(exit_price - take_profit) if take_profit else 1e18
    tol = max(exit_price * 0.0015, 30.0)
    if dist_tp <= tol and dist_tp <= dist_sl:
        return "TP"
    if dist_sl <= tol and dist_sl < dist_tp:
        return "SL"
    if d == "BUY":
        if take_profit and exit_price >= take_profit - tol:
            return "TP"
        if stop_loss and exit_price <= stop_loss + tol:
            return "SL"
    else:
        if take_profit and exit_price <= take_profit + tol:
            return "TP"
        if stop_loss and exit_price >= stop_loss - tol:
            return "SL"
    return "CLOSE"


def _duration_str(opened_at_iso: str) -> str:
    if not opened_at_iso:
        return "-"
    try:
        s = opened_at_iso.replace("Z", "+00:00")
        start = datetime.fromisoformat(s)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        secs = max(0, int((now - start).total_seconds()))
        if secs < 60:
            return f"{secs} วินาที"
        if secs < 3600:
            return f"{secs // 60} นาที"
        return f"{secs // 3600} ชม. {(secs % 3600) // 60} นาที"
    except Exception:
        return "-"


def on_trade_closed(risk: RiskManagementAgent, won: bool, logger=None) -> None:
    risk.record_trade_result(won=bool(won))
    msg = (
        f"trade closed won={won} streak_losses={risk.consecutive_losses} "
        f"scale={risk.current_risk_scale():.2f}"
    )
    print(f"  Streak update: {msg}")
    if logger:
        try:
            logger.log_event(
                "TRADE_CLOSED",
                {
                    "won": bool(won),
                    "streak_losses": risk.consecutive_losses,
                    "risk_scale": risk.current_risk_scale(),
                },
            )
        except Exception:
            pass


def track_open_position(
    *,
    direction: str,
    quantity: float,
    ticket: Any = None,
    oco_id: Any = None,
    entry_price: float = 0.0,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    strategy: str = "S1_TREND",
    protected: bool = False,
) -> None:
    if get_runtime_state is None:
        return
    get_runtime_state().set_open_position(
        SYMBOL,
        direction=direction,
        quantity=quantity,
        ticket=ticket,
        oco_id=oco_id,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        strategy=strategy,
        protected=protected,
    )


def has_open_position() -> bool:
    if get_runtime_state is None:
        return False
    return get_runtime_state().get_open_position(SYMBOL) is not None


def check_and_notify_closed_positions(
    binance,
    risk: RiskManagementAgent,
    notifier: LineNotifierAgent,
    logger=None,
    mode: str = "testnet",
) -> list[dict]:
    """Detect OCO/SL/TP fills; notify LINE with details + remaining balance."""
    closed: list[dict] = []
    if get_runtime_state is None or mode == "dry-run":
        return closed
    if binance is None or not getattr(binance, "is_configured", False):
        return closed

    state = get_runtime_state()
    pos = state.get_open_position(SYMBOL)
    if not pos:
        return closed

    oo = binance.get_open_orders(SYMBOL)
    open_orders = oo.get("data") if oo.get("ok") else []
    if not isinstance(open_orders, list):
        open_orders = []
    if _has_protective_orders(open_orders):
        print(
            f"  Position: OPEN (protected) qty={pos.get('quantity')} dir={pos.get('direction')}"
        )
        return closed

    direction = str(pos.get("direction") or "BUY").upper()
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("quantity") or 0)
    sl = float(pos.get("stop_loss") or 0)
    tp = float(pos.get("take_profit") or 0)
    opened_at = str(pos.get("at") or "")
    start_ms = _parse_iso_ms(opened_at)

    exit_price = 0.0
    exit_qty = 0.0
    try:
        if hasattr(binance, "get_my_trades"):
            trades_res = binance.get_my_trades(SYMBOL, limit=30, start_time=start_ms or None)
            trades = trades_res.get("data") if trades_res.get("ok") else []
            if isinstance(trades, list):
                want_buy = direction == "SELL"
                for t in reversed(trades):
                    is_buyer = bool(t.get("isBuyer"))
                    if is_buyer != want_buy:
                        continue
                    px = float(t.get("price") or 0)
                    q = float(t.get("qty") or t.get("quantity") or 0)
                    if px > 0 and q > 0:
                        exit_price = px
                        exit_qty = q
                        break
    except Exception as e:
        print(f"  [WARN] get_my_trades: {e}")

    if exit_price <= 0:
        try:
            tick = binance.get_ticker_price(SYMBOL)
            if tick.get("ok"):
                exit_price = float((tick.get("data") or {}).get("price") or 0)
        except Exception:
            pass

    if exit_qty <= 0:
        exit_qty = qty

    if direction == "BUY":
        pnl = (exit_price - entry) * exit_qty if entry and exit_price else 0.0
        risk_dist = abs(entry - sl) if sl else 0.0
    else:
        pnl = (entry - exit_price) * exit_qty if entry and exit_price else 0.0
        risk_dist = abs(sl - entry) if sl else 0.0
    risk_amt = risk_dist * exit_qty if risk_dist > 0 else 0.0
    r_mult = (pnl / risk_amt) if risk_amt > 0 else 0.0
    reason = _classify_exit(exit_price, sl, tp, direction)
    won = pnl >= 0

    usdt_free = btc_free = 0.0
    equity = 0.0
    try:
        bals = binance.get_balances_map() if hasattr(binance, "get_balances_map") else {}
        usdt_free = float((bals.get("USDT") or {}).get("free") or 0)
        btc_free = float((bals.get("BTC") or {}).get("free") or 0)
        px = exit_price
        if px <= 0:
            tick = binance.get_ticker_price(SYMBOL)
            if tick.get("ok"):
                px = float((tick.get("data") or {}).get("price") or 0)
        equity = usdt_free + btc_free * px
    except Exception as e:
        print(f"  [WARN] balance fetch: {e}")

    duration = _duration_str(opened_at)
    print(
        f"  CLOSE  : {direction} {reason} entry={entry:.2f} exit={exit_price:.2f} "
        f"pnl={pnl:+.2f} ({r_mult:+.2f}R) USDT={usdt_free:.2f}"
    )

    try:
        notifier.notify_close_order(
            direction=direction,
            symbol=SYMBOL,
            pnl=pnl,
            r_multiple=r_mult,
            duration=duration,
            equity=equity or usdt_free,
            exit_reason=reason,
            entry_price=entry,
            exit_price=exit_price,
            lot_size=exit_qty or qty,
            stop_loss=sl,
            take_profit=tp,
            usdt_free=usdt_free,
            btc_free=btc_free,
        )
    except Exception as e:
        print(f"  [WARN] close notify failed: {e}")

    on_trade_closed(risk, won=won, logger=logger)
    state.clear_open_position(SYMBOL)

    rec = {
        "action": "closed",
        "direction": direction,
        "exit_reason": reason,
        "entry_price": entry,
        "exit_price": exit_price,
        "pnl": pnl,
        "r_multiple": r_mult,
        "usdt_free": usdt_free,
        "btc_free": btc_free,
        "equity": equity,
    }
    if logger:
        try:
            logger.log_event("POSITION_CLOSED", rec)
        except Exception:
            pass
    closed.append(rec)
    return closed
