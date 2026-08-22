#!/usr/bin/env python3
"""รัน Backtest ที่ปรับพารามิเตอร์ให้แม่นยำขึ้น

python run_backtest.py
"""

from __future__ import annotations

from pathlib import Path

from backtest.engine import BacktestEngine, generate_synthetic_xauusd
from backtest.charts import plot_backtest_result, plot_price_with_signals
from agents.technical_analysis import TechnicalAnalysisAgent
from agents.risk_management import RiskManagementAgent


def main() -> None:
    print("=" * 60)
    print("XAUUSD Multi-Agent Backtest (Improved Accuracy)")
    print("Focus: Realistic costs + Stricter signals + Controlled risk")
    print("=" * 60)

    print("\n[1/4] Generating realistic synthetic XAUUSD data...")
    df_m15, df_h1 = generate_synthetic_xauusd(n_bars=5000, start_price=2350.0, seed=42)
    print(f"      M15 bars: {len(df_m15)} | H1 bars: {len(df_h1)}")
    print(f"      Period  : {df_m15.index[0]} -> {df_m15.index[-1]}")

    print("\n[2/4] Initializing Agents (stricter parameters)...")
    ta = TechnicalAnalysisAgent(
        min_confluence=0.62,
        rsi_oversold=32.0,
        rsi_overbought=68.0,
        pullback_atr_mult=0.5,
        min_atr=1.5,
    )
    risk = RiskManagementAgent(
        risk_per_trade=0.005,
        max_daily_drawdown=0.03,
        max_open_positions=1,
        min_reward_risk=1.8,
        atr_sl_multiplier=1.6,
        atr_tp_multiplier=3.0,
    )

    print("\n[3/4] Running backtest with spread/slippage/next-bar entry...")
    engine = BacktestEngine(
        ta_agent=ta,
        risk_agent=risk,
        initial_equity=10000.0,
        point=0.01,
        tick_value=1.0,
        commission_per_lot=7.0,
        spread_points=25.0,
        slippage_points=5.0,
    )
    result = engine.run(df_m15, df_h1)

    print("\n[4/4] Results")
    print("-" * 40)
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
    eq_path = plot_backtest_result(result, save_path=out_dir / "equity_and_trades.png", title="XAUUSD Backtest (Improved Accuracy)")
    print(f"\nSaved equity chart -> {eq_path}")
    tail = df_m15.tail(600).copy()
    price_path = plot_price_with_signals(tail, trades=result.trades, save_path=out_dir / "price_signals.png", title="XAUUSD Price + Signals (last 600 bars)")
    print(f"Saved price chart  -> {price_path}")

    print("\nParameters used for higher accuracy:")
    print("  - Entry at next bar OPEN (reduce look-ahead)")
    print("  - Spread 25 points + Slippage 5 points")
    print("  - Commission $7/lot round-turn")
    print("  - Risk 0.5%/trade | Min confluence 0.62 | Min R:R 1.8")
    print("  - Cooldown 4 bars after close | H1 bias must match direction")
    print("\nDone. Synthetic data only — not a guarantee of live profit.")


if __name__ == "__main__":
    main()
