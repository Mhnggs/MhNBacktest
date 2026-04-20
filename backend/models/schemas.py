"""Pydantic request/response schemas for the ICT Silver Bullet API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


ALLOWED_STOP_TYPES = {"Beyond sweep", "Beyond FVG", "Fixed pips"}
ALLOWED_FVG_ENTRY_TYPES = {"50% midpoint", "FVG touch", "FVG close"}
ALLOWED_HTF_NEUTRAL = {"Skip trade", "Allow both"}


class StrategyParamsSchema(BaseModel):
    """ICT Silver Bullet strategy parameters."""

    # Instrument / sizing
    pip_size: float = Field(0.0001, gt=0.0)
    starting_capital: float = Field(10_000.0, gt=0.0)
    risk_per_trade_pct: float = Field(1.0, gt=0.0, le=100.0)

    # Kill zones (NY-time windows)
    enable_london_sb: bool = True
    enable_ny_sb: bool = True
    enable_ny_pm_sb: bool = False

    # Liquidity detection
    swing_lookback: int = Field(5, ge=3, le=10)
    equal_level_tolerance_pips: float = Field(3.0, ge=0.0, le=25.0)
    min_sweep_pips: float = Field(3.0, ge=0.5, le=30.0)
    sweep_confirmation_candles: int = Field(3, ge=1, le=10)

    # Displacement
    displacement_body_pips: float = Field(8.0, ge=2.0, le=60.0)
    displacement_close_pct: float = Field(0.70, ge=0.5, le=1.0)

    # FVG
    min_fvg_size_pips: float = Field(3.0, ge=0.5, le=30.0)
    fvg_max_age_candles: int = Field(20, ge=3, le=100)
    fvg_entry_type: str = Field("50% midpoint")

    # MSS
    require_mss: bool = True

    # Order block
    require_ob_confluence: bool = False

    # HTF bias
    require_htf_alignment: bool = True
    htf_neutral_action: str = Field("Skip trade")

    # Risk / exits
    stop_type: str = Field("Beyond sweep")
    stop_buffer_pips: float = Field(3.0, ge=0.0, le=30.0)
    fixed_stop_pips: float = Field(10.0, ge=2.0, le=100.0)
    rr_ratio: float = Field(2.0, ge=0.5, le=10.0)
    use_partial_tp: bool = True
    max_trades_per_killzone: int = Field(1, ge=1, le=5)
    max_trades_per_day: int = Field(2, ge=1, le=10)
    close_at_killzone_end: bool = True

    # Confluence filter
    min_confluence_score: int = Field(5, ge=4, le=10)

    # Filters
    enable_news_filter: bool = True
    custom_skip_dates: list[str] = Field(default_factory=list)
    allowed_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    min_fvg_to_stop_ratio: float = Field(0.5, ge=0.1, le=2.0)
    spread_pips: float = Field(0.2, ge=0.0, le=5.0)

    # Circuit breakers
    enable_daily_circuit_breaker: bool = True
    daily_loss_limit_pct: float = Field(2.0, ge=0.0, le=100.0)
    enable_weekly_circuit_breaker: bool = True
    weekly_loss_limit_pct: float = Field(5.0, ge=0.0, le=100.0)


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
    kill_zone_breakdown: list[dict]
    sweep_type_breakdown: list[dict]
    fvg_size_breakdown: list[dict]
    confluence_breakdown: list[dict]
    htf_bias_breakdown: list[dict]
    entry_time_breakdown: list[dict]
    direction_breakdown: list[dict]
    mss_breakdown: list[dict]
    candles: list[dict]
    diagnostics: dict
