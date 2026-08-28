"""Acme-style successful Price Action features (bar-by-bar wick vs prior bar).

Buy success  : current low  < prior low  and body does not crash through.
Sell success : current high > prior high and body does not spike through.
Scores are ATR-normalized in [0, 1].
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.indicators import atr as atr_fn


def last_pa_snapshot(df: Optional[pd.DataFrame], atr_period: int = 14) -> dict:
    empty = {
        "pa_buy_score": 0.0,
        "pa_sell_score": 0.0,
        "pa_side": "NEUTRAL",
        "pa_strength": 0.0,
    }
    if df is None or len(df) < 3:
        return empty
    work = df.copy()
    if "atr" not in work.columns or pd.isna(work["atr"].iloc[-1]):
        work["atr"] = atr_fn(work["high"], work["low"], work["close"], atr_period)
    last = work.iloc[-1]
    prev = work.iloc[-2]
    atr_val = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    if atr_val <= 0:
        return empty

    prev_low = float(prev["low"])
    prev_high = float(prev["high"])
    curr_low = float(last["low"])
    curr_high = float(last["high"])
    body_low = min(float(last["open"]), float(last["close"]))
    body_high = max(float(last["open"]), float(last["close"]))

    buy_raw = (curr_low < prev_low) and (body_low > prev_low - 0.3 * atr_val)
    sell_raw = (curr_high > prev_high) and (body_high < prev_high + 0.3 * atr_val)

    buy_score = min(max(((prev_low - curr_low) / atr_val) * 1.5, 0.0), 1.0) if buy_raw else 0.0
    sell_score = min(max(((curr_high - prev_high) / atr_val) * 1.5, 0.0), 1.0) if sell_raw else 0.0

    if buy_score > sell_score + 0.15:
        side = "BUY"
    elif sell_score > buy_score + 0.15:
        side = "SELL"
    else:
        side = "NEUTRAL"

    return {
        "pa_buy_score": round(buy_score, 4),
        "pa_sell_score": round(sell_score, 4),
        "pa_side": side,
        "pa_strength": round(max(buy_score, sell_score), 4),
    }


def combine_h1_h4(h1_snap: dict, h4_snap: dict) -> dict:
    h4_side = h4_snap.get("pa_side") or "NEUTRAL"
    h1_side = h1_snap.get("pa_side") or "NEUTRAL"
    strength = float(h1_snap.get("pa_strength") or 0.0)
    if h4_side != "NEUTRAL" and h1_side == h4_side:
        strength = min(1.0, strength + 0.15)
    return {
        "pa_buy_score": float(h1_snap.get("pa_buy_score") or 0.0),
        "pa_sell_score": float(h1_snap.get("pa_sell_score") or 0.0),
        "pa_side": h1_side,
        "pa_h4_side": h4_side,
        "pa_strength": round(strength, 4),
    }
