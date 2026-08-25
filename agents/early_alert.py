"""Early Alert Agent — watch-only signals (no trade entry).

Research (2026-08-24 pre-rally study):
  Capitulation / exhaustion often shows:
    - Volume ≥ 2.5× SMA20
    - RSI H1 ≤ 30  (CAPITULATION_WATCH)
    - RSI H1 ≥ 70  (EXHAUSTION_WATCH)

These are alerts only. Do NOT open positions from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

from core.indicators import rsi


@dataclass
class EarlyAlert:
    active: bool
    kind: str  # CAPITULATION_WATCH | EXHAUSTION_WATCH | ""
    rsi: float
    vol_ratio: float
    price: float
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


class EarlyAlertAgent:
    """Volume climax + RSI extreme detector (H1 preferred, else M15)."""

    def __init__(
        self,
        vol_mult: float = 2.5,
        rsi_low: float = 30.0,
        rsi_high: float = 70.0,
        rsi_period: int = 14,
        vol_sma_period: int = 20,
        cooldown_bars: int = 4,  # suppress re-fire for N bars of same kind
    ):
        self.vol_mult = vol_mult
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.rsi_period = rsi_period
        self.vol_sma_period = vol_sma_period
        self.cooldown_bars = cooldown_bars
        self._last_kind: str = ""
        self._last_bar_ts = None
        self._bars_since: int = 999

    def check(self, df_h1: Optional[pd.DataFrame], df_m15: Optional[pd.DataFrame] = None) -> EarlyAlert:
        """Return alert from latest completed bar. Prefer H1."""
        df = None
        if df_h1 is not None and len(df_h1) >= max(self.vol_sma_period, self.rsi_period) + 2:
            df = df_h1
        elif df_m15 is not None and len(df_m15) >= max(self.vol_sma_period, self.rsi_period) + 2:
            df = df_m15
        if df is None:
            return EarlyAlert(False, "", 50.0, 0.0, 0.0, "data insufficient")

        work = df.copy()
        if "rsi" not in work.columns or work["rsi"].isna().iloc[-1]:
            work["rsi"] = rsi(work["close"], self.rsi_period)
        vol_col = None
        for c in ("volume", "vol", "Volume"):
            if c in work.columns:
                vol_col = c
                break
        if vol_col is None:
            return EarlyAlert(
                False, "", 50.0, 0.0, float(work["close"].iloc[-1]), "no volume column"
            )
        vol_sma = work[vol_col].rolling(self.vol_sma_period).mean()
        last_vol = float(work[vol_col].iloc[-1]) if not pd.isna(work[vol_col].iloc[-1]) else 0.0
        sma_v = float(vol_sma.iloc[-1]) if not pd.isna(vol_sma.iloc[-1]) else 0.0
        vol_ratio = (last_vol / sma_v) if sma_v > 0 else 0.0
        rsi_v = float(work["rsi"].iloc[-1]) if not pd.isna(work["rsi"].iloc[-1]) else 50.0
        price = float(work["close"].iloc[-1])
        ts = work.index[-1]

        # cooldown tracking
        if self._last_bar_ts is not None and ts != self._last_bar_ts:
            self._bars_since += 1
        self._last_bar_ts = ts

        kind = ""
        if vol_ratio >= self.vol_mult and rsi_v <= self.rsi_low:
            kind = "CAPITULATION_WATCH"
        elif vol_ratio >= self.vol_mult and rsi_v >= self.rsi_high:
            kind = "EXHAUSTION_WATCH"

        if not kind:
            return EarlyAlert(False, "", round(rsi_v, 1), round(vol_ratio, 2), price, "no extreme")

        # suppress duplicate same-kind within cooldown
        if kind == self._last_kind and self._bars_since < self.cooldown_bars:
            return EarlyAlert(
                False,
                kind,
                round(rsi_v, 1),
                round(vol_ratio, 2),
                price,
                f"cooldown ({self._bars_since}/{self.cooldown_bars})",
            )

        self._last_kind = kind
        self._bars_since = 0
        detail = (
            f"{kind}: RSI={rsi_v:.1f} vol={vol_ratio:.2f}x "
            f"(thr vol≥{self.vol_mult} RSI≤{self.rsi_low}/≥{self.rsi_high}) px={price:.2f}"
        )
        return EarlyAlert(True, kind, round(rsi_v, 1), round(vol_ratio, 2), price, detail)
