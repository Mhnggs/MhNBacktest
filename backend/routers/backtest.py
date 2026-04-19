"""Backtest execution endpoints."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..models.schemas import BacktestRequest, OptimizeRequest, WalkForwardRequest
from ..services.performance import (
    compute_stats,
    dow_breakdown,
    hourly_breakdown,
    monthly_breakdown,
)
from ..services.store import get_dataset
from ..services.strategy import StrategyParams, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def _candles_with_indicators(df: pd.DataFrame, ema_period: int, ema_secondary: int,
                             adx_period: int) -> list[dict]:
    """Attach indicators and serialize OHLCV rows for the candle chart.

    Indicator columns contain NaNs during their warmup period. Starlette's
    JSONResponse rejects non-finite floats, so we must convert them to
    nulls before returning. Using ``to_json`` then ``json.loads`` is the
    simplest path that handles NaN/±Inf correctly across dtypes.
    """
    from ..services.indicators import build_indicator_frame

    with_ind = build_indicator_frame(
        df,
        ema_period=ema_period,
        ema_secondary=ema_secondary,
        adx_period=adx_period,
    )
    with_ind = with_ind.replace([np.inf, -np.inf], np.nan)
    serialized = (
        with_ind.assign(datetime=lambda d: d["datetime"].astype(str))
        .to_json(orient="records", date_format="iso")
    )
    return json.loads(serialized)


def _load_filtered_df(req: BacktestRequest) -> pd.DataFrame:
    session = get_dataset(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found. Upload data or fetch first.")
    df = session["df"].copy()
    tz_aware = isinstance(df["datetime"].dtype, pd.DatetimeTZDtype)
    if req.start_date:
        start_ts = pd.to_datetime(req.start_date, utc=tz_aware)
        df = df[df["datetime"] >= start_ts]
    if req.end_date:
        end_ts = pd.to_datetime(req.end_date, utc=tz_aware)
        df = df[df["datetime"] <= end_ts]
    df = df.reset_index(drop=True)
    if df.empty:
        raise HTTPException(400, "Filtered dataset is empty")
    return df


def _session_markers(params: StrategyParams) -> list[dict]:
    def _to_hour(s: str) -> float:
        h, m = s.split(":")
        return int(h) + int(m) / 60.0

    markers = [
        {"label": "S1 start", "hour": _to_hour(params.session_start)},
        {"label": "S1 end", "hour": _to_hour(params.session_end)},
    ]
    if params.use_session_2:
        markers += [
            {"label": "S2 start", "hour": _to_hour(params.session_2_start)},
            {"label": "S2 end", "hour": _to_hour(params.session_2_end)},
        ]
    return markers


def _run_segment(df: pd.DataFrame, params: StrategyParams) -> dict:
    try:
        result = run_backtest(df, params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Backtest failed: {exc}") from exc
    stats = compute_stats(result["trades"], result["equity_curve"], params.starting_capital)
    return {
        "trades": result["trades"],
        "equity_curve": result["equity_curve"],
        "stats": stats,
        "monthly_breakdown": monthly_breakdown(result["trades"]),
        "dow_breakdown": dow_breakdown(result["trades"]),
        "hourly_breakdown": hourly_breakdown(result["trades"], params.timezone),
        "diagnostics": result.get("diagnostics", {}),
    }


@router.post("/run")
def run(req: BacktestRequest):
    df = _load_filtered_df(req)
    params = StrategyParams(**req.params.model_dump())

    segment = _run_segment(df, params)

    candles = _candles_with_indicators(
        df, params.ema_period, params.ema_secondary, params.adx_period,
    )

    return {
        **segment,
        "session_markers": _session_markers(params),
        "candles": candles,
    }


@router.post("/candles")
def candles(req: BacktestRequest):
    """Return candles with indicator overlays for the chart, without running the strategy.

    Useful when a backtest produces zero trades and you still want to inspect
    VWAP / EMA / price action for the filtered range.
    """
    df = _load_filtered_df(req)
    params = StrategyParams(**req.params.model_dump())
    return {
        "candles": _candles_with_indicators(
            df, params.ema_period, params.ema_secondary, params.adx_period,
        ),
        "session_markers": _session_markers(params),
    }


def _consistency_score(train_stats: dict, test_stats: dict) -> dict:
    test_sharpe = float(test_stats.get("sharpe_ratio") or 0.0)
    test_pf = float(test_stats.get("profit_factor") or 0.0)
    test_trades = int(test_stats.get("total_trades") or 0)

    if test_trades == 0:
        label, tier, note = "NO TEST TRADES", "unknown", "Test period produced no trades."
    elif test_sharpe < 0:
        label, tier, note = (
            "CURVE FITTED",
            "bad",
            "Test-period Sharpe is negative — do not trade this live.",
        )
    elif test_pf < 1.0:
        label, tier, note = (
            "MARGINAL",
            "warn",
            "Positive Sharpe but profit factor < 1.0 on unseen data.",
        )
    else:
        label, tier, note = (
            "ROBUST",
            "good",
            "Positive Sharpe and profit factor > 1.0 on unseen data.",
        )

    degradation = None
    train_sharpe = float(train_stats.get("sharpe_ratio") or 0.0)
    if train_sharpe != 0:
        degradation = (test_sharpe - train_sharpe) / abs(train_sharpe) * 100.0

    return {
        "label": label,
        "tier": tier,
        "note": note,
        "sharpe_degradation_pct": degradation,
        "train_sharpe": train_sharpe,
        "test_sharpe": test_sharpe,
        "train_profit_factor": float(train_stats.get("profit_factor") or 0.0),
        "test_profit_factor": test_pf,
    }


OPTIMIZE_ALLOWED_PARAMS = {
    "ema_period": {"type": int, "label": "EMA Fast", "min": 3, "max": 100},
    "ema_secondary": {"type": int, "label": "EMA Slow", "min": 3, "max": 200},
    "volume_multiplier": {"type": float, "label": "Volume ×", "min": 0.5, "max": 5.0},
    "risk_reward": {"type": float, "label": "Risk/Reward", "min": 0.5, "max": 8.0},
    "adx_threshold": {"type": float, "label": "ADX Threshold", "min": 10.0, "max": 60.0},
    "adx_period": {"type": int, "label": "ADX Period", "min": 5, "max": 50},
    "vwap_max_distance_pct": {"type": float, "label": "VWAP Distance %", "min": 0.1, "max": 10.0},
    "chop_filter_crossings": {"type": int, "label": "Chop Crossings", "min": 0, "max": 20},
    "stop_buffer_ticks": {"type": int, "label": "Stop Buffer Ticks", "min": 0, "max": 100},
    "max_trades_per_day": {"type": int, "label": "Max Trades/Day", "min": 1, "max": 50},
}

OPTIMIZE_METRICS = {
    "sharpe_ratio", "total_return_pct", "profit_factor",
    "total_trades", "win_rate", "max_drawdown_pct",
}

OPTIMIZE_MAX_CELLS = 400


def _coerce(name: str, value: float):
    spec = OPTIMIZE_ALLOWED_PARAMS[name]
    lo, hi = spec["min"], spec["max"]
    value = max(lo, min(hi, value))
    return spec["type"](round(value)) if spec["type"] is int else float(value)


@router.get("/optimize/options")
def optimize_options():
    return {
        "params": [
            {"key": k, "label": v["label"], "min": v["min"], "max": v["max"],
             "integer": v["type"] is int}
            for k, v in OPTIMIZE_ALLOWED_PARAMS.items()
        ],
        "metrics": sorted(OPTIMIZE_METRICS),
        "max_cells": OPTIMIZE_MAX_CELLS,
    }


@router.post("/optimize")
def optimize(req: OptimizeRequest):
    if req.x_param not in OPTIMIZE_ALLOWED_PARAMS or req.y_param not in OPTIMIZE_ALLOWED_PARAMS:
        raise HTTPException(400, f"Param must be one of {sorted(OPTIMIZE_ALLOWED_PARAMS)}")
    if req.x_param == req.y_param:
        raise HTTPException(400, "x_param and y_param must differ")
    if req.metric not in OPTIMIZE_METRICS:
        raise HTTPException(400, f"metric must be one of {sorted(OPTIMIZE_METRICS)}")
    if not req.x_values or not req.y_values:
        raise HTTPException(400, "x_values and y_values cannot be empty")
    total_cells = len(req.x_values) * len(req.y_values)
    if total_cells > OPTIMIZE_MAX_CELLS:
        raise HTTPException(
            400,
            f"{total_cells} cells exceeds cap of {OPTIMIZE_MAX_CELLS}. Widen the step.",
        )

    df = _load_filtered_df(req)
    base_params = req.params.model_dump()

    x_vals = [_coerce(req.x_param, v) for v in req.x_values]
    y_vals = [_coerce(req.y_param, v) for v in req.y_values]

    grid: list[list[dict]] = []
    best = None
    for yv in y_vals:
        row: list[dict] = []
        for xv in x_vals:
            overrides = {**base_params, req.x_param: xv, req.y_param: yv}
            params = StrategyParams(**overrides)
            try:
                run_result = run_backtest(df, params)
                stats = compute_stats(
                    run_result["trades"], run_result["equity_curve"], params.starting_capital,
                )
                metric_value = float(stats.get(req.metric) or 0.0)
                cell = {
                    "x": xv,
                    "y": yv,
                    "metric_value": metric_value,
                    "total_trades": int(stats.get("total_trades") or 0),
                    "win_rate": float(stats.get("win_rate") or 0.0),
                    "profit_factor": float(stats.get("profit_factor") or 0.0),
                    "sharpe_ratio": float(stats.get("sharpe_ratio") or 0.0),
                    "total_return_pct": float(stats.get("total_return_pct") or 0.0),
                    "max_drawdown_pct": float(stats.get("max_drawdown_pct") or 0.0),
                }
            except Exception as exc:  # noqa: BLE001
                cell = {
                    "x": xv, "y": yv, "metric_value": 0.0, "error": str(exc),
                    "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                    "sharpe_ratio": 0.0, "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
                }
            row.append(cell)
            if best is None or cell["metric_value"] > best["metric_value"]:
                best = cell
        grid.append(row)

    return {
        "x_param": req.x_param,
        "y_param": req.y_param,
        "metric": req.metric,
        "x_values": x_vals,
        "y_values": y_vals,
        "grid": grid,
        "best": best,
        "cells_run": total_cells,
    }


@router.post("/walkforward")
def walkforward(req: WalkForwardRequest):
    df = _load_filtered_df(req)
    params = StrategyParams(**req.params.model_dump())

    n = len(df)
    split_idx = max(1, min(n - 1, int(n * req.train_pct)))
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    test_df = df.iloc[split_idx:].reset_index(drop=True)

    if train_df.empty or test_df.empty:
        raise HTTPException(400, "Not enough data to split into train/test")

    split_datetime = str(df.iloc[split_idx]["datetime"])

    train_result = _run_segment(train_df, params)
    test_result = _run_segment(test_df, params)

    consistency = _consistency_score(train_result["stats"], test_result["stats"])

    return {
        "train": train_result,
        "test": test_result,
        "split_datetime": split_datetime,
        "train_pct": req.train_pct,
        "train_bars": int(len(train_df)),
        "test_bars": int(len(test_df)),
        "consistency": consistency,
        "session_markers": _session_markers(params),
    }
