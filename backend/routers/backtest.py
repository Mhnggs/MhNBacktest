"""Backtest execution endpoints."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..models.schemas import BacktestRequest
from ..services.performance import (
    compute_stats,
    dow_breakdown,
    hourly_breakdown,
    monthly_breakdown,
)
from ..services.store import get_dataset
from ..services.strategy import StrategyParams, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/run")
def run(req: BacktestRequest):
    session = get_dataset(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found. Upload data or fetch first.")

    df = session["df"].copy()
    if req.start_date:
        df = df[df["datetime"] >= pd.to_datetime(req.start_date)]
    if req.end_date:
        df = df[df["datetime"] <= pd.to_datetime(req.end_date)]
    df = df.reset_index(drop=True)

    if df.empty:
        raise HTTPException(400, "Filtered dataset is empty")

    params = StrategyParams(**req.params.model_dump())
    try:
        result = run_backtest(df, params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Backtest failed: {exc}") from exc

    stats = compute_stats(result["trades"], result["equity_curve"], params.starting_capital)

    candles = (
        df.assign(datetime=lambda d: d["datetime"].astype(str))
        .to_dict("records")
    )

    return {
        "trades": result["trades"],
        "equity_curve": result["equity_curve"],
        "stats": stats,
        "monthly_breakdown": monthly_breakdown(result["trades"]),
        "dow_breakdown": dow_breakdown(result["trades"]),
        "hourly_breakdown": hourly_breakdown(result["trades"]),
        "candles": candles,
    }
