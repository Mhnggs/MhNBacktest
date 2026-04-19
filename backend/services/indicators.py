"""Indicator calculations: EMAs and candlestick patterns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_ema(df: pd.DataFrame, period: int, column: str = "close",
            out_col: str | None = None) -> pd.DataFrame:
    out = df.copy()
    name = out_col or f"ema_{period}"
    out[name] = out[column].ewm(span=period, adjust=False).mean()
    return out


def add_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect candlestick patterns usable as entry triggers.

    Each pattern is emitted as its own boolean column plus aggregate
    ``bullish_patterns`` / ``bearish_patterns`` columns that join the name
    of every pattern that printed on the bar (comma-separated) — the trade
    log uses these to record which pattern fired.
    """
    out = df.copy()
    body = (out["close"] - out["open"]).abs()
    candle_range = (out["high"] - out["low"]).replace(0, np.nan)
    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]

    bullish = out["close"] > out["open"]
    bearish = out["close"] < out["open"]

    prev_open = out["open"].shift(1)
    prev_close = out["close"].shift(1)
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

    # A doji has a very small body relative to the overall range.
    out["doji"] = ((body / candle_range) < 0.1).fillna(False)

    # Piercing line: after a bearish bar, a bullish bar that opens below
    # the prior low and closes above the midpoint of the prior body.
    out["piercing_line"] = (
        bullish
        & (prev_close < prev_open)
        & (out["open"] < out["low"].shift(1))
        & (out["close"] > prev_mid)
        & (out["close"] < prev_open)
    ).fillna(False)

    # Dark cloud cover: after a bullish bar, a bearish bar that opens
    # above the prior high and closes below the midpoint of the prior body.
    out["dark_cloud_cover"] = (
        bearish
        & (prev_close > prev_open)
        & (out["open"] > out["high"].shift(1))
        & (out["close"] < prev_mid)
        & (out["close"] > prev_open)
    ).fillna(False)

    # Marubozu: large solid body with almost no wicks in the trade direction.
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

    return out


def build_indicator_frame(
    df: pd.DataFrame,
    ema_period: int = 9,
    ema_secondary: int = 20,
) -> pd.DataFrame:
    """Attach EMAs and candle pattern columns."""
    out = add_ema(df, ema_period, out_col="ema_fast")
    out = add_ema(out, ema_secondary, out_col="ema_slow")
    out = add_candle_patterns(out)
    return out
