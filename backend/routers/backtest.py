"""Backtest execution endpoints for the ICT Silver Bullet strategy."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from ..models.schemas import (
    AutoRobustRequest,
    BacktestRequest,
    OptimizeRequest,
    WalkForwardRequest,
)
from ..services.performance import (
    compute_stats,
    confluence_breakdown,
    direction_breakdown,
    dow_breakdown,
    entry_time_breakdown,
    fvg_size_breakdown,
    hourly_breakdown,
    htf_bias_breakdown,
    kill_zone_breakdown,
    monthly_breakdown,
    mss_breakdown,
    sweep_type_breakdown,
)
from ..services.store import get_dataset
from ..services.strategy import StrategyParams, run_backtest

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


def _candles_with_indicators(df: pd.DataFrame, params: "StrategyParams") -> list[dict]:
    """Attach Silver Bullet indicator columns and serialize rows for the chart."""
    from ..services.indicators import build_indicator_frame

    work = df.copy()
    if not isinstance(work["datetime"].dtype, pd.DatetimeTZDtype):
        source_tz = df.attrs.get("source_tz", "UTC")
        work["datetime"] = pd.to_datetime(work["datetime"]).dt.tz_localize(
            source_tz, nonexistent="shift_forward", ambiguous="NaT",
        ).dt.tz_convert("UTC")
        work = work.dropna(subset=["datetime"]).reset_index(drop=True)
    with_ind = build_indicator_frame(
        work,
        pip_size=params.pip_size,
        swing_lookback=params.swing_lookback,
        displacement_body_pips=params.displacement_body_pips,
        displacement_close_pct=params.displacement_close_pct,
        min_fvg_size_pips=params.min_fvg_size_pips,
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


def _session_markers() -> list[dict]:
    """Kill-zone boundaries for the hourly breakdown chart (NY time)."""
    return [
        {"label": "London SB", "hour": 3.0},
        {"label": "London SB end", "hour": 4.0},
        {"label": "NY SB", "hour": 10.0},
        {"label": "NY SB end", "hour": 11.0},
        {"label": "NY PM SB", "hour": 14.0},
        {"label": "NY PM SB end", "hour": 15.0},
    ]


def _run_segment(df: pd.DataFrame, params: StrategyParams) -> dict:
    try:
        result = run_backtest(df, params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Backtest failed: {exc}") from exc
    stats = compute_stats(result["trades"], result["equity_curve"], params.starting_capital)
    trades = result["trades"]
    return {
        "trades": trades,
        "equity_curve": result["equity_curve"],
        "stats": stats,
        "monthly_breakdown": monthly_breakdown(trades),
        "dow_breakdown": dow_breakdown(trades),
        "hourly_breakdown": hourly_breakdown(trades, "America/New_York"),
        "kill_zone_breakdown": kill_zone_breakdown(trades),
        "sweep_type_breakdown": sweep_type_breakdown(trades),
        "fvg_size_breakdown": fvg_size_breakdown(trades),
        "confluence_breakdown": confluence_breakdown(trades),
        "htf_bias_breakdown": htf_bias_breakdown(trades),
        "entry_time_breakdown": entry_time_breakdown(trades),
        "direction_breakdown": direction_breakdown(trades),
        "mss_breakdown": mss_breakdown(trades),
        "diagnostics": result.get("diagnostics", {}),
    }


@router.post("/run")
def run(req: BacktestRequest):
    df = _load_filtered_df(req)
    params = StrategyParams(**req.params.model_dump())

    segment = _run_segment(df, params)
    candles = _candles_with_indicators(df, params)

    return {
        **segment,
        "session_markers": _session_markers(),
        "candles": candles,
    }


@router.post("/candles")
def candles(req: BacktestRequest):
    df = _load_filtered_df(req)
    params = StrategyParams(**req.params.model_dump())
    return {
        "candles": _candles_with_indicators(df, params),
        "session_markers": _session_markers(),
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


# ------------- Optimizer parameter surface -------------

OPTIMIZE_ALLOWED_PARAMS = {
    "swing_lookback": {"type": int, "label": "Swing Lookback", "min": 3.0, "max": 10.0},
    "min_sweep_pips": {"type": float, "label": "Min Sweep (pips)", "min": 0.5, "max": 20.0},
    "displacement_body_pips": {"type": float, "label": "Displacement Body (pips)", "min": 3.0, "max": 30.0},
    "min_fvg_size_pips": {"type": float, "label": "Min FVG Size (pips)", "min": 1.0, "max": 20.0},
    "fvg_max_age_candles": {"type": int, "label": "FVG Max Age (bars)", "min": 3.0, "max": 60.0},
    "rr_ratio": {"type": float, "label": "R:R Ratio", "min": 0.5, "max": 5.0},
    "stop_buffer_pips": {"type": float, "label": "Stop Buffer (pips)", "min": 0.0, "max": 15.0},
    "equal_level_tolerance_pips": {"type": float, "label": "Equal Level Tolerance (pips)", "min": 0.5, "max": 15.0},
    "min_confluence_score": {"type": int, "label": "Min Confluence Score", "min": 4.0, "max": 10.0},
    "risk_per_trade_pct": {"type": float, "label": "Risk/Trade %", "min": 0.1, "max": 10.0},
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
        "session_markers": _session_markers(),
    }


AUTO_ROBUST_MAX_COMBOS = 500


def _run_stats_only(df: pd.DataFrame, params: StrategyParams) -> dict:
    result = run_backtest(df, params)
    stats = compute_stats(
        result["trades"], result["equity_curve"], params.starting_capital,
    )
    return stats


def _tier_rank(tier: str) -> int:
    return {"good": 0, "warn": 1, "unknown": 2, "bad": 3}.get(tier, 4)


@router.post("/auto_robust")
def auto_robust(req: AutoRobustRequest):
    """Sweep → rank by primary metric → walk-forward the top-K → return
    configurations that survived as ROBUST / MARGINAL."""
    if not req.sweeps:
        raise HTTPException(400, "At least one sweep axis is required")
    if len(req.sweeps) > 3:
        raise HTTPException(400, "Up to 3 sweep axes supported")
    keys = [s.key for s in req.sweeps]
    for k in keys:
        if k not in OPTIMIZE_ALLOWED_PARAMS:
            raise HTTPException(400, f"Param '{k}' not sweepable")
    if len(set(keys)) != len(keys):
        raise HTTPException(400, "Duplicate param keys in sweeps")
    if req.primary_metric not in OPTIMIZE_METRICS:
        raise HTTPException(400, f"primary_metric must be one of {sorted(OPTIMIZE_METRICS)}")

    coerced = [[_coerce(s.key, v) for v in s.values] for s in req.sweeps]
    total = 1
    for vs in coerced:
        if not vs:
            raise HTTPException(400, "Each sweep axis must have at least one value")
        total *= len(vs)
    if total > AUTO_ROBUST_MAX_COMBOS:
        raise HTTPException(
            400,
            f"{total} combinations exceeds cap of {AUTO_ROBUST_MAX_COMBOS}. Widen the step.",
        )

    df = _load_filtered_df(req)
    base_params = req.params.model_dump()

    from itertools import product

    candidates: list[dict] = []
    for combo in product(*coerced):
        overrides = dict(zip(keys, combo))
        params = StrategyParams(**{**base_params, **overrides})
        try:
            stats = _run_stats_only(df, params)
        except Exception as exc:  # noqa: BLE001
            candidates.append({
                "overrides": overrides,
                "error": str(exc),
                "metric_value": float("-inf"),
            })
            continue
        candidates.append({
            "overrides": overrides,
            "full_stats": {
                "total_trades": int(stats.get("total_trades") or 0),
                "win_rate": float(stats.get("win_rate") or 0.0),
                "profit_factor": float(stats.get("profit_factor") or 0.0),
                "sharpe_ratio": float(stats.get("sharpe_ratio") or 0.0),
                "total_return_pct": float(stats.get("total_return_pct") or 0.0),
                "max_drawdown_pct": float(stats.get("max_drawdown_pct") or 0.0),
            },
            "metric_value": float(stats.get(req.primary_metric) or 0.0),
        })

    scored = [c for c in candidates if "error" not in c]
    scored.sort(key=lambda c: c["metric_value"], reverse=True)
    top = scored[: req.top_k]

    n = len(df)
    split_idx = max(1, min(n - 1, int(n * req.train_pct)))
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    if train_df.empty or test_df.empty:
        raise HTTPException(400, "Not enough data to split into train/test")
    split_datetime = str(df.iloc[split_idx]["datetime"])

    validated: list[dict] = []
    for rank, cand in enumerate(top, start=1):
        params = StrategyParams(**{**base_params, **cand["overrides"]})
        try:
            train_stats = _run_stats_only(train_df, params)
            test_stats = _run_stats_only(test_df, params)
        except Exception as exc:  # noqa: BLE001
            validated.append({
                **cand,
                "rank": rank,
                "error": str(exc),
            })
            continue

        consistency = _consistency_score(train_stats, test_stats)
        robust_enough = (
            consistency["tier"] in ("good", "warn")
            and int(test_stats.get("total_trades") or 0) >= req.min_test_trades
        )

        validated.append({
            "rank": rank,
            "params": cand["overrides"],
            "full_stats": cand["full_stats"],
            "train_stats": {
                "total_trades": int(train_stats.get("total_trades") or 0),
                "win_rate": float(train_stats.get("win_rate") or 0.0),
                "profit_factor": float(train_stats.get("profit_factor") or 0.0),
                "sharpe_ratio": float(train_stats.get("sharpe_ratio") or 0.0),
                "total_return_pct": float(train_stats.get("total_return_pct") or 0.0),
                "max_drawdown_pct": float(train_stats.get("max_drawdown_pct") or 0.0),
            },
            "test_stats": {
                "total_trades": int(test_stats.get("total_trades") or 0),
                "win_rate": float(test_stats.get("win_rate") or 0.0),
                "profit_factor": float(test_stats.get("profit_factor") or 0.0),
                "sharpe_ratio": float(test_stats.get("sharpe_ratio") or 0.0),
                "total_return_pct": float(test_stats.get("total_return_pct") or 0.0),
                "max_drawdown_pct": float(test_stats.get("max_drawdown_pct") or 0.0),
            },
            "consistency": consistency,
            "robust_enough": robust_enough,
        })

    validated.sort(
        key=lambda r: (
            _tier_rank(r.get("consistency", {}).get("tier", "")),
            -float(r.get("test_stats", {}).get("sharpe_ratio") or 0.0),
        )
    )
    for i, r in enumerate(validated, start=1):
        r["rank"] = i

    tier_counts = {"good": 0, "warn": 0, "bad": 0, "unknown": 0}
    for r in validated:
        t = r.get("consistency", {}).get("tier", "unknown")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    return {
        "sweeps": [{"key": k, "values": v} for k, v in zip(keys, coerced)],
        "primary_metric": req.primary_metric,
        "train_pct": req.train_pct,
        "top_k": req.top_k,
        "min_test_trades": req.min_test_trades,
        "total_combos": total,
        "evaluated": len(scored),
        "split_datetime": split_datetime,
        "train_bars": int(len(train_df)),
        "test_bars": int(len(test_df)),
        "results": validated,
        "tier_counts": tier_counts,
        "max_combos": AUTO_ROBUST_MAX_COMBOS,
    }
