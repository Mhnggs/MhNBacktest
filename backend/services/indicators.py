"""Indicator calculations for the RSI Exhaustion Mean Reversion strategy.

Adds: RSI (Wilder, 3 periods), Bollinger Bands + width, ADX, daily-reset
VWAP + standard-deviation bands, previous-day high/low/open/close, daily open,
weekly open, London session high/low, plus candlestick pattern flags used for
optional confirmation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytz


def _wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Standard RSI using Wilder's smoothing (EMA with alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is zero and there has been any gain, RSI is 100.
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)
    # When both are zero (flat), RSI is 50.
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return rsi


def add_rsi(df: pd.DataFrame, fast: int = 2, medium: int = 3, slow: int = 14) -> pd.DataFrame:
    out = df.copy()
    out["rsi_fast"] = _wilder_rsi(out["close"], fast)
    out["rsi_medium"] = _wilder_rsi(out["close"], medium)
    out["rsi_slow"] = _wilder_rsi(out["close"], slow)
    return out


def add_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    out = df.copy()
    mid = out["close"].rolling(period, min_periods=period).mean()
    sd = out["close"].rolling(period, min_periods=period).std(ddof=0)
    out["bb_middle"] = mid
    out["bb_upper"] = mid + std * sd
    out["bb_lower"] = mid - std * sd
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_middle"].replace(0, np.nan)
    return out


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Wilder's ADX."""
    out = df.copy()
    high, low, close = out["high"], out["low"], out["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["adx"] = dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return out


def add_vwap_bands(df: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Daily-reset VWAP with ±1σ / ±2σ bands (volume-weighted typical price)."""
    out = df.copy()
    if not isinstance(out["datetime"].dtype, pd.DatetimeTZDtype):
        raise ValueError("add_vwap_bands requires timezone-aware datetimes")
    local = out["datetime"].dt.tz_convert(pytz.timezone(tz))
    dates = local.dt.date.values

    tp = ((out["high"] + out["low"] + out["close"]) / 3.0).to_numpy()
    v = out["volume"].fillna(1.0).to_numpy()
    pv = tp * v

    vwap = np.zeros(len(out))
    sd = np.zeros(len(out))

    current = None
    cum_pv = cum_v = cum_dev2 = 0.0
    for i in range(len(out)):
        d = dates[i]
        if d != current:
            current = d
            cum_pv = cum_v = cum_dev2 = 0.0
        cum_pv += pv[i]
        cum_v += v[i]
        vw = cum_pv / cum_v if cum_v > 0 else tp[i]
        vwap[i] = vw
        cum_dev2 += (tp[i] - vw) ** 2 * v[i]
        sd[i] = np.sqrt(cum_dev2 / cum_v) if cum_v > 0 else 0.0

    out["vwap"] = vwap
    out["vwap_sd"] = sd
    out["vwap_upper_1"] = vwap + sd
    out["vwap_upper_2"] = vwap + 2.0 * sd
    out["vwap_lower_1"] = vwap - sd
    out["vwap_lower_2"] = vwap - 2.0 * sd
    return out


def add_prev_day_levels(df: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
    """Attach previous-day high/low/open/close and today's daily/weekly open."""
    out = df.copy()
    local = out["datetime"].dt.tz_convert(pytz.timezone(tz))
    dates = pd.Series(local.dt.date.values, index=out.index, name="_d")

    by_day = out.groupby(dates)
    day_hi = by_day["high"].max()
    day_lo = by_day["low"].min()
    day_op = by_day["open"].first()
    day_cl = by_day["close"].last()

    day_hi.index.name = "_d"
    prev_hi = day_hi.shift(1)
    prev_lo = day_lo.shift(1)
    prev_op = day_op.shift(1)
    prev_cl = day_cl.shift(1)

    out["daily_open"] = dates.map(day_op).values
    out["prev_day_high"] = dates.map(prev_hi).values
    out["prev_day_low"] = dates.map(prev_lo).values
    out["prev_day_open"] = dates.map(prev_op).values
    out["prev_day_close"] = dates.map(prev_cl).values

    # Weekly open: first bar's open per ISO-week year/week.
    iso = local.dt.isocalendar()
    week_key = iso["year"].astype(str) + "-" + iso["week"].astype(str)
    week_series = pd.Series(week_key.values, index=out.index, name="_w")
    week_open = out.groupby(week_series)["open"].transform("first")
    out["weekly_open"] = week_open.values
    return out


def add_london_session_levels(df: pd.DataFrame) -> pd.DataFrame:
    """London session high/low (08:00-16:00 Europe/London). Populated AFTER
    16:00 London for the rest of that local day so NY session can reference it.
    """
    out = df.copy()
    london = out["datetime"].dt.tz_convert(pytz.timezone("Europe/London"))
    out["_lon_date"] = london.dt.date.values
    out["_lon_hhmm"] = (london.dt.hour + london.dt.minute / 60.0).values

    in_london = (out["_lon_hhmm"] >= 8.0) & (out["_lon_hhmm"] < 16.0)
    # High/low per London-date restricted to in-session bars.
    session_df = out[in_london]
    session_hi = session_df.groupby("_lon_date")["high"].max()
    session_lo = session_df.groupby("_lon_date")["low"].min()

    out["london_high"] = out["_lon_date"].map(session_hi)
    out["london_low"] = out["_lon_date"].map(session_lo)
    # Mask before 16:00 London so intra-session partial values aren't used.
    after_session = out["_lon_hhmm"] >= 16.0
    out.loc[~after_session, "london_high"] = np.nan
    out.loc[~after_session, "london_low"] = np.nan
    out = out.drop(columns=["_lon_date", "_lon_hhmm"])
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
        bullish & (prev_close < prev_open) & (body > prev_body)
        & (out["close"] > prev_open) & (out["open"] < prev_close)
    ).fillna(False)
    out["bearish_engulfing"] = (
        bearish & (prev_close > prev_open) & (body > prev_body)
        & (out["close"] < prev_open) & (out["open"] > prev_close)
    ).fillna(False)
    out["hammer"] = (
        bullish & (lower_wick >= 2 * body) & (upper_wick <= body) & (body > 0)
    ).fillna(False)
    out["shooting_star"] = (
        bearish & (upper_wick >= 2 * body) & (lower_wick <= body) & (body > 0)
    ).fillna(False)
    out["doji"] = ((body / candle_range) < 0.1).fillna(False)
    out["piercing_line"] = (
        bullish & (prev_close < prev_open)
        & (out["open"] < out["low"].shift(1))
        & (out["close"] > prev_mid) & (out["close"] < prev_open)
    ).fillna(False)
    out["dark_cloud_cover"] = (
        bearish & (prev_close > prev_open)
        & (out["open"] > out["high"].shift(1))
        & (out["close"] < prev_mid) & (out["close"] > prev_open)
    ).fillna(False)
    body_ratio = (body / candle_range).fillna(0.0)
    out["bullish_marubozu"] = (
        bullish & (body_ratio >= 0.8)
        & ((upper_wick / candle_range).fillna(0.0) <= 0.1)
    ).fillna(False)
    out["bearish_marubozu"] = (
        bearish & (body_ratio >= 0.8)
        & ((lower_wick / candle_range).fillna(0.0) <= 0.1)
    ).fillna(False)
    inside = (out["high"] < prev_high) & (out["low"] > prev_low)
    out["inside_bar_bull"] = inside.fillna(False)
    out["inside_bar_bear"] = inside.fillna(False)
    return out


def build_indicator_frame(
    df: pd.DataFrame,
    rsi_fast: int = 2,
    rsi_medium: int = 3,
    rsi_slow: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
    adx_period: int = 14,
    vwap_tz: str = "America/New_York",
) -> pd.DataFrame:
    """Attach all indicators used by the RSI Mean-Reversion strategy."""
    out = add_rsi(df, fast=rsi_fast, medium=rsi_medium, slow=rsi_slow)
    out = add_bollinger(out, period=bb_period, std=bb_std)
    out = add_adx(out, period=adx_period)
    out = add_vwap_bands(out, tz=vwap_tz)
    out = add_prev_day_levels(out, tz=vwap_tz)
    out = add_london_session_levels(out)
    out = add_candle_patterns(out)
    return out
