"""RSI Exhaustion Mean Reversion Strategy.

Core edge: when RSI(2) reaches an extreme value AT a well-known structure
level (previous-day high/low, VWAP bands, round numbers, London high/low,
daily/weekly open), price tends to mean-revert. The combination of
oscillator extreme + structure produces the edge; either alone is weak.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date
from typing import Optional

import math
import numpy as np
import pandas as pd
import pytz

from .indicators import build_indicator_frame
from .news_calendar import classify_news_day, parse_custom_skip_dates


CONFIRMATION_PATTERN_COLS: dict[str, tuple[str, str]] = {
    "engulfing": ("bullish_engulfing", "bearish_engulfing"),
    "marubozu": ("bullish_marubozu", "bearish_marubozu"),
    "hammer_star": ("hammer", "shooting_star"),
    "inside_bar": ("inside_bar_bull", "inside_bar_bear"),
    "piercing_cloud": ("piercing_line", "dark_cloud_cover"),
    "doji": ("doji", "doji"),
}


# Level type keys used for diagnostics and the level-performance breakdown.
LEVEL_TYPES = [
    "prev_day_high", "prev_day_low", "prev_day_close", "prev_day_open",
    "vwap", "vwap_upper_1", "vwap_upper_2", "vwap_lower_1", "vwap_lower_2",
    "round_number", "london_high", "london_low",
    "daily_open", "weekly_open",
]

SUPPORT_LEVEL_TYPES = {
    "prev_day_low", "vwap_lower_1", "vwap_lower_2",
    "round_number", "london_low", "daily_open", "weekly_open",
    "vwap", "prev_day_close", "prev_day_open",
}
RESISTANCE_LEVEL_TYPES = {
    "prev_day_high", "vwap_upper_1", "vwap_upper_2",
    "round_number", "london_high", "daily_open", "weekly_open",
    "vwap", "prev_day_close", "prev_day_open",
}


@dataclass
class StrategyParams:
    # Instrument
    pip_size: float = 0.0001

    # Sizing / risk
    starting_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0

    # RSI settings
    rsi_period: int = 2
    rsi_medium_period: int = 3
    rsi_slow_period: int = 14
    rsi_oversold: float = 10.0
    rsi_overbought: float = 90.0
    rsi_exit_level: float = 50.0
    use_rsi_exit: bool = True

    # Structure level toggles
    use_prev_day_high_low: bool = True
    use_prev_day_open_close: bool = False
    use_vwap: bool = True
    use_vwap_bands: bool = True
    use_round_numbers: bool = True
    use_london_levels: bool = True
    use_daily_open: bool = True
    use_weekly_open: bool = False
    level_tolerance_pips: float = 5.0
    require_level_confluence: bool = False
    round_number_grid_pips: float = 50.0

    # Trend filter
    use_trend_filter: bool = True
    trend_filter_type: str = "bb_width"  # "bb_width" | "adx" | "both"
    bb_width_max: float = 0.0015
    adx_max: float = 25.0

    # Session filter (times interpreted in Europe/London)
    session_timezone: str = "Europe/London"
    avoid_session_opens: bool = True
    use_asian_session: bool = True     # 00:00-07:00 London
    use_london_mid: bool = True        # 09:00-12:00 London
    use_ny_mid: bool = True            # 15:00-17:00 London

    # Confirmation
    require_confirmation_candle: bool = False
    confirmation_patterns: tuple = ("marubozu", "engulfing")

    # Risk & exit
    stop_pips: float = 8.0
    use_fixed_target: bool = True
    fixed_target_pips: float = 15.0
    rr_ratio: float = 1.5  # used if use_fixed_target is False and no nearest-opposite-level
    max_trade_duration_minutes: int = 120
    max_trades_per_day: int = 4

    # News filter
    enable_news_filter: bool = True
    custom_skip_dates: tuple = ()

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
    level_type: str
    level_price: float
    rsi_at_entry: float
    bb_width_at_entry: float
    pattern: str = ""
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""     # "stop" | "target" | "rsi" | "time" | "eod"
    pnl: float = 0.0
    pnl_pct: float = 0.0
    result: str = "open"
    bars_held: int = 0
    mfe_pips: float = 0.0   # max favorable excursion in pips

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat() if self.exit_time is not None else None
        return d


@dataclass
class _DayState:
    day: date
    trades_taken: int = 0


def _match_pattern(bar: dict, columns: list[str]) -> Optional[str]:
    for col in columns:
        if bar.get(col):
            return col
    return None


def _resolve_confirmation_cols(keys: tuple) -> tuple[list[str], list[str]]:
    bull, bear = [], []
    for k in keys:
        pair = CONFIRMATION_PATTERN_COLS.get(k)
        if pair:
            bull.append(pair[0])
            bear.append(pair[1])
    return bull, bear


def _in_avoided_open(hhmm: float) -> bool:
    """First 30 min of London (08:00-08:30) or NY (13:30-14:00) in London-time."""
    return (8.0 <= hhmm < 8.5) or (13.5 <= hhmm < 14.0)


def _session_allowed(hhmm: float, p: StrategyParams) -> bool:
    if p.avoid_session_opens and _in_avoided_open(hhmm):
        return False
    asian = 0.0 <= hhmm < 7.0
    london_mid = 9.0 <= hhmm < 12.0
    ny_mid = 15.0 <= hhmm < 17.0
    if asian and p.use_asian_session:
        return True
    if london_mid and p.use_london_mid:
        return True
    if ny_mid and p.use_ny_mid:
        return True
    return False


def _collect_candidate_levels(bar: dict, p: StrategyParams) -> list[tuple[str, float]]:
    """Gather every enabled structure level price for this bar."""
    lvls: list[tuple[str, float]] = []
    def _add(name: str, val):
        if val is None:
            return
        try:
            f = float(val)
        except (TypeError, ValueError):
            return
        if math.isnan(f):
            return
        lvls.append((name, f))

    if p.use_prev_day_high_low:
        _add("prev_day_high", bar.get("prev_day_high"))
        _add("prev_day_low", bar.get("prev_day_low"))
    if p.use_prev_day_open_close:
        _add("prev_day_open", bar.get("prev_day_open"))
        _add("prev_day_close", bar.get("prev_day_close"))
    if p.use_vwap:
        _add("vwap", bar.get("vwap"))
    if p.use_vwap_bands:
        _add("vwap_upper_1", bar.get("vwap_upper_1"))
        _add("vwap_upper_2", bar.get("vwap_upper_2"))
        _add("vwap_lower_1", bar.get("vwap_lower_1"))
        _add("vwap_lower_2", bar.get("vwap_lower_2"))
    if p.use_london_levels:
        _add("london_high", bar.get("london_high"))
        _add("london_low", bar.get("london_low"))
    if p.use_daily_open:
        _add("daily_open", bar.get("daily_open"))
    if p.use_weekly_open:
        _add("weekly_open", bar.get("weekly_open"))
    if p.use_round_numbers:
        close = float(bar["close"])
        grid = p.round_number_grid_pips * p.pip_size
        if grid > 0:
            lower = math.floor(close / grid) * grid
            upper = lower + grid
            _add("round_number", round(lower, 10))
            _add("round_number", round(upper, 10))
    return lvls


def _nearest_level_on_side(
    close: float,
    levels: list[tuple[str, float]],
    side: str,  # "support" (below/near price) or "resistance" (above/near price)
    tolerance: float,
) -> Optional[tuple[str, float, float]]:
    """Return (name, price, distance) of nearest valid level within tolerance."""
    allowed = SUPPORT_LEVEL_TYPES if side == "support" else RESISTANCE_LEVEL_TYPES
    best = None
    for name, price in levels:
        if name not in allowed:
            continue
        if side == "support" and price > close + tolerance:
            continue
        if side == "resistance" and price < close - tolerance:
            continue
        d = abs(close - price)
        if d > tolerance:
            continue
        if best is None or d < best[2]:
            best = (name, price, d)
    return best


def _count_levels_within(close: float, levels: list[tuple[str, float]], tolerance: float) -> int:
    return sum(1 for _, p in levels if abs(close - p) <= tolerance)


def _force_close(t: Trade, price: float, ts: pd.Timestamp, reason: str, result: str):
    if t.direction == "long":
        t.pnl = (price - t.entry_price) * t.units
    else:
        t.pnl = (t.entry_price - price) * t.units
    t.exit_price = price
    t.exit_time = ts
    t.exit_reason = reason
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
        rsi_fast=params.rsi_period,
        rsi_medium=params.rsi_medium_period,
        rsi_slow=params.rsi_slow_period,
    )

    pip_size = float(params.pip_size)
    level_tol = float(params.level_tolerance_pips) * pip_size
    stop_dist = float(params.stop_pips) * pip_size
    fixed_target_dist = float(params.fixed_target_pips) * pip_size
    max_dur = pd.Timedelta(minutes=int(params.max_trade_duration_minutes))

    bull_conf, bear_conf = _resolve_confirmation_cols(tuple(params.confirmation_patterns))
    allowed_days = {int(d) for d in params.allowed_days}
    custom_skip = parse_custom_skip_dates(list(params.custom_skip_dates))
    session_tz = pytz.timezone(params.session_timezone)

    trades: list[Trade] = []
    equity = params.starting_capital
    equity_curve: list[dict] = []
    open_trade: Optional[Trade] = None
    day_states: dict = {}
    next_id = 1

    diag = {
        "total_bars": 0,
        "signals_raw": 0,
        "skipped_trend_filter": 0,
        "skipped_session": 0,
        "skipped_no_level": 0,
        "skipped_no_confluence": 0,
        "skipped_no_confirmation": 0,
        "skipped_news": 0,
        "skipped_day_of_week": 0,
        "skipped_open_trade": 0,
        "skipped_max_trades_per_day": 0,
        "entries": 0,
        "long_entries": 0,
        "short_entries": 0,
        "news_skips_by_type": {},
    }

    rows = work.to_dict("records")
    n = len(rows)

    for i in range(n):
        bar = rows[i]
        ts: pd.Timestamp = bar["datetime"]
        diag["total_bars"] += 1

        # Manage any open trade BEFORE potentially opening a new one.
        if open_trade is not None:
            t = open_trade
            t.bars_held += 1
            high, low, close = bar["high"], bar["low"], bar["close"]

            # Track max favorable excursion.
            if t.direction == "long":
                mfe = (high - t.entry_price) / pip_size
            else:
                mfe = (t.entry_price - low) / pip_size
            if mfe > t.mfe_pips:
                t.mfe_pips = mfe

            # 1) Stop loss.
            if t.direction == "long" and low <= t.stop:
                _force_close(t, t.stop, ts, "stop", "loss")
            elif t.direction == "short" and high >= t.stop:
                _force_close(t, t.stop, ts, "stop", "loss")

            # 2) Fixed target.
            if t.exit_time is None:
                if t.direction == "long" and high >= t.target:
                    _force_close(t, t.target, ts, "target", "win")
                elif t.direction == "short" and low <= t.target:
                    _force_close(t, t.target, ts, "target", "win")

            # 3) RSI exit — close if RSI has crossed back toward mid AND trade
            # is in profit; otherwise hold through to stop/target/time.
            if t.exit_time is None and params.use_rsi_exit:
                rsi = bar.get("rsi_fast")
                if rsi is not None and not (isinstance(rsi, float) and math.isnan(rsi)):
                    if t.direction == "long" and rsi >= params.rsi_exit_level and close > t.entry_price:
                        _force_close(t, close, ts, "rsi", "win")
                    elif t.direction == "short" and rsi <= params.rsi_exit_level and close < t.entry_price:
                        _force_close(t, close, ts, "rsi", "win")

            # 4) Max duration.
            if t.exit_time is None and (ts - t.entry_time) >= max_dur:
                result = "win" if (
                    (t.direction == "long" and close > t.entry_price)
                    or (t.direction == "short" and close < t.entry_price)
                ) else "loss"
                _force_close(t, close, ts, "time", result)

            if t.exit_time is not None:
                t.pnl_pct = (t.pnl / params.starting_capital) * 100.0
                equity += t.pnl
                trades.append(t)
                open_trade = None

        equity_curve.append({"datetime": ts.isoformat(), "equity": equity})

        if open_trade is not None:
            diag["skipped_open_trade"] += 1
            continue

        # ---- Signal evaluation ----

        # RSI extreme check (cheap, first).
        rsi_fast = bar.get("rsi_fast")
        if rsi_fast is None or (isinstance(rsi_fast, float) and math.isnan(rsi_fast)):
            continue
        long_exhausted = rsi_fast < params.rsi_oversold
        short_exhausted = rsi_fast > params.rsi_overbought
        if not long_exhausted and not short_exhausted:
            continue
        diag["signals_raw"] += 1

        # Day / session filters (use session timezone).
        local_ts = ts.tz_convert(session_tz)
        local_date = local_ts.date()
        hhmm = local_ts.hour + local_ts.minute / 60.0

        if local_date.weekday() not in allowed_days:
            diag["skipped_day_of_week"] += 1
            continue

        # News filter.
        if params.enable_news_filter:
            label = classify_news_day(local_date)
            if label is not None or local_date in custom_skip:
                diag["skipped_news"] += 1
                bucket = label or "custom"
                diag["news_skips_by_type"][bucket] = diag["news_skips_by_type"].get(bucket, 0) + 1
                continue

        if not _session_allowed(hhmm, params):
            diag["skipped_session"] += 1
            continue

        # Trend filter.
        bb_w = bar.get("bb_width")
        adx_v = bar.get("adx")
        if params.use_trend_filter:
            blocked = False
            if params.trend_filter_type in ("bb_width", "both"):
                if bb_w is not None and not (isinstance(bb_w, float) and math.isnan(bb_w)):
                    if bb_w > params.bb_width_max:
                        blocked = True
            if params.trend_filter_type in ("adx", "both") and not blocked:
                if adx_v is not None and not (isinstance(adx_v, float) and math.isnan(adx_v)):
                    if adx_v > params.adx_max:
                        blocked = True
            if blocked:
                diag["skipped_trend_filter"] += 1
                continue

        # Structure-level check.
        close = float(bar["close"])
        candidates = _collect_candidate_levels(bar, params)
        side = "support" if long_exhausted else "resistance"
        nearest = _nearest_level_on_side(close, candidates, side, level_tol)
        if nearest is None:
            diag["skipped_no_level"] += 1
            continue
        if params.require_level_confluence and _count_levels_within(close, candidates, level_tol) < 2:
            diag["skipped_no_confluence"] += 1
            continue

        # Per-day trade cap (keyed by session-local date).
        state = day_states.get(local_date)
        if state is None:
            state = _DayState(day=local_date)
            day_states[local_date] = state
        if state.trades_taken >= int(params.max_trades_per_day):
            diag["skipped_max_trades_per_day"] += 1
            continue

        # Confirmation candle (optional).
        pattern = ""
        if params.require_confirmation_candle:
            cols = bull_conf if long_exhausted else bear_conf
            pattern = _match_pattern(bar, cols) or ""
            if not pattern:
                diag["skipped_no_confirmation"] += 1
                continue

        # ---- Build the trade ----
        direction = "long" if long_exhausted else "short"
        entry_price = close
        if direction == "long":
            stop = entry_price - stop_dist
            target = (
                entry_price + fixed_target_dist
                if params.use_fixed_target
                else entry_price + stop_dist * float(params.rr_ratio)
            )
        else:
            stop = entry_price + stop_dist
            target = (
                entry_price - fixed_target_dist
                if params.use_fixed_target
                else entry_price - stop_dist * float(params.rr_ratio)
            )

        risk = abs(entry_price - stop)
        if risk <= 0:
            continue
        risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
        units = risk_dollars / risk

        open_trade = Trade(
            id=next_id,
            direction=direction,
            entry_time=ts,
            entry_price=entry_price,
            stop=stop,
            target=target,
            risk_per_unit=risk,
            units=units,
            level_type=nearest[0],
            level_price=nearest[1],
            rsi_at_entry=float(rsi_fast),
            bb_width_at_entry=float(bb_w) if bb_w is not None and not (isinstance(bb_w, float) and math.isnan(bb_w)) else 0.0,
            pattern=pattern,
        )
        next_id += 1
        state.trades_taken += 1
        diag["entries"] += 1
        if direction == "long":
            diag["long_entries"] += 1
        else:
            diag["short_entries"] += 1

    # Close any trade left open at the end of data.
    if open_trade is not None and rows:
        last = rows[-1]
        _force_close(open_trade, last["close"], last["datetime"], "eod", "breakeven")
        open_trade.pnl_pct = (open_trade.pnl / params.starting_capital) * 100.0
        equity += open_trade.pnl
        trades.append(open_trade)

    day_state_records = [{"date": str(s.day), "trades_taken": s.trades_taken} for s in day_states.values()]

    return {
        "trades": [t.to_dict() for t in trades],
        "equity_curve": equity_curve,
        "diagnostics": diag,
        "day_states": day_state_records,
    }
