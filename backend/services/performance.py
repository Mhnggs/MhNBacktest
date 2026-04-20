"""Performance metrics: Sharpe, drawdown, win rate, profit factor, breakdowns."""

from __future__ import annotations

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


def _bucket_row(label_key: str, label: str, sub: pd.DataFrame) -> dict:
    n = int(len(sub))
    if n == 0:
        return {
            label_key: label, "trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "pnl": 0.0, "avg_pnl": 0.0,
            "best": 0.0, "worst": 0.0, "profit_factor": 0.0,
        }
    wins_mask = sub["pnl"] > 0
    losses_mask = sub["pnl"] < 0
    gross_profit = float(sub.loc[wins_mask, "pnl"].sum())
    gross_loss = float(-sub.loc[losses_mask, "pnl"].sum())
    return {
        label_key: label,
        "trades": n,
        "wins": int(wins_mask.sum()),
        "losses": int(losses_mask.sum()),
        "win_rate": float(wins_mask.sum()) / n * 100.0,
        "pnl": float(sub["pnl"].sum()),
        "avg_pnl": float(sub["pnl"].mean()),
        "best": float(sub["pnl"].max()),
        "worst": float(sub["pnl"].min()),
        "profit_factor": _safe_div(gross_profit, gross_loss),
    }


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


def hourly_breakdown(trades: list[dict], timezone: str = "UTC") -> list[dict]:
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


LEVEL_TYPE_ORDER = [
    "prev_day_high", "prev_day_low", "prev_day_open", "prev_day_close",
    "vwap", "vwap_upper_1", "vwap_upper_2", "vwap_lower_1", "vwap_lower_2",
    "round_number", "london_high", "london_low",
    "daily_open", "weekly_open",
]


def level_performance_breakdown(trades: list[dict]) -> list[dict]:
    """Win rate and P&L per structure-level type."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "level_type" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows = [_bucket_row("level_type", name, group) for name, group in df.groupby("level_type")]
    rows.sort(key=lambda r: LEVEL_TYPE_ORDER.index(r["level_type"]) if r["level_type"] in LEVEL_TYPE_ORDER else 999)
    return rows


RSI_BUCKETS_LONG = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30)]
RSI_BUCKETS_SHORT = [(70, 80), (80, 85), (85, 90), (90, 95), (95, 100)]


def rsi_bucket_breakdown(trades: list[dict]) -> list[dict]:
    """Win rate / avg pnl bucketed by RSI value at entry (separately for
    long-oversold entries and short-overbought entries)."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "rsi_at_entry" not in df.columns or "direction" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    df["rsi_at_entry"] = pd.to_numeric(df["rsi_at_entry"], errors="coerce")

    longs = df[df["direction"] == "long"]
    shorts = df[df["direction"] == "short"]
    rows: list[dict] = []
    for lo, hi in RSI_BUCKETS_LONG:
        label = f"L RSI {lo}-{hi}"
        sub = longs[(longs["rsi_at_entry"] >= lo) & (longs["rsi_at_entry"] < hi)]
        rows.append(_bucket_row("bucket", label, sub))
    for lo, hi in RSI_BUCKETS_SHORT:
        label = f"S RSI {lo}-{hi}"
        sub = shorts[(shorts["rsi_at_entry"] >= lo) & (shorts["rsi_at_entry"] < hi)]
        rows.append(_bucket_row("bucket", label, sub))
    return rows


def exit_reason_breakdown(trades: list[dict]) -> list[dict]:
    """P&L + win rate per exit type (stop / target / rsi / time / eod)."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "exit_reason" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    return [_bucket_row("exit_reason", str(name or "—"), group)
            for name, group in df.groupby("exit_reason")]


BB_WIDTH_BUCKETS = [
    (0.0, 0.001, "tight (<0.001)"),
    (0.001, 0.0015, "0.0010-0.0015"),
    (0.0015, 0.002, "0.0015-0.0020"),
    (0.002, 0.003, "0.0020-0.0030"),
    (0.003, 1.0, "wide (>0.003)"),
]


def bb_width_breakdown(trades: list[dict]) -> list[dict]:
    """Validate trend filter: performance vs Bollinger-band width at entry."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "bb_width_at_entry" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    df["bb_width_at_entry"] = pd.to_numeric(df["bb_width_at_entry"], errors="coerce")
    return [_bucket_row("bucket", label,
                        df[(df["bb_width_at_entry"] >= lo) & (df["bb_width_at_entry"] < hi)])
            for lo, hi, label in BB_WIDTH_BUCKETS]


def entry_time_breakdown(trades: list[dict], tz: str = "Europe/London") -> list[dict]:
    """Bucket entries into 30-min windows within the primary session TZ."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    try:
        local = df["entry_time"].dt.tz_convert(tz)
    except Exception:
        local = df["entry_time"]
    df["_hhmm"] = local.dt.hour + local.dt.minute / 60.0
    df["pnl"] = df["pnl"].astype(float)

    buckets = [(h, h + 0.5, f"{int(h):02d}:{'00' if h % 1 == 0 else '30'}") for h in
               [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5,
                9.0, 9.5, 10.0, 10.5, 11.0, 11.5,
                15.0, 15.5, 16.0, 16.5]]
    rows = []
    for lo, hi, label in buckets:
        sub = df[(df["_hhmm"] >= lo) & (df["_hhmm"] < hi)]
        if len(sub):
            rows.append(_bucket_row("bucket", label, sub))
    return rows


def direction_breakdown(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "direction" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    return [_bucket_row("direction", str(name), group) for name, group in df.groupby("direction")]
