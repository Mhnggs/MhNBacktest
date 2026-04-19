"""Indicator calculations: session-anchored VWAP, EMA, volume ratio, candle patterns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_session_vwap(df: pd.DataFrame, std_bands: tuple[float, ...] = (1.0, 2.0)) -> pd.DataFrame:
    """Add a session-anchored VWAP that resets every trading day.

    VWAP = cumulative(typical_price * volume) / cumulative(volume)
    Bands are computed from the rolling cumulative variance of typical price weighted by volume.
    """
    out = df.copy()
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    volume = out["volume"].replace(0, np.nan).fillna(1.0)
    session = out["datetime"].dt.date

    grouped = pd.DataFrame({
        "session": session,
        "tp": typical,
        "vol": volume,
        "tp_vol": typical * volume,
        "tp2_vol": (typical ** 2) * volume,
    })

    cum_vol = grouped.groupby("session")["vol"].cumsum()
    cum_tp_vol = grouped.groupby("session")["tp_vol"].cumsum()
    cum_tp2_vol = grouped.groupby("session")["tp2_vol"].cumsum()

    vwap = cum_tp_vol / cum_vol
    variance = (cum_tp2_vol / cum_vol) - vwap ** 2
    variance = variance.clip(lower=0.0)
    std = np.sqrt(variance)

    out["vwap"] = vwap.values
    for n in std_bands:
        out[f"vwap_upper_{n}"] = (vwap + n * std).values
        out[f"vwap_lower_{n}"] = (vwap - n * std).values
    return out


def add_ema(df: pd.DataFrame, period: int, column: str = "close", out_col: str | None = None) -> pd.DataFrame:
    """Add an exponential moving average column."""
    out = df.copy()
    name = out_col or f"ema_{period}"
    out[name] = out[column].ewm(span=period, adjust=False).mean()
    return out


def add_ema_slope(df: pd.DataFrame, ema_col: str, lookback: int = 3, out_col: str | None = None) -> pd.DataFrame:
    """Slope of an EMA expressed as percentage change over `lookback` candles."""
    out = df.copy()
    name = out_col or f"{ema_col}_slope"
    out[name] = (out[ema_col] - out[ema_col].shift(lookback)) / out[ema_col].shift(lookback)
    return out


def add_volume_stats(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    out = df.copy()
    out["vol_avg"] = out["volume"].rolling(lookback, min_periods=1).mean()
    out["vol_ratio"] = out["volume"] / out["vol_avg"].replace(0, np.nan)
    out["vol_ratio"] = out["vol_ratio"].fillna(0.0)
    return out


def add_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect common pullback-friendly candle patterns."""
    out = df.copy()
    body = (out["close"] - out["open"]).abs()
    candle_range = (out["high"] - out["low"]).replace(0, np.nan)
    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]

    prev_open = out["open"].shift(1)
    prev_close = out["close"].shift(1)
    prev_body = (prev_close - prev_open).abs()

    bullish = out["close"] > out["open"]
    bearish = out["close"] < out["open"]

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
        (lower_wick >= 2 * body)
        & (upper_wick <= body)
        & (body > 0)
    ).fillna(False)

    out["shooting_star"] = (
        (upper_wick >= 2 * body)
        & (lower_wick <= body)
        & (body > 0)
    ).fillna(False)

    close_position = (out["close"] - out["low"]) / candle_range
    out["strong_bull_close"] = (close_position >= 0.7).fillna(False)
    out["strong_bear_close"] = (close_position <= 0.3).fillna(False)

    out["bullish_pattern"] = (
        out["bullish_engulfing"] | out["hammer"] | out["strong_bull_close"]
    )
    out["bearish_pattern"] = (
        out["bearish_engulfing"] | out["shooting_star"] | out["strong_bear_close"]
    )
    return out


def add_vwap_crossings(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Count VWAP crossings within a rolling window — used for the chop filter."""
    out = df.copy()
    side = np.sign(out["close"] - out["vwap"]).fillna(0)
    crossed = (side != side.shift(1)).astype(int)
    crossed.iloc[0] = 0
    out["vwap_crossings"] = crossed.rolling(window, min_periods=1).sum()
    return out


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ADX, +DI, and -DI columns using Wilder's smoothing.

    Standard Wilder smoothing is an EMA with alpha = 1/period (RMA).
    """
    out = df.copy()
    high = out["high"]
    low = out["low"]
    close = out["close"]
    prev_close = close.shift(1)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.clip(lower=0)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder RMA: alpha = 1/period (use ewm with alpha to match TradingView)
    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    out["plus_di"] = plus_di
    out["minus_di"] = minus_di
    out["adx"] = adx
    return out


def build_indicator_frame(
    df: pd.DataFrame,
    ema_period: int = 9,
    ema_secondary: int = 20,
    ema_slope_lookback: int = 3,
    volume_lookback: int = 20,
    chop_window: int = 10,
    adx_period: int = 14,
) -> pd.DataFrame:
    """One-shot pipeline to attach every indicator the strategy needs."""
    out = add_session_vwap(df)
    out = add_ema(out, ema_period, out_col="ema_fast")
    out = add_ema(out, ema_secondary, out_col="ema_slow")
    out = add_ema_slope(out, "ema_fast", ema_slope_lookback, out_col="ema_fast_slope")
    out = add_volume_stats(out, volume_lookback)
    out = add_candle_patterns(out)
    out = add_vwap_crossings(out, chop_window)
    out = add_adx(out, adx_period)
    return out
