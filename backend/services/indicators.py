"""Indicator calculations for the ICT Silver Bullet strategy.

Per-candle flags/columns computed here:
  - Swing highs/lows (lookback-confirmed)
  - Previous-day high/low and previous-session (London/NY) high/low
  - Displacement flags (bullish/bearish body + close-position check)
  - Fair Value Gap formation at bar i (3-candle pattern: c1=i-2, c2=i-1, c3=i)
  - Kill-zone flags (London SB / NY SB / NY PM SB, in America/New_York)
  - Higher-timeframe bias (resampled to 1H, broadcast to 5m) — "bullish",
    "bearish", or "neutral" per candle.

The strategy runner turns these flags into a stateful setup machine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytz


NY_TZ = "America/New_York"
LONDON_TZ = "Europe/London"


# ---------- Swing detection ----------

def add_swings(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """A swing high requires high > all highs in lookback candles on each side.

    Lookback uses FUTURE candles (N bars after the pivot), so a swing at
    index i is only confirmed at index i+lookback. The strategy runner
    must respect this to avoid look-ahead bias.
    """
    out = df.copy()
    n = len(out)
    high = out["high"].to_numpy()
    low = out["low"].to_numpy()

    is_sh = np.zeros(n, dtype=bool)
    is_sl = np.zeros(n, dtype=bool)
    for i in range(lookback, n - lookback):
        left_h = high[i - lookback : i]
        right_h = high[i + 1 : i + lookback + 1]
        left_l = low[i - lookback : i]
        right_l = low[i + 1 : i + lookback + 1]
        if (left_h < high[i]).all() and (right_h < high[i]).all():
            is_sh[i] = True
        if (left_l > low[i]).all() and (right_l > low[i]).all():
            is_sl[i] = True
    out["is_swing_high"] = is_sh
    out["is_swing_low"] = is_sl
    return out


# ---------- Previous-day / previous-session levels ----------

def add_prev_day_levels(df: pd.DataFrame, tz: str = NY_TZ) -> pd.DataFrame:
    """Previous-day high/low in NY time. Stamped on every bar of a given day."""
    out = df.copy()
    local = out["datetime"].dt.tz_convert(pytz.timezone(tz))
    dates = pd.Series(local.dt.date.values, index=out.index, name="_d")
    by_day = out.groupby(dates)
    day_hi = by_day["high"].max()
    day_lo = by_day["low"].min()
    prev_hi = day_hi.shift(1)
    prev_lo = day_lo.shift(1)
    out["prev_day_high"] = dates.map(prev_hi).values
    out["prev_day_low"] = dates.map(prev_lo).values
    return out


def add_prev_session_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Previous London session (08:00-16:00 London) and previous NY session
    (09:30-16:00 NY) highs/lows. Stamped AFTER the session closes for the
    current local day so subsequent kill zones can reference them.
    """
    out = df.copy()

    london_local = out["datetime"].dt.tz_convert(pytz.timezone(LONDON_TZ))
    ny_local = out["datetime"].dt.tz_convert(pytz.timezone(NY_TZ))

    lon_hhmm = london_local.dt.hour + london_local.dt.minute / 60.0
    ny_hhmm = ny_local.dt.hour + ny_local.dt.minute / 60.0
    lon_date = pd.Series(london_local.dt.date.values, index=out.index)
    ny_date = pd.Series(ny_local.dt.date.values, index=out.index)

    in_london = (lon_hhmm >= 8.0) & (lon_hhmm < 16.0)
    in_ny = (ny_hhmm >= 9.5) & (ny_hhmm < 16.0)

    lon_sub = out.loc[in_london].copy()
    lon_sub["_d"] = lon_date[in_london].values
    lon_hi = lon_sub.groupby("_d")["high"].max().shift(1)
    lon_lo = lon_sub.groupby("_d")["low"].min().shift(1)

    ny_sub = out.loc[in_ny].copy()
    ny_sub["_d"] = ny_date[in_ny].values
    ny_hi = ny_sub.groupby("_d")["high"].max().shift(1)
    ny_lo = ny_sub.groupby("_d")["low"].min().shift(1)

    out["prev_london_high"] = lon_date.map(lon_hi).values
    out["prev_london_low"] = lon_date.map(lon_lo).values
    out["prev_ny_high"] = ny_date.map(ny_hi).values
    out["prev_ny_low"] = ny_date.map(ny_lo).values
    return out


