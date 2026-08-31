"""H4 EMA squeeze → breakout (pattern from 16–19 Aug 2026 BTC).

Circle on chart = compression (EMA50/100/200 tight).
Entry quality = first expansion: close above all EMAs + vol/ADX lift.
"""

from __future__ import annotations

import pandas as pd

from core.indicators import adx, atr, ema


def h4_squeeze_breakout(
    df_h4: pd.DataFrame | None,
    *,
    ema_fast: int = 50,
    ema_mid: int = 100,
    ema_slow: int = 200,
    squeeze_pct: float = 0.018,
    lookback: int = 12,
    vol_mult: float = 1.4,
    adx_period: int = 14,
) -> dict:
    empty = {
        "squeeze_now": False,
        "squeeze_recent": False,
        "breakout_buy": False,
        "breakout_sell": False,
        "ribbon_width_pct": 0.0,
        "vol_ratio": 0.0,
        "adx_up": False,
        "above": False,
        "below": False,
        "aligned": False,
        "aligned_down": False,
    }
    if df_h4 is None or len(df_h4) < max(ema_slow + 5, lookback + 5):
        return empty

    close = df_h4["close"]
    e50 = ema(close, ema_fast)
    e100 = ema(close, ema_mid)
    e200 = ema(close, ema_slow)
    ribbon_hi = pd.concat([e50, e100, e200], axis=1).max(axis=1)
    ribbon_lo = pd.concat([e50, e100, e200], axis=1).min(axis=1)
    width = (ribbon_hi - ribbon_lo) / close.replace(0, 1e-10)
    squeeze = width < squeeze_pct

    last_c = float(close.iloc[-1])
    last_e50 = float(e50.iloc[-1])
    last_e100 = float(e100.iloc[-1])
    last_e200 = float(e200.iloc[-1])
    above = last_c > last_e50 and last_c > last_e100 and last_c > last_e200
    below = last_c < last_e50 and last_c < last_e100 and last_c < last_e200
    aligned = last_e50 > last_e100 > last_e200
    aligned_down = last_e50 < last_e100 < last_e200
    squeeze_now = bool(squeeze.iloc[-1])
    squeeze_recent = bool(squeeze.iloc[-lookback:].any())

    vol_ratio = 1.0
    if "volume" in df_h4.columns:
        vol = df_h4["volume"].astype(float)
        vol_sma = vol.rolling(20, min_periods=5).mean()
        if float(vol_sma.iloc[-1] or 0) > 0:
            vol_ratio = float(vol.iloc[-1]) / float(vol_sma.iloc[-1])

    adx_s = adx(df_h4["high"], df_h4["low"], df_h4["close"], adx_period)
    adx_up = False
    if len(adx_s) >= 3 and not pd.isna(adx_s.iloc[-1]) and not pd.isna(adx_s.iloc[-3]):
        adx_up = float(adx_s.iloc[-1]) > float(adx_s.iloc[-3])

    prior_high = float(df_h4["high"].iloc[-lookback:-1].max()) if lookback > 1 else last_c
    prior_low = float(df_h4["low"].iloc[-lookback:-1].min()) if lookback > 1 else last_c
    breakout_buy = (
        squeeze_recent
        and not squeeze_now
        and above
        and last_c >= prior_high
        and (vol_ratio >= vol_mult or adx_up)
    )
    breakout_sell = (
        squeeze_recent
        and not squeeze_now
        and below
        and last_c <= prior_low
        and (vol_ratio >= vol_mult or adx_up)
    )

    return {
        "squeeze_now": squeeze_now,
        "squeeze_recent": squeeze_recent,
        "breakout_buy": bool(breakout_buy),
        "breakout_sell": bool(breakout_sell),
        "ribbon_width_pct": float(width.iloc[-1]) * 100.0,
        "vol_ratio": float(vol_ratio),
        "adx_up": bool(adx_up),
        "above": bool(above),
        "below": bool(below),
        "aligned": bool(aligned),
        "aligned_down": bool(aligned_down),
    }
