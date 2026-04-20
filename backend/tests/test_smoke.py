"""Smoke tests for the ICT Silver Bullet backtester.

Each test builds a small synthetic candle series in New York time, runs
the indicator pipeline and the backtest runner, and asserts that the
output shape is correct. These aren't exhaustive strategy validations —
they guard against import/serialisation/schema regressions.
"""

from __future__ import annotations

import pandas as pd

from backend.services.indicators import build_indicator_frame
from backend.services.performance import compute_stats, kill_zone_breakdown
from backend.services.strategy import StrategyParams, run_backtest


def _synthetic_frame(days: int = 5) -> pd.DataFrame:
    """Several weekdays of flat 5m candles in NY time → UTC."""
    rng_ny = pd.date_range("2024-02-05 00:00", periods=12 * 24 * days, freq="5min",
                           tz="America/New_York")
    df = pd.DataFrame({
        "datetime": rng_ny.tz_convert("UTC"),
        "open": 1.1000, "high": 1.1002, "low": 1.0998, "close": 1.1000,
        "volume": 1000.0,
    })
    return df.reset_index(drop=True)


def test_indicators_attach_silver_bullet_columns():
    df = _synthetic_frame()
    out = build_indicator_frame(df)
    for col in [
        "is_swing_high", "is_swing_low",
        "prev_day_high", "prev_day_low",
        "is_bull_disp", "is_bear_disp",
        "fvg_bull_top", "fvg_bear_top",
        "kill_zone", "htf_bias",
    ]:
        assert col in out.columns, f"missing column {col}"
    # Kill zones are flagged in the right NY hours.
    ny = out["datetime"].dt.tz_convert("America/New_York")
    ny_sb_mask = (ny.dt.hour == 10)
    assert out.loc[ny_sb_mask, "kill_zone"].eq("ny").all()


def test_run_backtest_returns_structure():
    df = _synthetic_frame()
    params = StrategyParams(
        enable_news_filter=False,
        require_mss=False,
        require_htf_alignment=False,
        min_confluence_score=4,
    )
    out = run_backtest(df, params)
    assert "trades" in out and "equity_curve" in out and "diagnostics" in out
    assert "setup_funnel" in out["diagnostics"]
    stats = compute_stats(out["trades"], out["equity_curve"], params.starting_capital)
    assert "total_trades" in stats
    assert stats["starting_capital"] == params.starting_capital
    # Breakdowns don't crash on empty trade lists.
    assert isinstance(kill_zone_breakdown(out["trades"]), list)


if __name__ == "__main__":
    test_indicators_attach_silver_bullet_columns()
    test_run_backtest_returns_structure()
    print("smoke ok")
