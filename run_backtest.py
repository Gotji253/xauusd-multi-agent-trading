#!/usr/bin/env python3
"""รัน Backtest กับข้อมูล synthetic / yfinance (ทองจริง) / CSV

ตัวอย่าง:
  python run_backtest.py
  python run_backtest.py --source yfinance
  python run_backtest.py --source yfinance --symbol GC=F --interval 1h --period 730d
  python run_backtest.py --source csv --csv data/xauusd_m15.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.data_loader import load_xauusd_data
from backtest.engine import BacktestEngine
from backtest.charts import plot_backtest_result, plot_price_with_signals
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent


def parse_args():
    p = argparse.ArgumentParser(description="XAUUSD Multi-Agent Backtest")
    p.add_argument("--source", choices=["synthetic", "yfinance", "csv"], default="synthetic")
    p.add_argument("--csv", type=str, default=None)
    p.add_argument("--symbol", type=str, default="GC=F")
    p.add_argument("--interval", type=str, default="15m")
    p.add_argument("--period", type=str, default="60d")
    p.add_argument("--bars", type=int, default=5000)
    p.add_argument("--equity", type=float, default=10000.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 60)
    print("XAUUSD Multi-Agent Backtest")
    print("Data source: synthetic | yfinance | csv")
    print("=" * 60)

    print(f"\n[1/4] Loading data (source={args.source})...")
    df_m15, df_h1, label = load_xauusd_data(
        source=args.source,
        csv_path=args.csv,
        symbol=args.symbol,
        interval=args.interval,
        period=args.period,
        n_bars=args.bars,
    )
    print(f"      Source  : {label}")
    print(f"      Bars    : M15/TF={len(df_m15)} | H1={len(df_h1)}")
    print(f"      Period  : {df_m15.index[0]} -> {df_m15.index[-1]}")
    print(f"      Last px : {float(df_m15['close'].iloc[-1]):.2f}")

    print("\n[2/4] Initializing Agents...")
    ta = TechnicalAnalysisAgent(min_confluence=0.62, rsi_oversold=32.0, rsi_overbought=68.0, pullback_atr_mult=0.5, min_atr=1.5)
    risk = RiskManagementAgent(risk_per_trade=0.005, max_daily_drawdown=0.03, max_open_positions=1, min_reward_risk=1.8, atr_sl_multiplier=1.6, atr_tp_multiplier=3.0)

    print("\n[3/4] Running backtest...")
    engine = BacktestEngine(ta_agent=ta, risk_agent=risk, initial_equity=args.equity, spread_points=25.0, slippage_points=5.0, commission_per_lot=7.0)
    result = engine.run(df_m15, df_h1, data_source=label)

    print("\n[4/4] Results")
    print("-" * 40)
    print(f"Data Source      : {result.data_source}")
    print(f"Initial Equity   : ${result.initial_equity:,.2f}")
    print(f"Final Equity     : ${result.final_equity:,.2f}")
    print(f"Total Return     : {result.total_return_pct:+.2f}%")
    print(f"Max Drawdown     : {result.max_drawdown_pct:.2f}%")
    print(f"Total Trades     : {result.total_trades}")
    print(f"Win Rate         : {result.win_rate:.1f}%")
    print(f"Profit Factor    : {result.profit_factor:.2f}")
    print(f"Average R        : {result.avg_r:.2f}")
    print(f"Expectancy $/tr  : ${result.expectancy:.2f}")
    print(f"Sharpe (approx)  : {result.sharpe_approx:.2f}")
    print("-" * 40)

    out_dir = Path("backtest_output")
    out_dir.mkdir(exist_ok=True)
    eq_path = plot_backtest_result(result, save_path=out_dir / "equity_and_trades.png", title="XAUUSD Backtest")
    print(f"\nSaved equity chart -> {eq_path}")
    tail = df_m15.tail(min(600, len(df_m15))).copy()
    price_path = plot_price_with_signals(tail, trades=result.trades, save_path=out_dir / "price_signals.png", title=f"Price + Signals ({label})")
    print(f"Saved price chart  -> {price_path}")

    if result.trades:
        print("\nLast 5 trades:")
        for t in result.trades[-5:]:
            sign = "+" if t.pnl >= 0 else ""
            print(f"  {t.entry_time.strftime('%Y-%m-%d %H:%M')} {t.direction:4} @ {t.entry_price:.2f} -> {t.exit_price:.2f} | PnL {sign}{t.pnl:.2f} ({sign}{t.r_multiple:.2f}R)")

    print("\nTips:")
    print("  python run_backtest.py --source yfinance")
    print("  python run_backtest.py --source yfinance --interval 1h --period 730d")
    print("  python run_backtest.py --source csv --csv path/to/xauusd.csv")
    print("\nDone.")


if __name__ == "__main__":
    main()