# ---------- Displacement ----------

def add_displacement(
    df: pd.DataFrame,
    min_body_pips: float = 8.0,
    pip_size: float = 0.0001,
    close_pct: float = 0.70,
) -> pd.DataFrame:
    """A displacement bar has a large body that closes in the extreme end of
    its range. Signals are only flagged on the confirming candle.
    """
    out = df.copy()
    body = (out["close"] - out["open"]).abs()
    rng = (out["high"] - out["low"]).replace(0, np.nan)
    min_body = min_body_pips * pip_size

    bull = out["close"] > out["open"]
    bear = out["close"] < out["open"]

    bull_close_pos = (out["close"] - out["low"]) / rng
    bear_close_pos = (out["high"] - out["close"]) / rng

    out["is_bull_disp"] = (bull & (body >= min_body) & (bull_close_pos >= close_pct)).fillna(False)
    out["is_bear_disp"] = (bear & (body >= min_body) & (bear_close_pos >= close_pct)).fillna(False)
    out["body_pips"] = (body / pip_size).fillna(0.0)
    return out


# ---------- Fair Value Gap ----------

def add_fvg(df: pd.DataFrame, pip_size: float = 0.0001, min_size_pips: float = 3.0) -> pd.DataFrame:
    """Bullish FVG at bar i: candle i-1 is a bullish displacement and the
    gap between high[i-2] and low[i] is non-empty. Bearish: mirror.
    Columns are populated only on bar i (the 3rd candle).
    """
    out = df.copy()
    n = len(out)
    high = out["high"].to_numpy()
    low = out["low"].to_numpy()
    bull_disp = out.get("is_bull_disp", pd.Series([False] * n)).to_numpy()
    bear_disp = out.get("is_bear_disp", pd.Series([False] * n)).to_numpy()

    min_size = min_size_pips * pip_size
    bull_top = np.full(n, np.nan)
    bull_bot = np.full(n, np.nan)
    bull_mid = np.full(n, np.nan)
    bear_top = np.full(n, np.nan)
    bear_bot = np.full(n, np.nan)
    bear_mid = np.full(n, np.nan)

    for i in range(2, n):
        if bull_disp[i - 1]:
            gb = high[i - 2]
            gt = low[i]
            if gt - gb >= min_size:
                bull_top[i] = gt
                bull_bot[i] = gb
                bull_mid[i] = (gb + gt) / 2.0
        if bear_disp[i - 1]:
            gb = high[i]
            gt = low[i - 2]
            if gt - gb >= min_size:
                bear_top[i] = gt
                bear_bot[i] = gb
                bear_mid[i] = (gb + gt) / 2.0

    out["fvg_bull_top"] = bull_top
    out["fvg_bull_bot"] = bull_bot
    out["fvg_bull_mid"] = bull_mid
    out["fvg_bear_top"] = bear_top
    out["fvg_bear_bot"] = bear_bot
    out["fvg_bear_mid"] = bear_mid
    out["fvg_bull_size_pips"] = (bull_top - bull_bot) / pip_size
    out["fvg_bear_size_pips"] = (bear_top - bear_bot) / pip_size
    return out


# ---------- Kill zones ----------

def add_kill_zones(df: pd.DataFrame) -> pd.DataFrame:
    """Flag each bar with the active NY-time kill zone (or empty string)."""
    out = df.copy()
    ny_local = out["datetime"].dt.tz_convert(pytz.timezone(NY_TZ))
    h = ny_local.dt.hour + ny_local.dt.minute / 60.0
    out["kz_london"] = (h >= 3.0) & (h < 4.0)
    out["kz_ny"] = (h >= 10.0) & (h < 11.0)
    out["kz_ny_pm"] = (h >= 14.0) & (h < 15.0)
    kz = np.where(
        out["kz_london"], "london",
        np.where(out["kz_ny"], "ny", np.where(out["kz_ny_pm"], "ny_pm", "")),
    )
    out["kill_zone"] = kz
    return out


# ---------- HTF bias ----------

