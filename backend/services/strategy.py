"""DR / IDR breakout-retest strategy.

Core edge: after the 09:30-10:30 NY "Defining Range" is set, the first
clean break of that range most often does *not* reverse to take out the
opposite side the same day. We enter on a retest of the broken level
(or fall back to a midpoint retest) with confirmation, risk fixed by the
stop-buffer beyond the DR level, targets expressed as multiples of the
DR range itself.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import time as dtime, date
from typing import Optional

import pandas as pd
import pytz

from .indicators import build_indicator_frame
from .news_calendar import classify_news_day, parse_custom_skip_dates


# Confirmation pattern group → (bullish column, bearish column).
CONFIRMATION_PATTERN_COLS: dict[str, tuple[str, str]] = {
    "engulfing": ("bullish_engulfing", "bearish_engulfing"),
    "marubozu": ("bullish_marubozu", "bearish_marubozu"),
    "hammer_star": ("hammer", "shooting_star"),
    "inside_bar": ("inside_bar_bull", "inside_bar_bear"),
    "piercing_cloud": ("piercing_line", "dark_cloud_cover"),
    "doji": ("doji", "doji"),
}


@dataclass
class StrategyParams:
    # Instrument
    pip_size: float = 0.0001

    # Sizing / risk
    starting_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0

    # DR window
    dr_start_time: str = "09:30"
    dr_end_time: str = "10:30"
    dr_timezone: str = "America/New_York"
    min_dr_range_pips: float = 15.0
    max_dr_range_pips: float = 70.0

    # Entry
    entry_type: str = "retest_then_midpoint"  # retest_only | midpoint_only | retest_then_midpoint
    retest_tolerance_pips: float = 5.0
    require_confirmation_candle: bool = True
    confirmation_patterns: tuple = ("marubozu", "engulfing")

    # Time limits
    retest_window_minutes: int = 90
    last_entry_time: str = "13:00"

    # Risk / exits
    stop_buffer_pips: float = 3.0
    use_partial_tp: bool = True
    partial_tp_1_mult: float = 0.5
    partial_tp_2_mult: float = 1.0
    partial_tp_pct: float = 50.0
    move_be_after_t1: bool = True
    max_trades_per_day: int = 1

    # News filter
    enable_news_filter: bool = True
    custom_skip_dates: tuple = ()

    # Day filter
    allowed_days: tuple = (0, 1, 2, 3, 4)


@dataclass
class Trade:
    id: int
    direction: str
    entry_time: pd.Timestamp
    entry_price: float
    stop: float
    target1: float
    target2: float
    risk_per_unit: float
    units: float
    dr_high: float
    dr_low: float
    dr_range: float
    dr_range_pips: float
    entry_type_used: str
    pattern: str = ""
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    result: str = "open"
    bars_held: int = 0
    breakeven_moved: bool = False
    partial_taken: bool = False
    partial_pnl: float = 0.0
    partial_exit_time: Optional[pd.Timestamp] = None
    partial_exit_price: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat() if self.exit_time is not None else None
        d["partial_exit_time"] = (
            self.partial_exit_time.isoformat() if self.partial_exit_time is not None else None
        )
        return d


@dataclass
class _DayState:
    day: date
    dr_high: float
    dr_low: float
    dr_range: float
    dr_midpoint: float
    valid: bool = True
    skip_reason: str = ""
    breakout_direction: Optional[str] = None  # "bull" or "bear"
    breakout_time: Optional[pd.Timestamp] = None
    breakout_price: Optional[float] = None
    retest_deadline: Optional[pd.Timestamp] = None
    last_entry_deadline: Optional[pd.Timestamp] = None
    traded: bool = False
    dr_high_taken_after_break: bool = False
    dr_low_taken_after_break: bool = False


def _parse_time(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _resolve_confirmation_cols(keys: tuple) -> tuple[list[str], list[str]]:
    bull, bear = [], []
    for k in keys:
        pair = CONFIRMATION_PATTERN_COLS.get(k)
        if pair:
            bull.append(pair[0])
            bear.append(pair[1])
    return bull, bear


def _match_pattern(bar: dict, columns: list[str]) -> Optional[str]:
    for col in columns:
        if bar.get(col):
            return col
    return None


def _local_time(ts: pd.Timestamp, tz_name: str) -> dtime:
    local = ts.tz_convert(pytz.timezone(tz_name)) if ts.tzinfo else ts
    return local.time()


def _deadline_ts(ts: pd.Timestamp, hhmm: str, tz_name: str) -> pd.Timestamp:
    tz = pytz.timezone(tz_name)
    local = ts.tz_convert(tz) if ts.tzinfo else tz.localize(ts.to_pydatetime())
    h, m = hhmm.split(":")
    end_local = local.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if ts.tzinfo:
        return pd.Timestamp(end_local).tz_convert("UTC")
    return pd.Timestamp(end_local.replace(tzinfo=None))


def _force_close(t: Trade, price: float, ts: pd.Timestamp, result: str):
    if t.direction == "long":
        t.pnl = (price - t.entry_price) * t.units + t.partial_pnl
    else:
        t.pnl = (t.entry_price - price) * t.units + t.partial_pnl
    t.exit_price = price
    t.exit_time = ts
    t.result = result


def run_backtest(df: pd.DataFrame, params: StrategyParams) -> dict:
    if df.empty:
        return {"trades": [], "equity_curve": [], "diagnostics": {}, "day_states": []}

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
        dr_start=params.dr_start_time,
        dr_end=params.dr_end_time,
        dr_tz=params.dr_timezone,
    )

    pip_size = float(params.pip_size)
    min_range = float(params.min_dr_range_pips) * pip_size
    max_range = float(params.max_dr_range_pips) * pip_size
    retest_tol = float(params.retest_tolerance_pips) * pip_size
    stop_buffer = float(params.stop_buffer_pips) * pip_size
    partial_frac = float(params.partial_tp_pct) / 100.0
    entry_type = params.entry_type
    wants_retest = entry_type in ("retest_only", "retest_then_midpoint")
    wants_midpoint = entry_type in ("midpoint_only", "retest_then_midpoint")

    bull_conf, bear_conf = _resolve_confirmation_cols(tuple(params.confirmation_patterns))
    allowed_days = {int(d) for d in params.allowed_days}
    custom_skip = parse_custom_skip_dates(list(params.custom_skip_dates))

    trades: list[Trade] = []
    equity = params.starting_capital
    equity_curve: list[dict] = []
    open_trade: Optional[Trade] = None
    day_states: dict = {}
    next_id = 1

    diag = {
        "total_bars": 0,
        "post_dr_bars": 0,
        "total_days_seen": 0,
        "valid_dr_days": 0,
        "days_skipped_narrow": 0,
        "days_skipped_wide": 0,
        "days_skipped_news": 0,
        "days_skipped_day_of_week": 0,
        "days_with_breakout": 0,
        "bull_breakouts": 0,
        "bear_breakouts": 0,
        "entries_via_retest": 0,
        "entries_via_midpoint": 0,
        "days_no_entry": 0,
        # Directional bias tracking
        "bull_break_days_low_held": 0,
        "bull_break_days_low_broken": 0,
        "bear_break_days_high_held": 0,
        "bear_break_days_high_broken": 0,
        "breakout_to_retest_minutes": [],
        "news_skips_by_type": {},
    }

    rows = work.to_dict("records")
    n = len(rows)

    for i in range(n):
        bar = rows[i]
        ts = bar["datetime"]
        diag["total_bars"] += 1

        # Track day state as soon as we see a bar after the DR window ends.
        day: date = bar["_dr_date"]

        post_dr_flag = bool(bar.get("post_dr", False))
        dr_high = bar.get("dr_high")
        dr_low = bar.get("dr_low")
        dr_range = bar.get("dr_range")

        state = day_states.get(day)

        # Day initialization — fires on the first post-DR bar for a new day.
        if state is None and post_dr_flag and dr_high is not None and pd.notna(dr_high):
            diag["total_days_seen"] += 1
            state = _DayState(
                day=day,
                dr_high=float(dr_high),
                dr_low=float(dr_low),
                dr_range=float(dr_range),
                dr_midpoint=(float(dr_high) + float(dr_low)) / 2.0,
            )
            state.last_entry_deadline = _deadline_ts(ts, params.last_entry_time, params.dr_timezone)

            # Day-of-week filter (based on NY date).
            dow = pd.Timestamp(state.day).weekday()
            if dow not in allowed_days:
                state.valid = False
                state.skip_reason = "day_of_week"
                diag["days_skipped_day_of_week"] += 1
            # Range validity.
            elif state.dr_range < min_range:
                state.valid = False
                state.skip_reason = "range_too_narrow"
                diag["days_skipped_narrow"] += 1
            elif state.dr_range > max_range:
                state.valid = False
                state.skip_reason = "range_too_wide"
                diag["days_skipped_wide"] += 1
            # News filter.
            elif params.enable_news_filter:
                label = classify_news_day(day)
                if label is not None or day in custom_skip:
                    state.valid = False
                    state.skip_reason = f"news_{label or 'custom'}"
                    diag["days_skipped_news"] += 1
                    bucket = label or "custom"
                    diag["news_skips_by_type"][bucket] = diag["news_skips_by_type"].get(bucket, 0) + 1

            if state.valid:
                diag["valid_dr_days"] += 1
            day_states[day] = state

        if post_dr_flag:
            diag["post_dr_bars"] += 1

        # ---- Manage any open trade ----
        if open_trade is not None:
            open_trade.bars_held += 1
            t = open_trade
            high, low, close = bar["high"], bar["low"], bar["close"]

            # Partial TP at target 1.
            if params.use_partial_tp and not t.partial_taken:
                if t.direction == "long":
                    if high >= t.target1:
                        closed_units = t.units * partial_frac
                        t.partial_pnl = (t.target1 - t.entry_price) * closed_units
                        t.partial_exit_price = t.target1
                        t.partial_exit_time = ts
                        t.units -= closed_units
                        t.partial_taken = True
                        if params.move_be_after_t1:
                            t.stop = max(t.stop, t.entry_price)
                            t.breakeven_moved = True
                else:
                    if low <= t.target1:
                        closed_units = t.units * partial_frac
                        t.partial_pnl = (t.entry_price - t.target1) * closed_units
                        t.partial_exit_price = t.target1
                        t.partial_exit_time = ts
                        t.units -= closed_units
                        t.partial_taken = True
                        if params.move_be_after_t1:
                            t.stop = min(t.stop, t.entry_price)
                            t.breakeven_moved = True

            # Full exit: stop or target 2.
            if t.direction == "long":
                if low <= t.stop:
                    result = "breakeven" if t.partial_taken and t.breakeven_moved else "loss"
                    _force_close(t, t.stop, ts, result)
                elif params.use_partial_tp and high >= t.target2:
                    _force_close(t, t.target2, ts, "win")
                elif not params.use_partial_tp and high >= t.target1:
                    # Single-target mode collapses to target1.
                    _force_close(t, t.target1, ts, "win")
            else:
                if high >= t.stop:
                    result = "breakeven" if t.partial_taken and t.breakeven_moved else "loss"
                    _force_close(t, t.stop, ts, result)
                elif params.use_partial_tp and low <= t.target2:
                    _force_close(t, t.target2, ts, "win")
                elif not params.use_partial_tp and low <= t.target1:
                    _force_close(t, t.target1, ts, "win")

            # Force close at last_entry_time (end of trading window).
            if (
                t.exit_time is None
                and state is not None
                and state.last_entry_deadline is not None
                and ts >= state.last_entry_deadline
            ):
                _force_close(t, close, ts, "timeout")

            if t.exit_time is not None:
                t.pnl_pct = (t.pnl / params.starting_capital) * 100
                equity += t.pnl
                trades.append(t)
                open_trade = None

        equity_curve.append({"datetime": ts.isoformat(), "equity": equity})

        # ---- Signal generation (only on post-DR bars for valid days) ----
        if state is None or not state.valid or state.traded or open_trade is not None:
            # Still track high/low taken post-breakout for directional bias.
            if state is not None and state.breakout_direction is not None:
                if state.breakout_direction == "bull" and bar["low"] <= state.dr_low:
                    state.dr_low_taken_after_break = True
                elif state.breakout_direction == "bear" and bar["high"] >= state.dr_high:
                    state.dr_high_taken_after_break = True
            continue

        if not post_dr_flag:
            continue

        # Past last_entry_time — no new entries this day.
        if state.last_entry_deadline is not None and ts >= state.last_entry_deadline:
            continue

        close = bar["close"]
        high = bar["high"]
        low = bar["low"]

        # --- Breakout detection ---
        if state.breakout_direction is None:
            # Need a prior bar that was inside or touching the DR. Use the
            # previous post-DR bar for the inside-range check; if this is
            # the very first post-DR bar, allow it.
            prev = rows[i - 1] if i > 0 else None
            prev_inside = True
            if prev is not None and prev.get("post_dr"):
                pc = prev["close"]
                prev_inside = (pc <= state.dr_high) and (pc >= state.dr_low)

            if close > state.dr_high and prev_inside:
                state.breakout_direction = "bull"
                state.breakout_time = ts
                state.breakout_price = close
                state.retest_deadline = ts + pd.Timedelta(minutes=params.retest_window_minutes)
                diag["days_with_breakout"] += 1
                diag["bull_breakouts"] += 1
            elif close < state.dr_low and prev_inside:
                state.breakout_direction = "bear"
                state.breakout_time = ts
                state.breakout_price = close
                state.retest_deadline = ts + pd.Timedelta(minutes=params.retest_window_minutes)
                diag["days_with_breakout"] += 1
                diag["bear_breakouts"] += 1

            # Never enter on the breakout bar itself — wait for retest/midpoint.
            continue

        # --- Entry logic (after breakout) ---
        is_bull = state.breakout_direction == "bull"
        retest_level = state.dr_high if is_bull else state.dr_low
        within_retest_window = (
            state.retest_deadline is not None and ts <= state.retest_deadline
        )

        entry_type_used = None
        pattern = ""

        # Primary: DR level retest.
        if wants_retest and within_retest_window:
            touched = (
                (is_bull and low <= retest_level + retest_tol)
                or (not is_bull and high >= retest_level - retest_tol)
            )
            if touched:
                if params.require_confirmation_candle:
                    cols = bull_conf if is_bull else bear_conf
                    pattern = _match_pattern(bar, cols) or ""
                    if pattern:
                        entry_type_used = "DR Retest"
                else:
                    entry_type_used = "DR Retest"

        # Fallback: midpoint retest after window expires (or midpoint-only mode).
        if entry_type_used is None and wants_midpoint:
            midpoint_ok = (
                state.retest_deadline is not None
                and ts > state.retest_deadline
                and entry_type == "retest_then_midpoint"
            ) or entry_type == "midpoint_only"

            if midpoint_ok:
                mp = state.dr_midpoint
                touched = (
                    (is_bull and low <= mp + retest_tol and low >= state.dr_low)
                    or (not is_bull and high >= mp - retest_tol and high <= state.dr_high)
                )
                if touched:
                    if params.require_confirmation_candle:
                        cols = bull_conf if is_bull else bear_conf
                        pattern = _match_pattern(bar, cols) or ""
                        if pattern:
                            entry_type_used = "Midpoint Retest"
                    else:
                        entry_type_used = "Midpoint Retest"

        if entry_type_used is None:
            continue

        # --- Build the trade ---
        entry_price = float(close)
        if is_bull:
            stop = state.dr_high - stop_buffer
            risk = entry_price - stop
            if risk <= 0:
                continue
            t1 = entry_price + state.dr_range * float(params.partial_tp_1_mult)
            t2 = entry_price + state.dr_range * float(params.partial_tp_2_mult)
            direction = "long"
        else:
            stop = state.dr_low + stop_buffer
            risk = stop - entry_price
            if risk <= 0:
                continue
            t1 = entry_price - state.dr_range * float(params.partial_tp_1_mult)
            t2 = entry_price - state.dr_range * float(params.partial_tp_2_mult)
            direction = "short"

        risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
        units = risk_dollars / risk

        open_trade = Trade(
            id=next_id,
            direction=direction,
            entry_time=ts,
            entry_price=entry_price,
            stop=stop,
            target1=t1,
            target2=t2,
            risk_per_unit=risk,
            units=units,
            dr_high=state.dr_high,
            dr_low=state.dr_low,
            dr_range=state.dr_range,
            dr_range_pips=state.dr_range / pip_size,
            entry_type_used=entry_type_used,
            pattern=pattern,
        )
        next_id += 1
        state.traded = True

        if entry_type_used == "DR Retest":
            diag["entries_via_retest"] += 1
        else:
            diag["entries_via_midpoint"] += 1
        if state.breakout_time is not None:
            mins = (ts - state.breakout_time).total_seconds() / 60.0
            diag["breakout_to_retest_minutes"].append(mins)

    # Close any trade left open at the end of data.
    if open_trade is not None and rows:
        last = rows[-1]
        _force_close(open_trade, last["close"], last["datetime"], "timeout")
        open_trade.pnl_pct = (open_trade.pnl / params.starting_capital) * 100
        equity += open_trade.pnl
        trades.append(open_trade)

    # Tally per-day directional bias and no-entry days.
    for st in day_states.values():
        if not st.valid:
            continue
        if st.breakout_direction is None:
            diag["days_no_entry"] += 1
            continue
        if not st.traded:
            diag["days_no_entry"] += 1
        if st.breakout_direction == "bull":
            if st.dr_low_taken_after_break:
                diag["bull_break_days_low_broken"] += 1
            else:
                diag["bull_break_days_low_held"] += 1
        else:
            if st.dr_high_taken_after_break:
                diag["bear_break_days_high_broken"] += 1
            else:
                diag["bear_break_days_high_held"] += 1

    # Summarize breakout→retest latency.
    latencies = diag.pop("breakout_to_retest_minutes")
    if latencies:
        diag["avg_breakout_to_entry_minutes"] = sum(latencies) / len(latencies)
    else:
        diag["avg_breakout_to_entry_minutes"] = 0.0

    # Serialize per-day states for downstream diagnostics (range buckets).
    day_state_records = [
        {
            "date": str(st.day),
            "valid": st.valid,
            "skip_reason": st.skip_reason,
            "dr_range_pips": (st.dr_range / pip_size) if st.dr_range is not None else None,
            "dr_high": st.dr_high,
            "dr_low": st.dr_low,
            "breakout_direction": st.breakout_direction,
            "traded": st.traded,
            "opposite_side_held": (
                (st.breakout_direction == "bull" and not st.dr_low_taken_after_break)
                or (st.breakout_direction == "bear" and not st.dr_high_taken_after_break)
            ) if st.breakout_direction else None,
        }
        for st in day_states.values()
    ]

    return {
        "trades": [t.to_dict() for t in trades],
        "equity_curve": equity_curve,
        "diagnostics": diag,
        "day_states": day_state_records,
    }
