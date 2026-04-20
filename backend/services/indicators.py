"""Indicator calculations: DR range levels + candlestick patterns."""

from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytz


def _parse_time(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def add_dr_levels(
    df: pd.DataFrame,
    dr_start: str = "09:30",
    dr_end: str = "10:30",
    dr_tz: str = "America/New_York",
) -> pd.DataFrame:
    """Attach per-day DR high/low/range/midpoint plus dr_period / post_dr flags.

    The DR (Defining Range) is the high/low between ``dr_start`` and
    ``dr_end`` in ``dr_tz`` each day. Every bar of the day receives that
    day's DR levels as columns so downstream code can read them without
    re-computing. Bars before 09:30 NY get NaN DR levels.
    """
    out = df.copy()
    if not isinstance(out["datetime"].dtype, pd.DatetimeTZDtype):
        raise ValueError("add_dr_levels requires timezone-aware datetimes (UTC expected)")

    tz = pytz.timezone(dr_tz)
    local = out["datetime"].dt.tz_convert(tz)
    out["_dr_date"] = local.dt.date
    out["_dr_hhmm"] = local.dt.hour + local.dt.minute / 60.0

    start_t = _parse_time(dr_start)
    end_t = _parse_time(dr_end)
    start_hhmm = start_t.hour + start_t.minute / 60.0
    end_hhmm = end_t.hour + end_t.minute / 60.0

    out["dr_period"] = (out["_dr_hhmm"] >= start_hhmm) & (out["_dr_hhmm"] < end_hhmm)
    out["post_dr"] = out["_dr_hhmm"] >= end_hhmm

    # Compute per-day DR high/low over the DR window.
    dr_window = out[out["dr_period"]]
    daily = dr_window.groupby("_dr_date").agg(
        dr_high=("high", "max"),
        dr_low=("low", "min"),
    )
    daily["dr_range"] = daily["dr_high"] - daily["dr_low"]
    daily["dr_midpoint"] = (daily["dr_high"] + daily["dr_low"]) / 2.0
    daily["dr_upper_quarter"] = daily["dr_low"] + daily["dr_range"] * 0.75
    daily["dr_lower_quarter"] = daily["dr_low"] + daily["dr_range"] * 0.25

    out = out.merge(daily, how="left", left_on="_dr_date", right_index=True)

    # Housekeep helper columns — keep _dr_date because strategy groups by it.
    out = out.drop(columns=["_dr_hhmm"])
    return out


def add_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect candlestick patterns usable as entry confirmation triggers."""
    out = df.copy()
    body = (out["close"] - out["open"]).abs()
    candle_range = (out["high"] - out["low"]).replace(0, np.nan)
    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]

    bullish = out["close"] > out["open"]
    bearish = out["close"] < out["open"]

    prev_open = out["open"].shift(1)
    prev_close = out["close"].shift(1)
    prev_high = out["high"].shift(1)
    prev_low = out["low"].shift(1)
    prev_body = (prev_close - prev_open).abs()
    prev_mid = (prev_open + prev_close) / 2.0

    out["bullish_engulfing"] = (
        bullish
        & (prev_close < prev_open)
        & (body > prev_body)
        & (out["close"] > prev_open)
        & (out["open"] < prev_close)
    ).fillna(False)

    out["bearish_engulfing"] = (
        bearish
        & (prev_close > prev_open)
        & (body > prev_body)
        & (out["close"] < prev_open)
        & (out["open"] > prev_close)
    ).fillna(False)

    out["hammer"] = (
        bullish
        & (lower_wick >= 2 * body)
        & (upper_wick <= body)
        & (body > 0)
    ).fillna(False)

    out["shooting_star"] = (
        bearish
        & (upper_wick >= 2 * body)
        & (lower_wick <= body)
        & (body > 0)
    ).fillna(False)

    out["doji"] = ((body / candle_range) < 0.1).fillna(False)

    out["piercing_line"] = (
        bullish
        & (prev_close < prev_open)
        & (out["open"] < out["low"].shift(1))
        & (out["close"] > prev_mid)
        & (out["close"] < prev_open)
    ).fillna(False)

    out["dark_cloud_cover"] = (
        bearish
        & (prev_close > prev_open)
        & (out["open"] > out["high"].shift(1))
        & (out["close"] < prev_mid)
        & (out["close"] > prev_open)
    ).fillna(False)

    body_ratio = (body / candle_range).fillna(0.0)
    out["bullish_marubozu"] = (
        bullish
        & (body_ratio >= 0.8)
        & ((upper_wick / candle_range).fillna(0.0) <= 0.1)
    ).fillna(False)
    out["bearish_marubozu"] = (
        bearish
        & (body_ratio >= 0.8)
        & ((lower_wick / candle_range).fillna(0.0) <= 0.1)
    ).fillna(False)

    # Inside bar: current bar entirely within previous bar's range.
    # Direction-agnostic — usable both ways.
    inside = (out["high"] < prev_high) & (out["low"] > prev_low)
    out["inside_bar_bull"] = inside.fillna(False)
    out["inside_bar_bear"] = inside.fillna(False)

    return out


def build_indicator_frame(
    df: pd.DataFrame,
    dr_start: str = "09:30",
    dr_end: str = "10:30",
    dr_tz: str = "America/New_York",
) -> pd.DataFrame:
    """Attach DR levels + candlestick pattern columns."""
    out = add_dr_levels(df, dr_start=dr_start, dr_end=dr_end, dr_tz=dr_tz)
    out = add_candle_patterns(out)
    return out
