"""Performance metrics: Sharpe, drawdown, win rate, profit factor, breakdowns."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np
import pandas as pd


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) else 0.0


def compute_stats(trades: list[dict], equity_curve: list[dict], starting_capital: float) -> dict:
    if not trades:
        return _empty_stats(starting_capital, equity_curve)

    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["pnl"] = df["pnl"].astype(float)

    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] < 0]

    gross_profit = wins["pnl"].sum()
    gross_loss = -losses["pnl"].sum()
    total_pnl = df["pnl"].sum()
    final_equity = starting_capital + total_pnl

    win_streaks, loss_streaks = _streaks(df["pnl"].tolist())

    eq_df = pd.DataFrame(equity_curve)
    if not eq_df.empty:
        eq_df["datetime"] = pd.to_datetime(eq_df["datetime"])
        eq_df["equity"] = eq_df["equity"].astype(float)
        peak = eq_df["equity"].cummax()
        drawdown = (eq_df["equity"] - peak) / peak
        max_dd = float(drawdown.min()) if not drawdown.empty else 0.0
    else:
        max_dd = 0.0

    daily_returns = _daily_returns(equity_curve, starting_capital)
    sharpe = _sharpe(daily_returns)

    durations = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
    avg_duration_min = float(durations.mean()) if len(durations) else 0.0

    return {
        "total_trades": int(len(df)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": _safe_div(len(wins), len(df)) * 100,
        "avg_win": float(wins["pnl"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["pnl"].mean()) if len(losses) else 0.0,
        "profit_factor": _safe_div(gross_profit, gross_loss),
        "total_pnl": float(total_pnl),
        "total_return_pct": _safe_div(total_pnl, starting_capital) * 100,
        "max_drawdown_pct": max_dd * 100,
        "sharpe_ratio": sharpe,
        "best_trade": float(df["pnl"].max()),
        "worst_trade": float(df["pnl"].min()),
        "avg_trade_duration_min": avg_duration_min,
        "max_consecutive_wins": win_streaks,
        "max_consecutive_losses": loss_streaks,
        "starting_capital": float(starting_capital),
        "final_equity": float(final_equity),
    }


def _empty_stats(starting_capital: float, equity_curve: list[dict]) -> dict:
    return {
        "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0,
        "total_pnl": 0.0, "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
        "avg_trade_duration_min": 0.0, "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "starting_capital": float(starting_capital),
        "final_equity": float(starting_capital),
    }


def _streaks(pnls: Iterable[float]) -> tuple[int, int]:
    win_max = loss_max = win_cur = loss_cur = 0
    for p in pnls:
        if p > 0:
            win_cur += 1
            loss_cur = 0
            win_max = max(win_max, win_cur)
        elif p < 0:
            loss_cur += 1
            win_cur = 0
            loss_max = max(loss_max, loss_cur)
        else:
            win_cur = loss_cur = 0
    return win_max, loss_max


def _daily_returns(equity_curve: list[dict], starting_capital: float) -> pd.Series:
    if not equity_curve:
        return pd.Series(dtype=float)
    df = pd.DataFrame(equity_curve)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["equity"] = df["equity"].astype(float)
    df = df.set_index("datetime").sort_index()
    daily = df["equity"].resample("1D").last().ffill()
    rets = daily.pct_change().dropna()
    return rets


def _sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    if returns.empty or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def monthly_breakdown(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True).dt.tz_convert(None)
    df["month"] = df["exit_time"].dt.to_period("M").astype(str)
    grouped = df.groupby("month").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "count"),
        wins=("pnl", lambda s: int((s > 0).sum())),
    ).reset_index()
    return grouped.to_dict("records")


def dow_breakdown(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["dow"] = df["entry_time"].dt.day_name()
    grouped = df.groupby("dow").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "count"),
        wins=("pnl", lambda s: int((s > 0).sum())),
        avg_pnl=("pnl", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["trades"] * 100).round(1)
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grouped["_o"] = grouped["dow"].map({d: i for i, d in enumerate(order)})
    grouped = grouped.sort_values("_o").drop(columns=["_o"])
    return grouped.to_dict("records")


_SESSION_ORDER = {"NY": 0, "London": 1, "Asian": 2}


def session_breakdown(trades: list[dict]) -> list[dict]:
    """Per-session win/loss/PF/PnL row per session label present in the trade log."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "session" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows: list[dict] = []
    for name, group in df.groupby(df["session"].fillna("—")):
        wins_mask = group["pnl"] > 0
        losses_mask = group["pnl"] < 0
        gross_profit = float(group.loc[wins_mask, "pnl"].sum())
        gross_loss = float(-group.loc[losses_mask, "pnl"].sum())
        n = int(len(group))
        rows.append({
            "session": str(name),
            "trades": n,
            "wins": int(wins_mask.sum()),
            "losses": int(losses_mask.sum()),
            "win_rate": (float(wins_mask.sum()) / n * 100.0) if n else 0.0,
            "pnl": float(group["pnl"].sum()),
            "avg_pnl": float(group["pnl"].mean()) if n else 0.0,
            "best": float(group["pnl"].max()) if n else 0.0,
            "worst": float(group["pnl"].min()) if n else 0.0,
            "profit_factor": _safe_div(gross_profit, gross_loss),
        })
    rows.sort(key=lambda r: (_SESSION_ORDER.get(r["session"], 99), r["session"]))
    return rows


def hourly_breakdown(trades: list[dict], timezone: str = "UTC") -> list[dict]:
    """Group trades by entry hour in the given timezone.

    Returns one row per hour 0..23 that saw at least one trade, with
    total/win/loss counts, win_rate %, total P&L, and avg P&L per trade.
    """
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    try:
        local = df["entry_time"].dt.tz_convert(timezone)
    except Exception:
        local = df["entry_time"]
    df["hour"] = local.dt.hour
    grouped = df.groupby("hour").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "count"),
        wins=("pnl", lambda s: int((s > 0).sum())),
        avg_pnl=("pnl", "mean"),
    ).reset_index()
    grouped["losses"] = grouped["trades"] - grouped["wins"]
    grouped["win_rate"] = (grouped["wins"] / grouped["trades"] * 100).round(1)
    return grouped.to_dict("records")
