"""Smoke test: synthetic data → run_backtest → compute_stats."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.indicators import build_indicator_frame
from backend.services.performance import compute_stats
from backend.services.strategy import StrategyParams, run_backtest


def _synthetic_data(days: int = 5, freq: str = "5min") -> pd.DataFrame:
    rng = pd.date_range("2024-01-02 09:30", periods=days * 78, freq=freq, tz="America/New_York")
    rng_utc = rng.tz_convert("UTC")
    rs = np.random.default_rng(42)
    base = 100.0
    closes = base + np.cumsum(rs.normal(0, 0.05, len(rng)))
    highs = closes + rs.uniform(0.05, 0.2, len(rng))
    lows = closes - rs.uniform(0.05, 0.2, len(rng))
    opens = closes + rs.normal(0, 0.05, len(rng))
    vol = rs.uniform(500, 5000, len(rng))
    return pd.DataFrame({
        "datetime": rng_utc,
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": vol,
    })


def test_indicators_attach_columns():
    df = _synthetic_data()
    out = build_indicator_frame(df)
    for col in ["vwap", "ema_fast", "ema_slow", "ema_fast_slope", "vol_ratio", "vwap_crossings"]:
        assert col in out.columns
    # VWAP must reset daily — first bar of each new session has VWAP equal to its typical price
    out["session"] = out["datetime"].dt.date
    first = out.groupby("session").first()
    typical = (first["high"] + first["low"] + first["close"]) / 3
    assert np.allclose(first["vwap"], typical, atol=1e-6)


def test_run_backtest_returns_structure():
    df = _synthetic_data()
    params = StrategyParams(
        require_volume=False, require_pattern=False, tick_size=0.01,
    )
    out = run_backtest(df, params)
    assert "trades" in out and "equity_curve" in out
    stats = compute_stats(out["trades"], out["equity_curve"], params.starting_capital)
    assert "total_trades" in stats
    assert stats["starting_capital"] == params.starting_capital


if __name__ == "__main__":
    test_indicators_attach_columns()
    test_run_backtest_returns_structure()
    print("smoke ok")
