#!/usr/bin/env python3
"""Paper / Testnet loop for BTCUSDT — S1 Trend PRIMARY (S2 off).

Modes:
  --dry-run     : analyze signal only (no order)  [default]
  --testnet     : place real orders on Binance Spot Testnet (requires API keys)
  --once        : single cycle then exit (default)
  --loop N      : repeat every --interval-sec seconds, N times (0 = forever)

Strategy (locked 2026-08-24):
  RegimeRouter enable_s2=False → S1 only
  H4 bias + ADX>=20 + min_confluence=0.62 + momentum cs1=0.5
  Risk: 0.5%/trade | SL 2.0 ATR | TP 3.6 ATR
  Streak: reduce@3→x0.5, deep@5→x0.25 (hard_halt=OFF)
  Daily DD kill: 3%

Usage:
  PYTHONPATH=. python scripts/paper_trade_btc.py --dry-run
  PYTHONPATH=. python scripts/paper_trade_btc.py --dry-run --loop 3 --interval-sec 60
  PYTHONPATH=. python scripts/paper_trade_btc.py --testnet --once
  PYTHONPATH=. python scripts/paper_trade_btc.py --testnet --loop 0 --interval-sec 300
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from config import settings
from core.data_loader import load_binance_klines, resample_ohlcv, load_yfinance
from core.binance_orders import BinanceOrderExt
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.mean_reversion import MeanReversionAgent
from agents.regime_router import RegimeRouter
from agents.risk_management import RiskManagementAgent
from agents.execution import ExecutionAgent
from agents.line_notifier import LineNotifierAgent
from agents.early_alert import EarlyAlertAgent

try:
    from utils.trade_log import TradeLogger
except Exception:
    TradeLogger = None  # type: ignore


def load_market_data(bars: int = 1500):
    """Prefer Binance public klines; fallback yfinance.

    Need enough M15 history so resampled H1 covers EMA200 (~200+ H1 bars
    ⇒ ~800+ M15). Default 1500 M15 ≈ 375 H1.
    Also loads W1 for higher-TF bias filter on H4-path entries.
    """
    try:
        # Load H1 directly when possible for cleaner EMA/ADX, plus M15 for entry TF
        m15 = load_binance_klines(symbol="BTCUSDT", interval="15m", max_bars=bars)
        try:
            h1 = load_binance_klines(symbol="BTCUSDT", interval="1h", max_bars=max(300, bars // 4))
        except Exception:
            h1 = resample_ohlcv(m15, "1h")
        try:
            h4 = load_binance_klines(symbol="BTCUSDT", interval="4h", max_bars=max(100, bars // 16))
        except Exception:
            h4 = resample_ohlcv(m15 if len(m15) else h1, "4h")
        try:
            w1 = load_binance_klines(symbol="BTCUSDT", interval="1w", max_bars=300)
        except Exception:
            base = h4 if len(h4) else h1
            w1 = resample_ohlcv(base, "1W")
        return m15, h1, h4, w1, "binance:BTCUSDT:15m"
    except Exception as e:
        print(f"[WARN] Binance klines failed ({e}) — try yfinance")
        try:
            h1 = load_yfinance(symbol="BTC-USD", interval="1h", period="60d")
            h4 = resample_ohlcv(h1, "4h")
            w1 = resample_ohlcv(h1, "1W")
            return h1, h1, h4, w1, "yfinance:BTC-USD:1h"
        except Exception as e2:
            raise RuntimeError(f"Cannot load market data: {e2}") from e2


def build_agents(mode: str):
    """S1 primary via RegimeRouter (S2 off) + momentum + streak ladder."""
    ta = TechnicalAnalysisAgent(
        require_h4=True,
        require_w1=True,
        w1_mode="no_oppose",
        min_confluence=0.62,
        require_adx=True,
        min_adx=20.0,
        require_h4_adx=True,
        min_h4_adx=25.0,
        require_momentum=True,
        momentum_slope_bars=1,
        momentum_against_atr=0.5,
    )
    mr = MeanReversionAgent(
        max_adx=20.0,
        require_low_adx=True,
        min_score=0.70,
        require_bb_width=True,
        max_atr_ratio=1.3,
        require_atr_filter=True,
    )
    # S1 risk profile with streak ladder (production)
    risk = RiskManagementAgent(
        risk_per_trade=getattr(settings, "RISK_PER_TRADE", 0.005) or 0.005,
        max_daily_drawdown=getattr(settings, "MAX_DAILY_DRAWDOWN", 0.03) or 0.03,
        max_open_positions=getattr(settings, "MAX_OPEN_POSITIONS", 1) or 1,
        min_reward_risk=1.8,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=3.6,
        enable_streak_control=True,
        streak_reduce_at=3,
        streak_deep_at=5,
        risk_scale_on_streak=0.5,
        risk_scale_deep=0.25,
        hard_halt_on_deep_streak=False,
    )
    router = RegimeRouter(
        trend_agent=ta,
        mr_agent=mr,
        risk_trend=risk,
        enable_s2=False,
        s2_mode="off",
        s2_max_adx=18.0,
    )
    binance = BinanceOrderExt(
        api_key=settings.BINANCE_API_KEY,
        api_secret=settings.BINANCE_API_SECRET,
        environment=settings.BINANCE_ENVIRONMENT,
        base_url=settings.BINANCE_BASE_URL or None,
    )
    exec_mode = "mock" if mode == "dry-run" else "binance"
    if mode == "testnet" and not binance.is_configured:
        print("[WARN] No Binance API keys — falling back to mock execution")
        exec_mode = "mock"
    execution = ExecutionAgent(
        binance_client=binance,
        mode=exec_mode,
        default_units_scale=settings.BINANCE_QTY_SCALE,
        default_symbol="BTCUSDT",
        attach_oco=True,
    )
    notifier = LineNotifierAgent(
        channel_access_token=settings.LINE_CHANNEL_ACCESS_TOKEN,
        user_id=settings.LINE_USER_ID,
    )
    logger = None
    if TradeLogger is not None:
        logger = TradeLogger(name="paper_s1", log_dir=ROOT / "logs")
    early = EarlyAlertAgent(vol_mult=2.5, rsi_low=30.0, rsi_high=70.0)
    return router, risk, execution, notifier, binance, logger, early


def on_paper_trade_closed(risk: RiskManagementAgent, won: bool, logger=None) -> None:
    """1.3 — update streak after a closed paper/testnet trade."""
    risk.record_trade_result(won=bool(won))
    # keep router risk in sync if it is a different instance
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


def one_cycle(router, risk, execution, notifier, logger, early, mode: str) -> dict:
    m15, h1, h4, w1, label = load_market_data()
    last_px = float(m15["close"].iloc[-1])
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] Data: {label} | bars={len(m15)} last={last_px:.2f} | W1={len(w1)}")

    # --- 1.1 Early Alert (watch-only, never enters) ---
    alert = early.check(h1, m15)
    if alert.active:
        print(f"  ALERT  : {alert.kind} | {alert.detail}")
        try:
            notifier.notify_early_alert(alert.kind, alert.detail, alert.price)
        except Exception as e:
            print(f"  [WARN] early-alert notify: {e}")
        if logger:
            try:
                logger.log_event("EARLY_ALERT", alert.to_dict())
            except Exception:
                pass
    else:
        print(f"  Alert  : idle (RSI={alert.rsi} vol={alert.vol_ratio}x)")

    # S1 via router (S2 off) — H4 path + W1 filter
    signal = router.analyze(m15, h1, h4, df_w1=w1)
    st = router.status()
    gate = getattr(signal, "gate", "") or ""
    w1b = getattr(signal, "w1_bias", "") or ""
    print(f"  Router : regime={st['regime']} strategy={st['strategy']} "
          f"ADX={st['adx']:.1f} s2_mode={st['s2_mode']}")
    print(f"  Bias   : H4={getattr(signal, 'timeframe_bias', '')} W1={w1b}")
    print(f"  Signal : {signal.direction} | strength={signal.strength}")
    if signal.direction == "NONE" and gate:
        print(f"  Gate   : {gate}")
    print(f"  Reason : {signal.reason}")
    print(f"  RSI={getattr(signal, 'rsi_value', None)} ATR={getattr(signal, 'atr', 0):.4f}")
    print(f"  Streak : losses={risk.consecutive_losses} scale={risk.current_risk_scale():.2f}")

    record = {
        "ts": ts,
        "price": last_px,
        "regime": st["regime"],
        "strategy": st["strategy"],
        "adx": st["adx"],
        "direction": signal.direction,
        "strength": float(signal.strength) if signal.strength is not None else 0.0,
        "reason": signal.reason,
        "gate": gate,
        "w1_bias": w1b,
        "h4_bias": getattr(signal, "timeframe_bias", ""),
        "early_alert": alert.to_dict() if alert else None,
        "streak_losses": risk.consecutive_losses,
        "risk_scale": risk.current_risk_scale(),
        "mode": mode,
    }

    if signal.direction == "NONE":
        record["action"] = "skip"
        if logger:
            try:
                logger.log_event("SIGNAL_NONE", record)
            except Exception:
                pass
        return record

    equity = 10000.0
    conn = execution.test_connection()
    if conn.get("balances"):
        usdt = conn["balances"].get("USDT") or {}
        if usdt.get("free"):
            equity = max(float(usdt["free"]), 100.0)

    # Prefer router risk profile for S1
    risk_agent = router.get_risk_agent()
    decision = risk_agent.calculate(
        equity=equity,
        entry_price=signal.entry_price,
        direction=signal.direction,
        atr=signal.atr,
        current_daily_pnl=0.0,
        open_positions=0,
        point=1.0,
        tick_value=1.0,
    )
    print(
        f"  Risk   : approved={decision.approved} lot={decision.lot_size} "
        f"SL={decision.stop_loss} TP={decision.take_profit} "
        f"scale={getattr(decision,'risk_scale',1.0)} "
        f"streak={getattr(decision,'consecutive_losses', risk_agent.consecutive_losses)} "
        f"| {decision.reason}"
    )
    record["approved"] = decision.approved
    record["lot"] = decision.lot_size
    record["sl"] = decision.stop_loss
    record["tp"] = decision.take_profit

    if not decision.approved:
        record["action"] = "rejected"
        if logger:
            try:
                logger.log_event("RISK_REJECT", record)
            except Exception:
                pass
        return record

    if mode == "dry-run":
        print("  [DRY-RUN] ไม่ส่งออเดอร์จริง — S1 signal logged only")
        record["action"] = "dry-run"
        if logger:
            try:
                logger.log_event("DRY_RUN_SIGNAL", record)
            except Exception:
                pass
        return record

    result = execution.place_order(
        symbol="BTCUSDT",
        direction=signal.direction,
        lot_size=decision.lot_size,
        stop_loss=decision.stop_loss,
        take_profit=decision.take_profit,
        comment="PaperS1-H4ADX",
    )
    print(
        f"  Order  : success={result.get('success')} ticket={result.get('ticket')} "
        f"msg={result.get('message')}"
    )
    record["action"] = "ordered"
    record["order"] = {
        "success": result.get("success"),
        "ticket": result.get("ticket"),
        "message": result.get("message"),
    }
    if logger:
        try:
            logger.log_event("ORDER", record)
        except Exception:
            pass

    try:
        notifier.notify_open_order(
            direction=signal.direction,
            symbol="BTCUSDT",
            entry_price=signal.entry_price,
            lot_size=decision.lot_size,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            risk_percent=getattr(decision, "risk_percent", settings.RISK_PER_TRADE * 100),
            rr=getattr(decision, "reward_risk_ratio", None) or 1.8,
            reason=str(signal.reason)[:120],
        )
    except Exception as e:
        print(f"  [WARN] notify failed: {e}")

    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="BTCUSDT Paper/Testnet — S1 only")
    parser.add_argument("--dry-run", action="store_true", help="analyze only, no orders")
    parser.add_argument("--testnet", action="store_true", help="use Binance testnet orders")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--loop", type=int, default=1, help="cycles (0=forever)")
    parser.add_argument("--interval-sec", type=int, default=300, help="seconds between cycles")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="after cycles, run gate/alert log summary (scripts/summarize_paper_logs.py)",
    )
    args = parser.parse_args()

    mode = "dry-run"
    if args.testnet:
        mode = "testnet"
        env = (settings.BINANCE_ENVIRONMENT or "testnet").lower()
        if env not in ("testnet", "demo"):
            print("ERROR: paper_trade_btc.py บังคับ testnet — ตั้ง BINANCE_ENVIRONMENT=testnet")
            return 2

    print("=" * 60)
    print("BTCUSDT Paper / Testnet — S1 TREND PRIMARY")
    print(f"Mode     : {mode}")
    print("Strategy : RegimeRouter enable_s2=False (S2 OFF)")
    print("Params   : W1 + H4 bias + ADX H1>=20 H4>=25 + conf>=0.62 + MOM cs1=0.5")
    print(f"Risk     : {getattr(settings,'RISK_PER_TRADE',0.005)*100:.2f}%/trade | SL 2.0 ATR | TP 3.6 ATR")
    print("Streak   : reduce@3→x0.5 | deep@5→x0.25 | hard_halt=OFF")
    print(f"Max DD   : {getattr(settings,'MAX_DAILY_DRAWDOWN',0.03)*100:.1f}% daily kill")
    print("=" * 60)

    router, risk, execution, notifier, binance, logger, early = build_agents(mode)
    conn = execution.test_connection()
    print(f"Execution: {execution.mode} | {conn.get('message')}")
    if conn.get("btcusdt_price") or conn.get("last_price"):
        print(f"BTC price: {conn.get('btcusdt_price') or conn.get('last_price')}")
    print(f"Router   : {router.status()}")
    print(f"TA mom   : require={router.trend_agent.require_momentum} "
          f"bars={router.trend_agent.momentum_slope_bars} "
          f"thr={router.trend_agent.momentum_against_atr}")
    print(f"Risk streak: losses={risk.consecutive_losses} scale={risk.current_risk_scale()}")
    print("EarlyAlert: vol≥2.5x + RSI≤30/≥70 → CAPITULATION/EXHAUSTION_WATCH (no entry)")

    cycles = args.loop if args.loop > 0 else 10**9
    for i in range(cycles):
        try:
            one_cycle(router, risk, execution, notifier, logger, early, mode)
        except Exception as e:
            print(f"[ERROR] cycle failed: {e}")
            import traceback
            traceback.print_exc()
        if i + 1 < cycles:
            print(f"  sleep {args.interval_sec}s ...")
            time.sleep(args.interval_sec)

    print("\nDone. Logs → logs/ (paper_s1_* if TradeLogger available)")
    if args.summary:
        try:
            from scripts.summarize_paper_logs import load_jsonl_files, summarize, print_report

            log_dir = ROOT / "logs"
            paths = sorted(log_dir.glob("paper_s1*.jsonl")) + sorted(
                log_dir.glob("*dryrun*.jsonl")
            )
            # de-dupe
            seen = set()
            uniq = []
            for p in paths:
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    uniq.append(p)
            rows = load_jsonl_files(uniq)
            print_report(summarize(rows), uniq)
        except Exception as e:
            print(f"[WARN] summary failed: {e}")
            print("  Manual: PYTHONPATH=. python scripts/summarize_paper_logs.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
