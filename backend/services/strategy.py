"""VWAP + EMA pullback strategy: signal generation and trade execution."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time as dtime
from typing import Optional

import numpy as np
import pandas as pd
import pytz

from .indicators import build_indicator_frame


@dataclass
class StrategyParams:
    ema_period: int = 9
    ema_secondary: int = 20
    volume_multiplier: float = 1.2
    risk_reward: float = 2.0
    partial_rr: float = 1.5
    use_partial_tp: bool = True
    stop_buffer_ticks: int = 3
    tick_size: float = 0.0001
    max_trades_per_day: int = 3
    session_start: str = "09:45"
    session_end: str = "11:30"
    session_2_start: str = "13:30"
    session_2_end: str = "15:00"
    use_session_2: bool = True
    timezone: str = "America/New_York"
    vwap_max_distance_pct: float = 2.0
    chop_filter_crossings: int = 3
    require_volume: bool = True
    require_pattern: bool = True
    min_ema_slope: float = 0.0001
    ema_touch_pct: float = 0.001  # 0.1%
    starting_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0


@dataclass
class Trade:
    id: int
    direction: str  # 'long' or 'short'
    entry_time: pd.Timestamp
    entry_price: float
    stop: float
    target_1: float
    target_2: float
    risk_per_unit: float
    units: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    result: str = "open"  # win | loss | breakeven | open | timeout
    partial_filled: bool = False
    bars_held: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat()
        d["exit_time"] = self.exit_time.isoformat() if self.exit_time is not None else None
        return d


def _parse_time(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _within_session(ts: pd.Timestamp, params: StrategyParams) -> bool:
    """Check if a timestamp falls within an active trading session."""
    tz = pytz.timezone(params.timezone)
    local = ts.tz_convert(tz) if ts.tzinfo else tz.localize(ts.to_pydatetime())
    t = local.time()

    s1 = _parse_time(params.session_start)
    e1 = _parse_time(params.session_end)
    if s1 <= t <= e1:
        return True

    if params.use_session_2:
        s2 = _parse_time(params.session_2_start)
        e2 = _parse_time(params.session_2_end)
        if s2 <= t <= e2:
            return True
    return False


def _session_end_today(ts: pd.Timestamp, params: StrategyParams) -> pd.Timestamp:
    """Return the last session close for the day of `ts`."""
    tz = pytz.timezone(params.timezone)
    local = ts.tz_convert(tz) if ts.tzinfo else tz.localize(ts.to_pydatetime())
    end_str = params.session_2_end if params.use_session_2 else params.session_end
    eh, em = end_str.split(":")
    end_local = local.replace(hour=int(eh), minute=int(em), second=0, microsecond=0)
    return pd.Timestamp(end_local).tz_convert("UTC") if ts.tzinfo else pd.Timestamp(end_local.replace(tzinfo=None))


def run_backtest(df: pd.DataFrame, params: StrategyParams) -> dict:
    """Run the strategy bar-by-bar and return trades + equity curve."""
    if df.empty:
        return {"trades": [], "equity_curve": [], "signals": []}

    work = df.copy()
    if not isinstance(work["datetime"].dtype, pd.DatetimeTZDtype):
        # Treat naive timestamps as the dataset's source tz (UTC by default).
        # MetaTrader exports often use the broker's local time — see README for that case.
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

    # Auto-disable volume filter if the dataset has no real volume info
    # (common for forex / CFDs returned by TwelveData).
    effective_require_volume = params.require_volume
    if effective_require_volume and float(df["volume"].sum()) <= 0:
        effective_require_volume = False

    work = build_indicator_frame(
        work,
        ema_period=params.ema_period,
        ema_secondary=params.ema_secondary,
    )

    tz = pytz.timezone(params.timezone)
    local_ts = work["datetime"].dt.tz_convert(tz)
    work["_local"] = local_ts
    work["_session_date"] = local_ts.dt.date
    work["_local_time"] = local_ts.dt.time
    work["_in_session"] = work.apply(
        lambda r: _within_session(r["datetime"], params), axis=1
    )

    trades: list[Trade] = []
    equity = params.starting_capital
    equity_curve: list[dict] = []
    open_trade: Optional[Trade] = None
    daily_count: dict = {}
    next_id = 1
    tick = params.tick_size

    diag = {
        "total_bars": 0, "in_session_bars": 0, "candidate_bars": 0,
        "rejected_vwap_side": 0, "rejected_ema_slope": 0,
        "rejected_ema_touch": 0, "rejected_candle_dir": 0,
        "rejected_volume": 0, "rejected_vwap_distance": 0,
        "rejected_chop": 0, "rejected_pattern": 0,
        "rejected_max_per_day": 0, "rejected_open_trade": 0,
        "long_signals": 0, "short_signals": 0,
        "volume_filter_active": effective_require_volume,
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
                hit_stop = low <= t.stop
                hit_t1 = high >= t.target_1
                hit_t2 = high >= t.target_2

                if hit_stop and not (hit_t1 and t.partial_filled):
                    pnl = (t.stop - t.entry_price) * t.units
                    t.exit_price = t.stop
                    t.exit_time = ts
                    t.pnl = pnl
                    t.result = "loss" if pnl < 0 else ("breakeven" if pnl == 0 else "win")
                elif params.use_partial_tp and hit_t1 and not t.partial_filled:
                    partial_pnl = (t.target_1 - t.entry_price) * (t.units * 0.5)
                    t.partial_filled = True
                    t.units *= 0.5
                    t.stop = t.entry_price  # move to breakeven
                    t.pnl += partial_pnl
                    if hit_t2:
                        final_pnl = (t.target_2 - t.entry_price) * t.units
                        t.exit_price = t.target_2
                        t.exit_time = ts
                        t.pnl += final_pnl
                        t.result = "win"
                elif hit_t2:
                    final_pnl = (t.target_2 - t.entry_price) * t.units
                    t.exit_price = t.target_2
                    t.exit_time = ts
                    t.pnl += final_pnl
                    t.result = "win"
            else:  # short
                hit_stop = high >= t.stop
                hit_t1 = low <= t.target_1
                hit_t2 = low <= t.target_2

                if hit_stop and not (hit_t1 and t.partial_filled):
                    pnl = (t.entry_price - t.stop) * t.units
                    t.exit_price = t.stop
                    t.exit_time = ts
                    t.pnl = pnl
                    t.result = "loss" if pnl < 0 else ("breakeven" if pnl == 0 else "win")
                elif params.use_partial_tp and hit_t1 and not t.partial_filled:
                    partial_pnl = (t.entry_price - t.target_1) * (t.units * 0.5)
                    t.partial_filled = True
                    t.units *= 0.5
                    t.stop = t.entry_price
                    t.pnl += partial_pnl
                    if hit_t2:
                        final_pnl = (t.entry_price - t.target_2) * t.units
                        t.exit_price = t.target_2
                        t.exit_time = ts
                        t.pnl += final_pnl
                        t.result = "win"
                elif hit_t2:
                    final_pnl = (t.entry_price - t.target_2) * t.units
                    t.exit_price = t.target_2
                    t.exit_time = ts
                    t.pnl += final_pnl
                    t.result = "win"

            # End-of-session close
            if t.exit_time is None:
                end_today = _session_end_today(ts, params)
                if ts >= end_today:
                    if t.direction == "long":
                        final_pnl = (close - t.entry_price) * t.units
                    else:
                        final_pnl = (t.entry_price - close) * t.units
                    t.exit_price = close
                    t.exit_time = ts
                    t.pnl += final_pnl
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
        if daily_count.get(session_date, 0) >= params.max_trades_per_day:
            diag["rejected_max_per_day"] += 1
            continue
        if pd.isna(bar.get("ema_fast")) or pd.isna(bar.get("vwap")):
            continue
        diag["candidate_bars"] += 1

        slope = bar.get("ema_fast_slope")
        slope_ok_long = slope is not None and not pd.isna(slope) and slope > params.min_ema_slope
        slope_ok_short = slope is not None and not pd.isna(slope) and slope < -params.min_ema_slope

        long_checks = {
            "vwap_side": bar["close"] > bar["vwap"],
            "ema_slope": slope_ok_long,
            "ema_touch": prev["low"] <= bar["ema_fast"] * (1 + params.ema_touch_pct),
            "candle_dir": bar["close"] > bar["open"],
            "volume": (not effective_require_volume) or bar["vol_ratio"] >= params.volume_multiplier,
            "vwap_distance": (bar["close"] - bar["vwap"]) / bar["vwap"] * 100 <= params.vwap_max_distance_pct,
            "chop": bar["vwap_crossings"] <= params.chop_filter_crossings,
            "pattern": (not params.require_pattern) or bool(bar["bullish_pattern"]),
        }
        short_checks = {
            "vwap_side": bar["close"] < bar["vwap"],
            "ema_slope": slope_ok_short,
            "ema_touch": prev["high"] >= bar["ema_fast"] * (1 - params.ema_touch_pct),
            "candle_dir": bar["close"] < bar["open"],
            "volume": (not effective_require_volume) or bar["vol_ratio"] >= params.volume_multiplier,
            "vwap_distance": (bar["vwap"] - bar["close"]) / bar["vwap"] * 100 <= params.vwap_max_distance_pct,
            "chop": bar["vwap_crossings"] <= params.chop_filter_crossings,
            "pattern": (not params.require_pattern) or bool(bar["bearish_pattern"]),
        }

        long_cond = all(long_checks.values())
        short_cond = all(short_checks.values())

        # Track which filter most often blocks signals (only count when not in trade)
        if not long_cond and not short_cond:
            for name, ok in long_checks.items():
                if not ok:
                    diag[f"rejected_{name if name != 'vwap_side' else 'vwap_side'}"] = (
                        diag.get(f"rejected_{name}", 0)
                    )
            # Use whichever side had the most filters passing as the "intended" direction
            long_pass = sum(long_checks.values())
            short_pass = sum(short_checks.values())
            checks = long_checks if long_pass >= short_pass else short_checks
            for name, ok in checks.items():
                if not ok:
                    key = f"rejected_{name}"
                    diag[key] = diag.get(key, 0) + 1
                    break  # only count the first failing filter per bar

        if long_cond:
            diag["long_signals"] += 1
            entry = bar["high"] + tick
            stop = bar["low"] - params.stop_buffer_ticks * tick
            risk_per_unit = entry - stop
            if risk_per_unit <= 0:
                continue
            risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
            units = risk_dollars / risk_per_unit
            target_1 = entry + risk_per_unit * params.partial_rr
            target_2 = entry + risk_per_unit * params.risk_reward
            open_trade = Trade(
                id=next_id, direction="long", entry_time=ts, entry_price=entry,
                stop=stop, target_1=target_1, target_2=target_2,
                risk_per_unit=risk_per_unit, units=units,
            )
            next_id += 1
            daily_count[session_date] = daily_count.get(session_date, 0) + 1

        elif short_cond:
            diag["short_signals"] += 1
            entry = bar["low"] - tick
            stop = bar["high"] + params.stop_buffer_ticks * tick
            risk_per_unit = stop - entry
            if risk_per_unit <= 0:
                continue
            risk_dollars = equity * (params.risk_per_trade_pct / 100.0)
            units = risk_dollars / risk_per_unit
            target_1 = entry - risk_per_unit * params.partial_rr
            target_2 = entry - risk_per_unit * params.risk_reward
            open_trade = Trade(
                id=next_id, direction="short", entry_time=ts, entry_price=entry,
                stop=stop, target_1=target_1, target_2=target_2,
                risk_per_unit=risk_per_unit, units=units,
            )
            next_id += 1
            daily_count[session_date] = daily_count.get(session_date, 0) + 1

    return {
        "trades": [t.to_dict() for t in trades],
        "equity_curve": equity_curve,
        "diagnostics": diag,
    }
