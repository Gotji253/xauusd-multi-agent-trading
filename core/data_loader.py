"""Data Loader for XAUUSD / Gold — synthetic, CSV, yfinance.

รองรับ:
- synthetic: ข้อมูลจำลองสำหรับ unit test / CI
- csv: ไฟล์ OHLCV จริง (คอลัมน์ time/datetime, open, high, low, close)
- yfinance: ราคาทองจริงจาก Yahoo Finance (GC=F Gold Futures)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd


REQUIRED_COLS = ("open", "high", "low", "close")


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]

    time_candidates = ("time", "datetime", "date", "timestamp", "dt")
    time_col = next((c for c in time_candidates if c in out.columns), None)

    if not isinstance(out.index, pd.DatetimeIndex):
        if time_col is not None:
            out[time_col] = pd.to_datetime(out[time_col], utc=False)
            out = out.set_index(time_col)
        else:
            out.index = pd.to_datetime(out.index, utc=False)

    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.sort_index()

    missing = [c for c in REQUIRED_COLS if c not in out.columns]
    if missing:
        raise ValueError(f"ขาดคอลัมน์ OHLCV: {missing} — มีอยู่: {list(out.columns)}")

    out = out[list(REQUIRED_COLS)].astype(float)
    out = out.dropna()
    out = out[out["high"] >= out["low"]]
    return out


def load_csv(path: str | Path, datetime_col: Optional[str] = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ CSV: {path}")
    df = pd.read_csv(path)
    if datetime_col and datetime_col in df.columns:
        df = df.rename(columns={datetime_col: "time"})
    return _normalize_ohlcv(df)


def load_yfinance(
    symbol: str = "GC=F",
    interval: str = "15m",
    period: str = "60d",
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("ต้องติดตั้ง yfinance ก่อน: pip install yfinance") from e

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(
            f"yfinance ไม่คืนข้อมูลสำหรับ {symbol} interval={interval} period={period}"
        )
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    return _normalize_ohlcv(df)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    ohlc = (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    return ohlc


def generate_synthetic_xauusd(
    n_bars: int = 5000,
    start_price: float = 2350.0,
    seed: int = 42,
    freq: str = "15min",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq=freq)
    returns = np.zeros(n_bars)
    vol = 0.0010
    for i in range(n_bars):
        if i > 0:
            vol = 0.92 * vol + 0.08 * abs(returns[i - 1]) + 0.00015
        if i % 350 == 0 and i > 0:
            vol *= 1.6
        if i % 500 == 0 and i > 0:
            vol *= 0.7
        trend = 0.00001 * np.sin(i / 180.0)
        returns[i] = np.random.normal(trend, vol)
    close = start_price * np.exp(np.cumsum(returns))
    noise = np.abs(np.random.normal(0, 1.2, n_bars))
    high = close + noise
    low = close - noise
    open_ = np.roll(close, 1)
    open_[0] = start_price
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    m15 = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=dates,
    )
    h1 = resample_ohlcv(m15, "1h")
    return m15, h1


def load_xauusd_data(
    source: str = "synthetic",
    csv_path: Optional[str] = None,
    symbol: str = "GC=F",
    interval: str = "15m",
    period: str = "60d",
    n_bars: int = 5000,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    source = source.lower().strip()
    if source == "synthetic":
        m15, h1 = generate_synthetic_xauusd(n_bars=n_bars, seed=seed)
        return m15, h1, "synthetic"
    if source == "csv":
        if not csv_path:
            raise ValueError("source=csv ต้องระบุ --csv path/to/file.csv")
        m15 = load_csv(csv_path)
        h1 = resample_ohlcv(m15, "1h")
        if len(h1) < 50:
            h1 = m15.copy()
        return m15, h1, f"csv:{csv_path}"
    if source in ("yfinance", "yahoo", "live"):
        try:
            m15 = load_yfinance(symbol=symbol, interval=interval, period=period)
        except Exception as e:
            print(f"[WARN] โหลด {interval} ไม่สำเร็จ ({e}) — ลอง interval=1h")
            m15 = load_yfinance(symbol=symbol, interval="1h", period="730d")
        h1 = resample_ohlcv(m15, "1h")
        if len(h1) < 30:
            h1 = m15.copy()
        label = f"yfinance:{symbol}:{interval}:{period}"
        return m15, h1, label
    raise ValueError(f"source ไม่รองรับ: {source} (ใช้ synthetic | yfinance | csv)")
