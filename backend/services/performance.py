"""Performance metrics and breakdowns for the Silver Bullet strategy."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) else 0.0


def compute_stats(trades: list[dict], equity_curve: list[dict], starting_capital: float) -> dict:
    if not trades:
        return _empty_stats(starting_capital)

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

    daily_returns = _daily_returns(equity_curve)
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


def _empty_stats(starting_capital: float) -> dict:
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


def _daily_returns(equity_curve: list[dict]) -> pd.Series:
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


# ------------------------- bucket utilities -------------------------

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


# ------------------------- generic breakdowns -------------------------

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


def hourly_breakdown(trades: list[dict], timezone: str = "America/New_York") -> list[dict]:
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


# ------------------------- Silver Bullet breakdowns -------------------------

KILL_ZONE_ORDER = ["london", "ny", "ny_pm"]
KILL_ZONE_LABELS = {"london": "London SB", "ny": "NY SB", "ny_pm": "NY PM SB"}

SWEEP_TYPE_ORDER = [
    "EQH", "EQL",
    "prev_day_high", "prev_day_low",
    "prev_london_high", "prev_london_low",
    "prev_ny_high", "prev_ny_low",
]

SWEEP_TYPE_LABELS = {
    "EQH": "Equal Highs",
    "EQL": "Equal Lows",
    "prev_day_high": "Prev Day High",
    "prev_day_low": "Prev Day Low",
    "prev_london_high": "Prev London H",
    "prev_london_low": "Prev London L",
    "prev_ny_high": "Prev NY H",
    "prev_ny_low": "Prev NY L",
}


def kill_zone_breakdown(trades: list[dict]) -> list[dict]:
    """P&L, win rate, avg duration per kill zone."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "kill_zone" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows: list[dict] = []
    for kz in KILL_ZONE_ORDER:
        sub = df[df["kill_zone"] == kz]
        row = _bucket_row("kill_zone", KILL_ZONE_LABELS[kz], sub)
        rows.append(row)
    return rows


def sweep_type_breakdown(trades: list[dict]) -> list[dict]:
    """Performance by liquidity type that was swept."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "sweep_level_type" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows: list[dict] = []
    for lt in SWEEP_TYPE_ORDER:
        sub = df[df["sweep_level_type"] == lt]
        if len(sub) == 0:
            continue
        rows.append(_bucket_row("sweep_type", SWEEP_TYPE_LABELS[lt], sub))
    return rows


FVG_SIZE_BUCKETS = [
    (0.0, 5.0, "< 5 pips"),
    (5.0, 10.0, "5-10"),
    (10.0, 15.0, "10-15"),
    (15.0, 25.0, "15-25"),
    (25.0, 1_000.0, "> 25"),
]


def fvg_size_breakdown(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "fvg_size_pips" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    df["fvg_size_pips"] = pd.to_numeric(df["fvg_size_pips"], errors="coerce").fillna(0.0)
    rows: list[dict] = []
    for lo, hi, label in FVG_SIZE_BUCKETS:
        sub = df[(df["fvg_size_pips"] >= lo) & (df["fvg_size_pips"] < hi)]
        rows.append(_bucket_row("bucket", label, sub))
    return rows


def confluence_breakdown(trades: list[dict]) -> list[dict]:
    """Win rate + avg PnL by confluence score (4-10)."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "confluence_score" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    df["confluence_score"] = pd.to_numeric(df["confluence_score"], errors="coerce").fillna(0).astype(int)
    rows: list[dict] = []
    for score in range(4, 11):
        sub = df[df["confluence_score"] == score]
        rows.append(_bucket_row("score", f"Score {score}", sub))
    return rows


def htf_bias_breakdown(trades: list[dict]) -> list[dict]:
    """Performance by HTF bias when the trade was taken."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "htf_bias" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows: list[dict] = []
    for bias in ("bullish", "bearish", "neutral"):
        sub = df[df["htf_bias"] == bias]
        rows.append(_bucket_row("bias", bias.title(), sub))
    return rows


def entry_time_breakdown(trades: list[dict]) -> list[dict]:
    """5-minute buckets within kill zones. Helps find the sweetest entry window."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    try:
        local = df["entry_time"].dt.tz_convert("America/New_York")
    except Exception:
        local = df["entry_time"]
    df["pnl"] = df["pnl"].astype(float)
    df["_hhmm"] = local.dt.strftime("%H:%M")
    rows: list[dict] = []
    for hhmm, sub in df.groupby("_hhmm"):
        rows.append(_bucket_row("bucket", hhmm, sub))
    rows.sort(key=lambda r: r["bucket"])
    return rows


def direction_breakdown(trades: list[dict]) -> list[dict]:
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "direction" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    return [_bucket_row("direction", str(name), group) for name, group in df.groupby("direction")]


def mss_breakdown(trades: list[dict]) -> list[dict]:
    """With-MSS vs without-MSS performance."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    if "mss_confirmed" not in df.columns:
        return []
    df["pnl"] = df["pnl"].astype(float)
    rows: list[dict] = []
    for flag, label in [(True, "MSS confirmed"), (False, "No MSS")]:
        sub = df[df["mss_confirmed"].astype(bool) == flag]
        rows.append(_bucket_row("bucket", label, sub))
    return rows
