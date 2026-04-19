"""Backtest execution endpoints."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..models.schemas import BacktestRequest, WalkForwardRequest
from ..services.performance import (
    compute_stats,
    dow_breakdown,
    hourly_breakdown,
    monthly_breakdown,
)
from ..services.store import get_dataset
from ..services.strategy import StrategyParams, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


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

    candles = (
        df.assign(datetime=lambda d: d["datetime"].astype(str))
        .to_dict("records")
    )

    return {
        **segment,
        "session_markers": _session_markers(params),
        "candles": candles,
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
