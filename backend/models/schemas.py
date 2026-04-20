"""Pydantic request/response schemas for the API layer."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


ENTRY_TYPES = {"retest_only", "midpoint_only", "retest_then_midpoint"}

ALLOWED_CONFIRMATION_PATTERNS = {
    "engulfing", "marubozu", "hammer_star", "inside_bar", "piercing_cloud", "doji",
}


class StrategyParamsSchema(BaseModel):
    """DR / IDR breakout-retest strategy parameters."""

    # Instrument
    pip_size: float = Field(0.0001, gt=0.0)

    # Sizing / risk
    starting_capital: float = Field(10_000.0, gt=0.0)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=100.0)

    # DR window
    dr_start_time: str = "09:30"
    dr_end_time: str = "10:30"
    dr_timezone: str = "America/New_York"
    min_dr_range_pips: float = Field(15.0, ge=0.0, le=500.0)
    max_dr_range_pips: float = Field(70.0, gt=0.0, le=1000.0)

    # Entry
    entry_type: str = Field("retest_then_midpoint")
    retest_tolerance_pips: float = Field(5.0, ge=0.0, le=100.0)
    require_confirmation_candle: bool = True
    confirmation_patterns: list[str] = Field(
        default_factory=lambda: ["marubozu", "engulfing"],
    )

    # Time limits
    retest_window_minutes: int = Field(90, ge=1, le=600)
    last_entry_time: str = "13:00"

    # Risk / exits
    stop_type: str = Field("dr_range")  # "dr_range" | "buffer_only"
    stop_buffer_pips: float = Field(3.0, ge=0.0, le=100.0)
    use_partial_tp: bool = True
    partial_tp_1_mult: float = Field(0.5, gt=0.0, le=5.0)
    partial_tp_2_mult: float = Field(1.0, gt=0.0, le=5.0)
    partial_tp_pct: float = Field(50.0, gt=0.0, lt=100.0)
    move_be_after_t1: bool = True
    max_trades_per_day: int = Field(1, ge=1, le=10)
    max_profit_r: float = Field(2.5, ge=0.0, le=20.0)

    # Circuit breakers
    enable_daily_circuit_breaker: bool = True
    daily_loss_limit_pct: float = Field(2.0, ge=0.0, le=100.0)
    enable_weekly_circuit_breaker: bool = True
    weekly_loss_limit_pct: float = Field(5.0, ge=0.0, le=100.0)

    # News filter
    enable_news_filter: bool = True
    custom_skip_dates: list[str] = Field(default_factory=list)

    # Day filter (0 = Mon … 4 = Fri)
    allowed_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])


class TwelveDataRequest(BaseModel):
    symbol: str
    interval: str = "5min"
    start_date: str
    end_date: str
    api_key: str
    use_cache: bool = True


class BacktestRequest(BaseModel):
    session_id: str
    params: StrategyParamsSchema
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class WalkForwardRequest(BacktestRequest):
    train_pct: float = Field(0.7, ge=0.1, le=0.9)


class OptimizeRequest(BacktestRequest):
    x_param: str
    y_param: str
    x_values: list[float]
    y_values: list[float]
    metric: str = Field(
        "sharpe_ratio",
        description="Stat name to display in the heatmap",
    )


class SweepAxis(BaseModel):
    key: str
    values: list[float]


class AutoRobustRequest(BacktestRequest):
    sweeps: list[SweepAxis]
    train_pct: float = Field(0.7, ge=0.1, le=0.9)
    top_k: int = Field(10, ge=1, le=50)
    primary_metric: str = "sharpe_ratio"
    min_test_trades: int = Field(5, ge=0, le=1000)


class UploadResponse(BaseModel):
    session_id: str
    rows_loaded: int
    date_range: dict
    sample: list[dict]


class BacktestResponse(BaseModel):
    trades: list[dict]
    equity_curve: list[dict]
    stats: dict
    monthly_breakdown: list[dict]
    dow_breakdown: list[dict]
    hourly_breakdown: list[dict]
    candles: list[dict]
