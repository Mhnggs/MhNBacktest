"""Pydantic request/response schemas for the API layer."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


ALLOWED_PATTERN_KEYS = {
    "engulfing", "hammer_star", "piercing_cloud", "marubozu", "doji",
}


class StrategyParamsSchema(BaseModel):
    # Core strategy
    ema_period: int = Field(9, ge=2, le=200)
    ema_secondary: int = Field(20, ge=2, le=400)
    allowed_patterns: list[str] = Field(
        default_factory=lambda: ["engulfing", "hammer_star", "marubozu"],
    )
    stop_loss_pips: float = Field(20.0, gt=0.0, le=1000.0)
    risk_reward: float = Field(2.0, ge=0.5, le=10.0)
    pip_size: float = Field(0.0001, gt=0.0)

    # Sizing / risk
    starting_capital: float = Field(10_000.0, gt=0.0)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=100.0)
    max_trades_per_day: int = Field(3, ge=1, le=50)

    # Partial take-profit: close `partial_tp_pct`% of the position at
    # `partial_tp_r` × risk and move stop to breakeven for the runner.
    use_partial_tp: bool = False
    partial_tp_r: float = Field(1.5, gt=0.0, le=10.0)
    partial_tp_pct: float = Field(50.0, gt=0.0, lt=100.0)

    # Standalone breakeven: move stop to entry price once price reaches
    # `breakeven_r` × risk in favour, without closing anything.
    use_breakeven: bool = False
    breakeven_r: float = Field(1.5, gt=0.0, le=10.0)

    # Session (NY — supports a morning + afternoon window)
    use_ny: bool = True
    session_start: str = "09:45"
    session_end: str = "11:30"
    session_2_start: str = "13:30"
    session_2_end: str = "15:00"
    use_session_2: bool = True
    timezone: str = "America/New_York"

    # London session
    use_london: bool = False
    london_start: str = "08:00"
    london_end: str = "11:00"
    london_tz: str = "Europe/London"

    # Asian session (Tokyo by default)
    use_asian: bool = False
    asian_start: str = "09:00"
    asian_end: str = "12:00"
    asian_tz: str = "Asia/Tokyo"

    # Day filter
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
    x_values: list[float]
    y_param: str
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
