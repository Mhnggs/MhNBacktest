"""Data loading utilities for MetaTrader CSV files and the TwelveData REST API."""

from __future__ import annotations

import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import pytz
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

REQUIRED_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower().lstrip("<").rstrip(">")
        if key in {"date", "<date>"}:
            rename_map[col] = "date"
        elif key in {"time", "<time>"}:
            rename_map[col] = "time"
        elif key in {"datetime", "timestamp", "date_time"}:
            rename_map[col] = "datetime"
        elif key in {"open", "o"}:
            rename_map[col] = "open"
        elif key in {"high", "h"}:
            rename_map[col] = "high"
        elif key in {"low", "l"}:
            rename_map[col] = "low"
        elif key in {"close", "c"}:
            rename_map[col] = "close"
        elif key in {"volume", "vol", "tickvol", "tick_volume", "v"}:
            rename_map[col] = "volume"
    return df.rename(columns=rename_map)


def _detect_separator(raw: str) -> str:
    head = raw.splitlines()[0] if raw else ""
    if head.count("\t") >= head.count(",") and head.count("\t") > 0:
        return "\t"
    if head.count(";") > head.count(","):
        return ";"
    return ","


def parse_mt_csv(raw_bytes: bytes, source_tz: str = "UTC") -> pd.DataFrame:
    """Parse a MetaTrader-style CSV export into a normalised OHLCV DataFrame.

    `source_tz` should match your MT broker's server time (commonly 'Etc/GMT-3'
    for MT5 brokers on GMT+3 server time). The result is UTC tz-aware.
    """
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    sep = _detect_separator(text)
    df = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
    df = _normalise_columns(df)

    if "datetime" not in df.columns:
        if "date" not in df.columns:
            raise ValueError("CSV missing date or datetime column")
        date_series = df["date"].astype(str).str.replace(".", "-", regex=False)
        if "time" in df.columns:
            time_series = df["time"].astype(str)
            df["datetime"] = pd.to_datetime(
                date_series + " " + time_series, errors="coerce"
            )
        else:
            df["datetime"] = pd.to_datetime(date_series, errors="coerce")
    else:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    if "volume" not in df.columns:
        df["volume"] = 0.0

    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"CSV missing required column: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["datetime", "open", "high", "low", "close"])
    df = df[REQUIRED_COLUMNS].sort_values("datetime").reset_index(drop=True)
    df["volume"] = df["volume"].fillna(0.0)

    tz = pytz.timezone(source_tz)
    df["datetime"] = (
        df["datetime"]
        .dt.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
        .dt.tz_convert("UTC")
    )
    df = df.dropna(subset=["datetime"]).reset_index(drop=True)
    df.attrs["source_tz"] = source_tz
    return df


def merge_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(list(frames), ignore_index=True)
    combined = combined.drop_duplicates(subset=["datetime"]).sort_values("datetime")
    return combined.reset_index(drop=True)


_INTERVAL_MAP = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "1h",
    "4h": "4h",
    "1day": "1day",
}


def _cache_key(symbol: str, interval: str, start: str, end: str) -> Path:
    safe = f"{symbol}_{interval}_{start}_{end}".replace("/", "-").replace(":", "")
    return CACHE_DIR / f"{safe}.csv"


def fetch_twelvedata(
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    api_key: str,
    use_cache: bool = True,
    request_pause: float = 8.0,
) -> pd.DataFrame:
    """Fetch OHLCV data from TwelveData and return a normalised DataFrame."""
    if interval not in _INTERVAL_MAP:
        raise ValueError(
            f"Unsupported interval '{interval}'. Use one of {sorted(_INTERVAL_MAP)}"
        )

    cache_path = _cache_key(symbol, interval, start_date, end_date)
    if use_cache and cache_path.exists():
        cached = pd.read_csv(cache_path)
        cached["datetime"] = pd.to_datetime(cached["datetime"], utc=True)
        return cached

    url = "https://api.twelvedata.com/time_series"
    all_rows: list[dict] = []
    page_start = start_date
    page_size = 5000

    while True:
        params = {
            "symbol": symbol,
            "interval": _INTERVAL_MAP[interval],
            "start_date": page_start,
            "end_date": end_date,
            "apikey": api_key,
            "format": "JSON",
            "outputsize": page_size,
            "order": "asc",
            "timezone": "UTC",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if isinstance(payload, dict) and payload.get("status") == "error":
            raise RuntimeError(f"TwelveData error: {payload.get('message')}")

        values = payload.get("values", []) if isinstance(payload, dict) else []
        if not values:
            break

        all_rows.extend(values)

        last_dt = pd.to_datetime(values[-1]["datetime"])
        if len(values) < page_size or last_dt >= pd.to_datetime(end_date):
            break

        page_start = (last_dt + pd.Timedelta(seconds=1)).isoformat()
        time.sleep(request_pause)

    if not all_rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.DataFrame(all_rows)
    df = df.rename(columns={"datetime": "datetime"})
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    df = df[REQUIRED_COLUMNS]
    df["volume"] = df["volume"].fillna(0.0)
    df.attrs["source_tz"] = "UTC"

    if use_cache:
        df.to_csv(cache_path, index=False)
    return df


def summarise(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows": 0, "start": None, "end": None}
    return {
        "rows": int(len(df)),
        "start": df["datetime"].iloc[0].isoformat(),
        "end": df["datetime"].iloc[-1].isoformat(),
    }
