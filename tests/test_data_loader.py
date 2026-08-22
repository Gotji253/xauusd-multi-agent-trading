"""Tests for data loader."""

from __future__ import annotations

from pathlib import Path
import pytest

from core.data_loader import (
    generate_synthetic_xauusd,
    load_csv,
    load_xauusd_data,
    resample_ohlcv,
)


def test_synthetic():
    m15, h1 = generate_synthetic_xauusd(n_bars=500, seed=1)
    assert len(m15) == 500
    assert len(h1) > 0
    assert list(m15.columns) == ["open", "high", "low", "close"]


def test_load_csv(tmp_path: Path):
    m15, _ = generate_synthetic_xauusd(n_bars=100, seed=2)
    csv_path = tmp_path / "sample.csv"
    out = m15.reset_index().rename(columns={"index": "time"})
    out.to_csv(csv_path, index=False)
    loaded = load_csv(csv_path)
    assert len(loaded) == 100
    assert "close" in loaded.columns


def test_load_xauusd_synthetic():
    m15, h1, label = load_xauusd_data(source="synthetic", n_bars=300)
    assert "synthetic" in label
    assert len(m15) == 300


def test_resample():
    m15, _ = generate_synthetic_xauusd(n_bars=200, seed=3)
    h1 = resample_ohlcv(m15, "1h")
    assert len(h1) > 0
