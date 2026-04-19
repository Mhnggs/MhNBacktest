"""EMA crossover strategy with candlestick-pattern entry triggers."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import time as dtime
from typing import Optional

import pandas as pd
import pytz

from .indicators import build_indicator_frame


# Pattern group → (bullish column, bearish column).
# The UI offers these group keys; the engine expands each to the directional
# column matching the crossover direction.
PATTERN_GROUPS: dict[str, tuple[str, str]] = {
    "engulfing": ("bullish_engulfing", "bearish_engulfing"),
    "hammer_star": ("hammer", "shooting_star"),
    "piercing_cloud": ("piercing_line", "dark_cloud_cover"),
    "marubozu": ("bullish_marubozu", "bearish_marubozu"),
    "doji": ("doji", "doji"),
}


@dataclass
class StrategyParams:
    # Core strategy
    ema_period: int = 9
    ema_secondary: int = 20
    allowed_patterns: tuple = ("engulfing", "hammer_star", "marubozu")
    stop_loss_pips: float = 20.0
    risk_reward: float = 2.0
    pip_size: float = 0.0001  # 0.0001 for majors, 0.01 for JPY, 0.1 for gold, etc.

    # Risk / sizing
    starting_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0
    max_trades_per_day: int = 3

    # Session window
    session_start: str = "09:45"
    session_end: str = "11:30"
    session_2_start: str = "13:30"
    session_2_end: str = "15:00"
    use_session_2: bool = True
    timezone: str = "America/New_York"

    # Day filter (0 = Mon … 4 = Fri)
    allowed_days: tuple = (0, 1, 2, 3, 4)


@dataclass
class Trade:
    id: int
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    stop: float
    target: float
    risk_per_unit: float
    units: float
    pattern: str = ""
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    result: str = "open"
    bars_held: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat() if self.exit_time is not None else None
        return d


def _parse_time(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _within_session(ts: pd.Timestamp, params: StrategyParams) -> bool:
    tz = pytz.timezone(params.timezone)
    local = ts.tz_convert(tz) if ts.tzinfo else tz.localize(ts.to_pydatetime())
    t = local.time()
    if _parse_time(params.session_start) <= t <= _parse_time(params.session_end):
        return True
    if params.use_session_2:
        if _parse_time(params.session_2_start) <= t <= _parse_time(params.session_2_end):
            return True
    return False


def _session_end_today(ts: pd.Timestamp, params: StrategyParams) -> pd.Timestamp:
    tz = pytz.timezone(params.timezone)
    local = ts.tz_convert(tz) if ts.tzinfo else tz.localize(ts.to_pydatetime())
    end_str = params.session_2_end if params.use_session_2 else params.session_end
    eh, em = end_str.split(":")
    end_local = local.replace(hour=int(eh), minute=int(em), second=0, microsecond=0)
    return (
        pd.Timestamp(end_local).tz_convert("UTC")
        if ts.tzinfo else pd.Timestamp(end_local.replace(tzinfo=None))
    )


def _resolve_pattern_columns(allowed_keys: tuple) -> tuple[list[str], list[str]]:
    bull, bear = [], []
    for key in allowed_keys:
        if key in PATTERN_GROUPS:
            b, s = PATTERN_GROUPS[key]
            bull.append(b)
            bear.append(s)
    return bull, bear


def _match_pattern(bar: dict, columns: list[str]) -> Optional[str]:
    for col in columns:
        if bar.get(col):
            return col
    return None


def run_backtest(df: pd.DataFrame, params: StrategyParams) -> dict:
    if df.empty:
        return {"trades": [], "equity_curve": [], "diagnostics": {}}

    work = df.copy()
    if not isinstance(work["datetime"].dtype, pd.DatetimeTZDtype):
        source_tz = df.attrs.get("source_tz", "UTC")
        tz = pytz.timezone(source_tz)
        work["datetime"] = (
            work["datetime"]
            .dt.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
            .dt.tz_convert("UTC")
        )
        work = work.dropna(subset=["datetime"]).reset_index(drop=True)
    else:
        work["datetime"] = work["datetime"].dt.tz_convert("UTC")

    work = build_indicator_frame(
        work,
        ema_period=params.ema_period,
        ema_secondary=params.ema_secondary,
    )

    tz = pytz.timezone(params.timezone)
    local_ts = work["datetime"].dt.tz_convert(tz)
    work["_session_date"] = local_ts.dt.date
    work["_local_dow"] = local_ts.dt.dayofweek
    work["_in_session"] = work["datetime"].apply(lambda ts: _within_session(ts, params))

    allowed_days = {int(d) for d in params.allowed_days}
    bull_cols, bear_cols = _resolve_pattern_columns(tuple(params.allowed_patterns))

    trades: list[Trade] = []
    equity = params.starting_capital
    equity_curve: list[dict] = []
    open_trade: Optional[Trade] = None
    daily_count: dict = {}
    next_id = 1
    stop_distance = float(params.stop_loss_pips) * float(params.pip_size)

    diag = {
        "total_bars": 0,
        "in_session_bars": 0,
        "rejected_day_of_week": 0,
        "rejected_max_per_day": 0,
        "rejected_open_trade": 0,
        "bullish_crosses": 0,
        "bearish_crosses": 0,
        "rejected_no_pattern": 0,
        "long_signals": 0,
        "short_signals": 0,
        "pattern_counts": {},
        "allowed_days": list(params.allowed_days),
        "allowed_patterns": list(params.allowed_patterns),
    }

    rows = work.to_dict("records")
    n = len(rows)

    for i in range(1, n):
        bar = rows[i]
        prev = rows[i - 1]
        ts = bar["datetime"]
        session_date = bar["_session_date"]

        # ---- Manage open trade first ----
        if open_trade is not None:
            open_trade.bars_held += 1
            high, low, close = bar["high"], bar["low"], bar["close"]
            t = open_trade

            if t.direction == "long":
                if low <= t.stop:
                    t.exit_price = t.stop
                    t.exit_time = ts
                    t.pnl = (t.stop - t.entry_price) * t.units
                    t.result = "loss" if t.pnl < 0 else "breakeven"
                elif high >= t.target:
                    t.exit_price = t.target
                    t.exit_time = ts
                    t.pnl = (t.target - t.entry_price) * t.units
                    t.result = "win"
            else:  # short
                if high >= t.stop:
                    t.exit_price = t.stop
                    t.exit_time = ts
                    t.pnl = (t.entry_price - t.stop) * t.units
                    t.result = "loss" if t.pnl < 0 else "breakeven"
                elif low <= t.target:
                    t.exit_price = t.target
                    t.exit_time = ts
                    t.pnl = (t.entry_price - t.target) * t.units
                    t.result = "win"

            if t.exit_time is None:
                end_today = _session_end_today(ts, params)
                if ts >= end_today:
                    if t.direction == "long":
                        t.pnl = (close - t.entry_price) * t.units
                    else:
                        t.pnl = (t.entry_price - close) * t.units
                    t.exit_price = close
                    t.exit_time = ts
                    t.result = "timeout"

            if t.exit_time is not None:
                t.pnl_pct = (t.pnl / params.starting_capital) * 100
                equity += t.pnl
                trades.append(t)
                open_trade = None

        equity_curve.append({"datetime": ts.isoformat(), "equity": equity})

        diag["total_bars"] += 1

        if open_trade is not None:
            diag["rejected_open_trade"] += 1
            continue
        if not bar["_in_session"]:
            continue
        diag["in_session_bars"] += 1
        if int(bar["_local_dow"]) not in allowed_days:
            diag["rejected_day_of_week"] += 1
            continue
        if daily_count.get(session_date, 0) >= params.max_trades_per_day:
            diag["rejected_max_per_day"] += 1
            continue

        ef_now, es_now = bar.get("ema_fast"), bar.get("ema_slow")
        ef_prev, es_prev = prev.get("ema_fast"), prev.get("ema_slow")
        if any(pd.isna(v) for v in (ef_now, es_now, ef_prev, es_prev)):
            continue

        bull_cross = ef_prev <= es_prev and ef_now > es_now
        bear_cross = ef_prev >= es_prev and ef_now < es_now
        if not (bull_cross or bear_cross):
            continue

        if bull_cross:
            diag["bullish_crosses"] += 1
            pattern = _match_pattern(bar, bull_cols)
            if pattern is None:
                diag["rejected_no_pattern"] += 1
                continue
            entry = float(bar["close"])
            stop = entry - stop_distance
            target = entry + stop_distance * params.risk_reward
            if stop_distance <= 0:
                continue
            risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
            units = risk_dollars / stop_distance
            diag["long_signals"] += 1
            diag["pattern_counts"][pattern] = diag["pattern_counts"].get(pattern, 0) + 1
            open_trade = Trade(
                id=next_id, direction="long", entry_time=ts, entry_price=entry,
                stop=stop, target=target, risk_per_unit=stop_distance,
                units=units, pattern=pattern,
            )
            next_id += 1
            daily_count[session_date] = daily_count.get(session_date, 0) + 1

        elif bear_cross:
            diag["bearish_crosses"] += 1
            pattern = _match_pattern(bar, bear_cols)
            if pattern is None:
                diag["rejected_no_pattern"] += 1
                continue
            entry = float(bar["close"])
            stop = entry + stop_distance
            target = entry - stop_distance * params.risk_reward
            if stop_distance <= 0:
                continue
            risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
            units = risk_dollars / stop_distance
            diag["short_signals"] += 1
            diag["pattern_counts"][pattern] = diag["pattern_counts"].get(pattern, 0) + 1
            open_trade = Trade(
                id=next_id, direction="short", entry_time=ts, entry_price=entry,
                stop=stop, target=target, risk_per_unit=stop_distance,
                units=units, pattern=pattern,
            )
            next_id += 1
            daily_count[session_date] = daily_count.get(session_date, 0) + 1

    return {
        "trades": [t.to_dict() for t in trades],
        "equity_curve": equity_curve,
        "diagnostics": diag,
    }
