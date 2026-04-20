"""Smoke test: synthetic DR day → run_backtest → compute_stats."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services.indicators import build_indicator_frame
from backend.services.performance import compute_stats
from backend.services.strategy import StrategyParams, run_backtest


def _synthetic_dr_day(day: str = "2024-02-06") -> pd.DataFrame:
    """One NY-day with a clean bull breakout of the 09:30-10:30 DR."""
    rng = pd.date_range(f"{day} 00:00", f"{day} 23:55", freq="5min", tz="America/New_York")
    rng_utc = rng.tz_convert("UTC")
    rows = []
    for ts in rng:
        hm = ts.hour + ts.minute / 60.0
        if 9.5 <= hm < 10.5:
            o, c = 1.1000, 1.1005
            h, l = 1.1010, 1.0995
        elif 10.5 <= hm < 10.6:
            o, c = 1.1005, 1.1020  # breakout
            h, l = 1.1022, 1.1003
        elif 10.6 <= hm < 10.7:
            o, c = 1.1020, 1.1013  # retest toward dr_high
            h, l = 1.1021, 1.1011
        elif 10.7 <= hm < 10.8:
            o, c = 1.1013, 1.1050  # confirmation + move up
            h, l = 1.1055, 1.1012
        else:
            o = c = 1.1050
            h = l = 1.1050
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": 1000.0})
    df = pd.DataFrame(rows)
    df.insert(0, "datetime", rng_utc)
    return df


def test_indicators_attach_dr_columns():
    df = _synthetic_dr_day()
    out = build_indicator_frame(df)
    for col in ["dr_high", "dr_low", "dr_range", "dr_midpoint", "post_dr"]:
        assert col in out.columns
    post = out[out["post_dr"]]
    assert not post.empty
    # dr_high must be >= dr_low on post-DR bars
    assert (post["dr_high"] >= post["dr_low"]).all()


def test_run_backtest_returns_structure():
    df = _synthetic_dr_day()
    params = StrategyParams(
        min_dr_range_pips=5.0,
        max_dr_range_pips=500.0,
        require_confirmation_candle=False,
        enable_news_filter=False,
    )
    out = run_backtest(df, params)
    assert "trades" in out and "equity_curve" in out and "diagnostics" in out
    stats = compute_stats(out["trades"], out["equity_curve"], params.starting_capital)
    assert "total_trades" in stats
    assert stats["starting_capital"] == params.starting_capital


if __name__ == "__main__":
    test_indicators_attach_dr_columns()
    test_run_backtest_returns_structure()
    print("smoke ok")
