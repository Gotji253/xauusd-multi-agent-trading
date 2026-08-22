"""Chart generation for Backtest results."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from backtest.engine import BacktestResult
from core.indicators import ema, rsi


def plot_backtest_result(
    result: BacktestResult,
    df_m15: Optional[pd.DataFrame] = None,
    save_path: str | Path = "backtest_result.png",
    title: str = "XAUUSD Multi-Agent Backtest",
) -> Path:
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [3, 1.2, 1.5]})
    src = f" | {result.data_source}" if result.data_source else ""
    fig.suptitle(title + src, fontsize=13, fontweight="bold")
    eq = result.equity_curve
    ax1 = axes[0]
    ax1.plot(eq.index, eq.values, color="#1f77b4", linewidth=1.5, label="Equity")
    ax1.axhline(result.initial_equity, color="gray", linestyle="--", alpha=0.6)
    ax1.set_ylabel("Equity ($)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(
        f"Return: {result.total_return_pct:+.2f}% | MaxDD: {result.max_drawdown_pct:.2f}% | "
        f"Trades: {result.total_trades} | WR: {result.win_rate:.1f}% | PF: {result.profit_factor:.2f} | "
        f"AvgR: {result.avg_r:.2f} | Exp: ${result.expectancy:.2f}"
    )
    ax2 = axes[1]
    peak = eq.cummax()
    dd = (eq - peak) / peak * 100
    ax2.fill_between(dd.index, dd.values, 0, color="#d62728", alpha=0.4)
    ax2.plot(dd.index, dd.values, color="#d62728", linewidth=0.8)
    ax2.set_ylabel("Drawdown %")
    ax2.grid(True, alpha=0.3)
    ymin = min(float(dd.min()) * 1.1, -1) if len(dd) else -5
    ax2.set_ylim(ymin, 1)
    ax3 = axes[2]
    if result.trades:
        pnls = [t.pnl for t in result.trades]
        colors = ["#2ca02c" if p > 0 else "#d62728" for p in pnls]
        ax3.bar(range(len(pnls)), pnls, color=colors, alpha=0.8)
        ax3.axhline(0, color="black", linewidth=0.8)
        ax3.set_xlabel("Trade #")
        ax3.set_ylabel("PnL ($)")
        ax3.grid(True, alpha=0.3)
    else:
        ax3.text(0.5, 0.5, "No trades", ha="center", va="center", transform=ax3.transAxes)
    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return save_path


def plot_price_with_signals(
    df: pd.DataFrame,
    trades: list = None,
    save_path: str | Path = "price_signals.png",
    title: str = "XAUUSD Price + Indicators",
) -> Path:
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    if "ema_fast" not in df.columns:
        df["ema_fast"] = ema(df["close"], 20)
        df["ema_slow"] = ema(df["close"], 50)
        df["rsi"] = rsi(df["close"], 14)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    ax1.plot(df.index, df["close"], color="black", linewidth=1.0, label="Close", alpha=0.9)
    ax1.plot(df.index, df["ema_fast"], color="#ff7f0e", linewidth=1.0, label="EMA20", alpha=0.8)
    ax1.plot(df.index, df["ema_slow"], color="#1f77b4", linewidth=1.0, label="EMA50", alpha=0.8)
    if trades:
        for t in trades:
            color = "#2ca02c" if t.direction == "BUY" else "#d62728"
            marker = "^" if t.direction == "BUY" else "v"
            ax1.scatter(t.entry_time, t.entry_price, color=color, marker=marker, s=80, zorder=5)
            if t.exit_time is not None:
                ax1.scatter(t.exit_time, t.exit_price, color=color, marker="x", s=60, zorder=5)
                ax1.plot([t.entry_time, t.exit_time], [t.entry_price, t.exit_price], color=color, alpha=0.35, linewidth=1)
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax2.plot(df.index, df["rsi"], color="#9467bd", linewidth=1.0)
    ax2.axhline(70, color="red", linestyle="--", alpha=0.5)
    ax2.axhline(30, color="green", linestyle="--", alpha=0.5)
    ax2.axhline(50, color="gray", linestyle=":", alpha=0.5)
    ax2.set_ylabel("RSI(14)")
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return save_path