def add_htf_bias(df: pd.DataFrame, lookback_hours: int = 10) -> pd.DataFrame:
    """Resample to 1H, compute bullish/bearish bias from last N hourly bars,
    broadcast back to the 5m grid.

    Bullish: at least 6 of last N hourly bars show higher highs AND at
    least 5 show higher lows. Mirror for bearish. Otherwise neutral.
    """
    out = df.copy()
    work = out.set_index("datetime")[["open", "high", "low", "close"]]
    hourly = work.resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna()

    if hourly.empty:
        out["htf_bias"] = "neutral"
        return out

    hh_flag = (hourly["high"] > hourly["high"].shift(1)).astype(int)
    lh_flag = (hourly["high"] < hourly["high"].shift(1)).astype(int)
    hl_flag = (hourly["low"] > hourly["low"].shift(1)).astype(int)
    ll_flag = (hourly["low"] < hourly["low"].shift(1)).astype(int)

    min_periods = max(3, lookback_hours // 2)
    hh = hh_flag.rolling(lookback_hours, min_periods=min_periods).sum()
    lh = lh_flag.rolling(lookback_hours, min_periods=min_periods).sum()
    hl = hl_flag.rolling(lookback_hours, min_periods=min_periods).sum()
    ll = ll_flag.rolling(lookback_hours, min_periods=min_periods).sum()

    bullish = (hh >= 6) & (hl >= 5)
    bearish = (ll >= 6) & (lh >= 5)
    bias = pd.Series("neutral", index=hourly.index, dtype=object)
    bias[bullish] = "bullish"
    bias[bearish] = "bearish"
    # Convert both sides to naive UTC for the asof merge (pandas requires
    # matching tz-dtypes).
    bias_index_utc = pd.DatetimeIndex(bias.index).tz_convert("UTC").tz_localize(None)
    bias_df = pd.DataFrame({
        "hour_ts": bias_index_utc,
        "htf_bias": bias.values,
    }).sort_values("hour_ts")

    ts_utc_naive = pd.DatetimeIndex(out["datetime"]).tz_convert("UTC").tz_localize(None)
    left = pd.DataFrame({
        "_i": np.arange(len(out)),
        "ts": ts_utc_naive,
    }).sort_values("ts")
    merged = pd.merge_asof(
        left, bias_df,
        left_on="ts", right_on="hour_ts",
        direction="backward",
    )
    merged = merged.sort_values("_i")
    out["htf_bias"] = merged["htf_bias"].fillna("neutral").values
    return out


# ---------- Candle patterns (minimal — optional entry confirmation) ----------

def add_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
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

    out["bullish_engulfing"] = (
        bullish & (prev_close < prev_open) & (body > prev_body)
        & (out["close"] > prev_open) & (out["open"] < prev_close)
    ).fillna(False)
    out["bearish_engulfing"] = (
        bearish & (prev_close > prev_open) & (body > prev_body)
        & (out["close"] < prev_open) & (out["open"] > prev_close)
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
    return out


# ---------- Orchestrator ----------

def build_indicator_frame(
    df: pd.DataFrame,
    pip_size: float = 0.0001,
    swing_lookback: int = 5,
    displacement_body_pips: float = 8.0,
    displacement_close_pct: float = 0.70,
    min_fvg_size_pips: float = 3.0,
    htf_lookback_hours: int = 10,
) -> pd.DataFrame:
    """Attach all Silver Bullet indicators."""
    if not isinstance(df["datetime"].dtype, pd.DatetimeTZDtype):
        raise ValueError("build_indicator_frame requires timezone-aware datetimes")
    out = df
    out = add_swings(out, lookback=swing_lookback)
    out = add_prev_day_levels(out, tz=NY_TZ)
    out = add_prev_session_levels(out)
    out = add_displacement(
        out,
        min_body_pips=displacement_body_pips,
        pip_size=pip_size,
        close_pct=displacement_close_pct,
    )
    out = add_fvg(out, pip_size=pip_size, min_size_pips=min_fvg_size_pips)
    out = add_kill_zones(out)
    out = add_htf_bias(out, lookback_hours=htf_lookback_hours)
    out = add_candle_patterns(out)
    return out
