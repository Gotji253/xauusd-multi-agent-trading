"""Backtest Engine for XAUUSD Multi-Agent system.

Features:
- Next-bar OPEN entry (reduce look-ahead)
- Spread + Slippage + Commission
- Uses TechnicalAnalysisAgent + RiskManagementAgent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd

from agents.technical_analysis import TechnicalAnalysisAgent, Signal
from agents.risk_management import RiskManagementAgent, RiskDecision
from core.data_loader import generate_synthetic_xauusd  # noqa: F401


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    pnl: float
    r_multiple: float
    reason: str
    strength: float


@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    initial_equity: float = 10000.0
    final_equity: float = 10000.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_r: float = 0.0
    expectancy: float = 0.0
    sharpe_approx: float = 0.0
    data_source: str = ""


class BacktestEngine:
    def __init__(
        self,
        ta_agent: Optional[TechnicalAnalysisAgent] = None,
        risk_agent: Optional[RiskManagementAgent] = None,
        initial_equity: float = 10000.0,
        point: float = 0.01,
        tick_value: float = 1.0,
        commission_per_lot: float = 7.0,
        spread_points: float = 25.0,
        slippage_points: float = 5.0,
        cooldown_bars: int = 4,
    ):
        self.ta = ta_agent or TechnicalAnalysisAgent()
        self.risk = risk_agent or RiskManagementAgent(
            risk_per_trade=0.005,
            max_daily_drawdown=0.03,
            max_open_positions=1,
            min_reward_risk=1.8,
            atr_sl_multiplier=1.6,
            atr_tp_multiplier=3.0,
        )
        self.initial_equity = initial_equity
        self.point = point
        self.tick_value = tick_value
        self.commission_per_lot = commission_per_lot
        self.spread_points = spread_points
        self.slippage_points = slippage_points
        self.cooldown_bars = cooldown_bars

    def run(self, df_m15, df_h1, lookback_h1: int = 300, data_source: str = "") -> BacktestResult:
        m15 = self._normalize(df_m15)
        h1 = self._normalize(df_h1)
        equity = self.initial_equity
        equity_curve, equity_times, trades = [], [], []
        open_trade = None
        pending_signal = None
        pending_decision = None
        daily_pnl = 0.0
        current_day = None
        bars_since_last = 999
        start_idx = max(250, getattr(self.ta, "ema_trend", 200) + 10)
        start_idx = min(start_idx, max(len(m15) - 5, 1))

        for i in range(start_idx, len(m15) - 1):
            row = m15.iloc[i]
            ts = m15.index[i]
            day = ts.date()
            if current_day is None or day != current_day:
                daily_pnl = 0.0
                current_day = day
            equity_curve.append(equity)
            equity_times.append(ts)
            bars_since_last += 1

            if open_trade is not None:
                hit_sl, hit_tp, exit_price = self._check_exit(open_trade, row)
                if hit_sl or hit_tp:
                    pnl = self._calc_pnl(open_trade, exit_price)
                    equity += pnl
                    daily_pnl += pnl
                    open_trade.exit_time = ts
                    open_trade.exit_price = exit_price
                    open_trade.pnl = round(pnl, 2)
                    open_trade.r_multiple = round(self._calc_r(open_trade, exit_price), 2)
                    trades.append(open_trade)
                    open_trade = None
                    bars_since_last = 0
                continue

            if pending_signal is not None and pending_decision is not None:
                entry_price = self._apply_costs(float(row["open"]), pending_signal.direction, True)
                atr = pending_signal.atr
                if pending_signal.direction == "BUY":
                    sl = entry_price - atr * self.risk.atr_sl_multiplier
                    tp = entry_price + atr * self.risk.atr_tp_multiplier
                else:
                    sl = entry_price + atr * self.risk.atr_sl_multiplier
                    tp = entry_price - atr * self.risk.atr_tp_multiplier
                open_trade = Trade(
                    entry_time=ts, exit_time=None, direction=pending_signal.direction,
                    entry_price=round(entry_price, 2), exit_price=0.0,
                    stop_loss=round(sl, 2), take_profit=round(tp, 2),
                    lot_size=pending_decision.lot_size, pnl=0.0, r_multiple=0.0,
                    reason=pending_signal.reason, strength=pending_signal.strength,
                )
                pending_signal = pending_decision = None
                continue

            if bars_since_last < self.cooldown_bars:
                continue

            m15_window = m15.iloc[: i + 1]
            h1_window = h1[h1.index <= ts].tail(lookback_h1)
            if len(h1_window) < 50:
                continue

            signal = self.ta.analyze(m15_window, h1_window)
            if signal.direction == "NONE":
                continue

            decision = self.risk.calculate(
                equity=equity, entry_price=signal.entry_price, direction=signal.direction,
                atr=signal.atr, current_daily_pnl=daily_pnl, open_positions=0,
                point=self.point, tick_value=self.tick_value,
            )
            if not decision.approved:
                continue
            pending_signal, pending_decision = signal, decision

        if open_trade is not None:
            last_price = float(m15.iloc[-1]["close"])
            pnl = self._calc_pnl(open_trade, last_price)
            equity += pnl
            open_trade.exit_time = m15.index[-1]
            open_trade.exit_price = last_price
            open_trade.pnl = round(pnl, 2)
            open_trade.r_multiple = round(self._calc_r(open_trade, last_price), 2)
            trades.append(open_trade)

        if equity_curve:
            equity_curve.append(equity)
            equity_times.append(m15.index[-1])

        eq_series = pd.Series(equity_curve, index=pd.DatetimeIndex(equity_times))
        result = self._build_result(trades, eq_series, equity)
        result.data_source = data_source
        return result

    def _normalize(self, df):
        out = df.copy()
        if not isinstance(out.index, pd.DatetimeIndex):
            if "time" in out.columns:
                out = out.set_index("time")
            out.index = pd.to_datetime(out.index)
        out.index = pd.to_datetime(out.index).tz_localize(None)
        return out.sort_index()

    def _apply_costs(self, price, direction, is_entry):
        cost = (self.spread_points / 2.0 + self.slippage_points) * self.point
        if direction == "BUY":
            return price + cost if is_entry else price - cost
        return price - cost if is_entry else price + cost

    def _check_exit(self, trade, row):
        hit_sl = hit_tp = False
        exit_price = float(row["close"])
        if trade.direction == "BUY":
            if float(row["low"]) <= trade.stop_loss:
                hit_sl, exit_price = True, trade.stop_loss
            elif float(row["high"]) >= trade.take_profit:
                hit_tp, exit_price = True, trade.take_profit
        else:
            if float(row["high"]) >= trade.stop_loss:
                hit_sl, exit_price = True, trade.stop_loss
            elif float(row["low"]) <= trade.take_profit:
                hit_tp, exit_price = True, trade.take_profit
        if hit_sl or hit_tp:
            exit_price = self._apply_costs(exit_price, trade.direction, False)
        return hit_sl, hit_tp, exit_price

    def _calc_pnl(self, trade, exit_price):
        if trade.direction == "BUY":
            points = (exit_price - trade.entry_price) / self.point
        else:
            points = (trade.entry_price - exit_price) / self.point
        return points * self.tick_value * trade.lot_size - self.commission_per_lot * trade.lot_size

    def _calc_r(self, trade, exit_price):
        risk = abs(trade.entry_price - trade.stop_loss)
        if risk <= 0:
            return 0.0
        if trade.direction == "BUY":
            return (exit_price - trade.entry_price) / risk
        return (trade.entry_price - exit_price) / risk

    def _build_result(self, trades, equity_curve, final_equity):
        total = len(trades)
        if total == 0:
            return BacktestResult(trades=[], equity_curve=equity_curve, initial_equity=self.initial_equity, final_equity=final_equity)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / total * 100
        gp = sum(t.pnl for t in wins) if wins else 0.0
        gl = abs(sum(t.pnl for t in losses)) if losses else 1e-9
        pf = gp / gl if gl > 0 else 0.0
        avg_r = float(np.mean([t.r_multiple for t in trades]))
        expectancy = float(np.mean([t.pnl for t in trades]))
        peak = equity_curve.cummax()
        dd = (equity_curve - peak) / peak
        max_dd = float(dd.min()) * 100
        daily_eq = equity_curve.resample("1D").last().dropna()
        if len(daily_eq) > 5:
            rets = daily_eq.pct_change().dropna()
            sharpe = float(rets.mean() / (rets.std() + 1e-9) * np.sqrt(252))
        else:
            sharpe = 0.0
        return BacktestResult(
            trades=trades, equity_curve=equity_curve,
            initial_equity=self.initial_equity, final_equity=final_equity,
            total_return_pct=round((final_equity / self.initial_equity - 1) * 100, 2),
            max_drawdown_pct=round(max_dd, 2), win_rate=round(win_rate, 1),
            profit_factor=round(pf, 2), total_trades=total, avg_r=round(avg_r, 2),
            expectancy=round(expectancy, 2), sharpe_approx=round(sharpe, 2),
        )
