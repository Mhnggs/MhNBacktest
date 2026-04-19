"""Pydantic request/response schemas for the API layer."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StrategyParamsSchema(BaseModel):
    ema_period: int = Field(9, ge=2, le=200)
    ema_secondary: int = Field(20, ge=2, le=400)
    volume_multiplier: float = Field(1.2, ge=0.0, le=10.0)
    risk_reward: float = Field(2.0, ge=0.5, le=10.0)
    partial_rr: float = Field(1.5, ge=0.5, le=10.0)
    use_partial_tp: bool = True
    stop_buffer_ticks: int = Field(3, ge=0, le=200)
    tick_size: float = Field(0.0001, gt=0.0)
    max_trades_per_day: int = Field(3, ge=1, le=50)
    session_start: str = "09:45"
    session_end: str = "11:30"
    session_2_start: str = "13:30"
    session_2_end: str = "15:00"
    use_session_2: bool = True
    timezone: str = "America/New_York"
    vwap_max_distance_pct: float = Field(2.0, ge=0.0, le=100.0)
    chop_filter_crossings: int = Field(3, ge=0, le=20)
    require_volume: bool = True
    require_pattern: bool = True
    min_ema_slope: float = Field(0.0001, ge=0.0)
    ema_touch_pct: float = Field(0.001, ge=0.0)
    starting_capital: float = Field(10000.0, gt=0.0)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=100.0)
    use_adx_filter: bool = True
    adx_period: int = Field(14, ge=5, le=50)
    adx_threshold: float = Field(25.0, ge=0.0, le=100.0)
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
