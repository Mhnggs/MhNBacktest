"""ICT Silver Bullet strategy: liquidity sweep → displacement → FVG → MSS entry.

Per-candle state machine inside each kill zone:
  1. Update active liquidity pools (EQH/EQL + prev-day + prev-session).
  2. Detect a liquidity sweep against those pools.
  3. Wait for a displacement bar (within displacement_search_bars of sweep).
  4. Wait for an FVG to form (same direction as sweep).
  5. (Optional) Wait for a Market Structure Shift.
  6. (Optional) Check higher-timeframe bias alignment.
  7. Enter when price trades into the FVG (limit at midpoint).
  8. Manage the trade (partial TP at 1R, final at rr_ratio × R, stop).
  9. Close at end of kill zone if `close_at_killzone_end` is on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pytz

from .indicators import build_indicator_frame, NY_TZ
from .news_calendar import is_news_day, parse_custom_skip_dates


DISPLACEMENT_SEARCH_BARS = 10     # sweep → displacement must be within this many bars
FVG_SEARCH_BARS = 6               # displacement → FVG within this many bars
MSS_SEARCH_BARS = 12              # FVG → MSS within this many bars
FVG_ENTRY_WINDOW_BARS = 20        # FVG valid for this many bars after formation


LEVEL_TYPE_LABELS = {
    "EQH": "Equal Highs",
    "EQL": "Equal Lows",
    "prev_day_high": "Prev Day High",
    "prev_day_low": "Prev Day Low",
    "prev_london_high": "Prev London High",
    "prev_london_low": "Prev London Low",
    "prev_ny_high": "Prev NY High",
    "prev_ny_low": "Prev NY Low",
}

# High-quality sweep categories (for confluence scoring).
PREV_SESSION_LEVEL_TYPES = {
    "prev_day_high", "prev_day_low",
    "prev_london_high", "prev_london_low",
    "prev_ny_high", "prev_ny_low",
}


# ----------------------- params -----------------------

@dataclass
class StrategyParams:
    # Instrument / sizing
    pip_size: float = 0.0001
    starting_capital: float = 10_000.0
    risk_per_trade_pct: float = 1.0

    # Kill zones
    enable_london_sb: bool = True
    enable_ny_sb: bool = True
    enable_ny_pm_sb: bool = False

    # Liquidity detection
    swing_lookback: int = 5
    equal_level_tolerance_pips: float = 3.0
    min_sweep_pips: float = 3.0
    sweep_confirmation_candles: int = 3

    # Displacement
    displacement_body_pips: float = 8.0
    displacement_close_pct: float = 0.70

    # FVG
    min_fvg_size_pips: float = 3.0
    fvg_max_age_candles: int = 20
    fvg_entry_type: str = "50% midpoint"   # or "FVG touch", "FVG close"

    # MSS
    require_mss: bool = True

    # Order block
    require_ob_confluence: bool = False

    # HTF bias
    require_htf_alignment: bool = True
    htf_neutral_action: str = "Skip trade"  # or "Allow both"

    # Risk / exits
    stop_type: str = "Beyond sweep"        # "Beyond sweep" | "Beyond FVG" | "Fixed pips"
    stop_buffer_pips: float = 3.0
    fixed_stop_pips: float = 10.0
    rr_ratio: float = 2.0
    use_partial_tp: bool = True
    max_trades_per_killzone: int = 1
    max_trades_per_day: int = 2
    close_at_killzone_end: bool = True

    # Confluence
    min_confluence_score: int = 5

    # Filters
    enable_news_filter: bool = True
    custom_skip_dates: list[str] = field(default_factory=list)
    allowed_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    min_fvg_to_stop_ratio: float = 0.5
    spread_pips: float = 0.2

    # Circuit breakers
    enable_daily_circuit_breaker: bool = True
    daily_loss_limit_pct: float = 2.0
    enable_weekly_circuit_breaker: bool = True
    weekly_loss_limit_pct: float = 5.0


# ----------------------- state -----------------------

@dataclass
class LiquidityLevel:
    level_type: str
    price: float
    source_bar: int
    active_since_bar: int
    swept: bool = False
    swept_at_bar: int = -1


@dataclass
class ActiveFVG:
    direction: str                  # "bull" / "bear"
    top: float
    bot: float
    mid: float
    formed_at_bar: int
    mitigated: bool = False


@dataclass
class SetupState:
    """State machine for one sweep→entry sequence inside a kill zone."""
    kill_zone: str = ""
    sweep_bar: int = -1
    sweep_type: str = ""            # "bullish" | "bearish"
    sweep_level_type: str = ""
    sweep_level_price: float = 0.0
    sweep_wick_extreme: float = 0.0  # the wick that swept (for stop)
    displacement_bar: int = -1
    fvg: Optional[ActiveFVG] = None
    mss_confirmed: bool = False


@dataclass
class OpenTrade:
    id: int
    direction: str
    entry_time: pd.Timestamp
    entry_bar: int
    entry_price: float
    size: float
    stop: float
    target1: float
    target2: float
    partial_filled: bool = False
    partial_pnl: float = 0.0
    open_size: float = 0.0
    kill_zone: str = ""
    # Diagnostics
    confluence_score: int = 0
    confluence_breakdown: dict = field(default_factory=dict)
    sweep_level_type: str = ""
    sweep_level_price: float = 0.0
    fvg_top: float = 0.0
    fvg_bot: float = 0.0
    fvg_mid: float = 0.0
    fvg_size_pips: float = 0.0
    htf_bias_at_entry: str = ""
    mss_confirmed: bool = False


# ----------------------- helpers -----------------------

def _to_ny(ts: pd.Timestamp) -> datetime:
    tz = pytz.timezone(NY_TZ)
    return ts.to_pydatetime().astimezone(tz)


def _pip(params: StrategyParams, pips: float) -> float:
    return pips * params.pip_size


def _killzone_for_bar(row: pd.Series, params: StrategyParams) -> str:
    kz = row.get("kill_zone", "") or ""
    if kz == "london" and not params.enable_london_sb:
        return ""
    if kz == "ny" and not params.enable_ny_sb:
        return ""
    if kz == "ny_pm" and not params.enable_ny_pm_sb:
        return ""
    return kz


def _detect_equal_levels(
    swings: list[tuple[int, float]],
    new_bar: int,
    new_price: float,
    tolerance: float,
) -> Optional[tuple[int, float]]:
    """Return the matched earlier swing (bar, price) if within tolerance."""
    for bar, px in reversed(swings):
        if abs(px - new_price) <= tolerance:
            return (bar, px)
    return None


def _maybe_activate_prev_session_levels(
    row: pd.Series,
    bar_idx: int,
    active_levels: list[LiquidityLevel],
    activated_keys: set[tuple[str, float, object]],
) -> None:
    """Add prev-day / prev-session levels from the current row if not yet added today."""
    ny_date = row["datetime"].tz_convert(NY_TZ).date()
    for lt in ("prev_day_high", "prev_day_low",
               "prev_london_high", "prev_london_low",
               "prev_ny_high", "prev_ny_low"):
        px = row.get(lt)
        if px is None or pd.isna(px):
            continue
        key = (lt, float(px), ny_date)
        if key in activated_keys:
            continue
        activated_keys.add(key)
        active_levels.append(LiquidityLevel(
            level_type=lt, price=float(px),
            source_bar=bar_idx, active_since_bar=bar_idx,
        ))


def _check_sweep(
    candle: pd.Series, level: LiquidityLevel, params: StrategyParams,
) -> Optional[dict]:
    """Single-candle sweep: wick beyond level by min_sweep_pips AND close back."""
    buf = _pip(params, params.min_sweep_pips)
    is_bsl = level.level_type in ("EQH", "prev_day_high", "prev_london_high", "prev_ny_high")
    is_ssl = level.level_type in ("EQL", "prev_day_low", "prev_london_low", "prev_ny_low")
    if is_bsl and candle["high"] > level.price + buf and candle["close"] < level.price:
        return {"type": "bearish", "wick_extreme": candle["high"]}
    if is_ssl and candle["low"] < level.price - buf and candle["close"] > level.price:
        return {"type": "bullish", "wick_extreme": candle["low"]}
    return None


def _find_order_block(
    candles: pd.DataFrame, displacement_bar: int, direction: str, max_back: int = 10,
) -> Optional[dict]:
    """Last opposing candle before the displacement bar."""
    for j in range(displacement_bar - 1, max(displacement_bar - max_back, -1), -1):
        c = candles.iloc[j]
        if direction == "bull" and c["close"] < c["open"]:
            return {"high": float(c["high"]), "low": float(c["low"]), "bar": j}
        if direction == "bear" and c["close"] > c["open"]:
            return {"high": float(c["high"]), "low": float(c["low"]), "bar": j}
    return None


def _daily_key(ts: pd.Timestamp) -> str:
    return ts.tz_convert(NY_TZ).strftime("%Y-%m-%d")


def _week_key(ts: pd.Timestamp) -> str:
    ny = ts.tz_convert(NY_TZ)
    iso = ny.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ----------------------- main runner -----------------------

def run_backtest(df: pd.DataFrame, params: StrategyParams) -> dict:
    ind = build_indicator_frame(
        df,
        pip_size=params.pip_size,
        swing_lookback=params.swing_lookback,
        displacement_body_pips=params.displacement_body_pips,
        displacement_close_pct=params.displacement_close_pct,
        min_fvg_size_pips=params.min_fvg_size_pips,
    )
    n = len(ind)

    # Per-bar arrays for speed.
    ts = ind["datetime"].to_numpy()
    op = ind["open"].to_numpy(); hi = ind["high"].to_numpy()
    lo = ind["low"].to_numpy();  cl = ind["close"].to_numpy()
    is_sh = ind["is_swing_high"].to_numpy()
    is_sl = ind["is_swing_low"].to_numpy()
    kz_arr = ind["kill_zone"].to_numpy()
    htf_arr = ind["htf_bias"].to_numpy()

    # Stateful holders.
    active_levels: list[LiquidityLevel] = []
    activated_keys: set[tuple[str, float, object]] = set()
    recent_highs: list[tuple[int, float]] = []   # confirmed swing highs (bar, price)
    recent_lows: list[tuple[int, float]] = []
    active_fvgs: list[ActiveFVG] = []

    setup: Optional[SetupState] = None
    current_killzone: str = ""
    kz_trade_count: int = 0

    open_trade: Optional[OpenTrade] = None
    trades: list[dict] = []
    equity = params.starting_capital
    equity_curve: list[dict] = [{"datetime": str(ind.iloc[0]["datetime"]), "equity": equity}]

    daily_pnl: dict[str, float] = {}
    daily_trades: dict[str, int] = {}
    weekly_pnl: dict[str, float] = {}
    next_trade_id = 1
    tol = _pip(params, params.equal_level_tolerance_pips)
    news_skip_dates = parse_custom_skip_dates(params.custom_skip_dates)

    # Diagnostics counters.
    diag = {
        "bars_total": n,
        "bars_in_killzone": 0,
        "sweeps_detected": 0,
        "displacements_after_sweep": 0,
        "fvgs_after_displacement": 0,
        "mss_confirmations": 0,
        "htf_aligned_passes": 0,
        "entries_attempted": 0,
        "entries_taken": 0,
        "skipped_daily_limit": 0,
        "skipped_killzone_limit": 0,
        "skipped_news": 0,
        "skipped_low_confluence": 0,
        "skipped_fvg_mitigated": 0,
        "skipped_r_ratio": 0,
        "skipped_open_trade": 0,
        "skipped_wrong_day": 0,
        "skipped_circuit_breaker": 0,
    }

    def _close_trade(trade: OpenTrade, exit_bar: int, exit_price: float, reason: str):
        nonlocal equity, open_trade
        exit_t = ind.iloc[exit_bar]["datetime"]
        spread_cost = params.spread_pips * params.pip_size * trade.open_size
        if trade.direction == "long":
            final_pnl = (exit_price - trade.entry_price) * trade.open_size
        else:
            final_pnl = (trade.entry_price - exit_price) * trade.open_size
        final_pnl -= spread_cost
        total_pnl = trade.partial_pnl + final_pnl
        equity += final_pnl
        result = "win" if total_pnl > 0 else "loss" if total_pnl < 0 else "breakeven"
        dk = _daily_key(exit_t)
        wk = _week_key(exit_t)
        daily_pnl[dk] = daily_pnl.get(dk, 0.0) + final_pnl + trade.partial_pnl if not trade.partial_filled else daily_pnl.get(dk, 0.0) + final_pnl
        weekly_pnl[wk] = weekly_pnl.get(wk, 0.0) + final_pnl
        trades.append({
            "id": trade.id,
            "entry_time": str(trade.entry_time),
            "exit_time": str(exit_t),
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "exit_price": exit_price,
            "stop": trade.stop,
            "target1": trade.target1,
            "target2": trade.target2,
            "size": trade.size,
            "pnl": total_pnl,
            "result": result,
            "exit_reason": reason,
            "kill_zone": trade.kill_zone,
            "confluence_score": trade.confluence_score,
            "confluence_breakdown": trade.confluence_breakdown,
            "sweep_level_type": trade.sweep_level_type,
            "sweep_level_price": trade.sweep_level_price,
            "fvg_top": trade.fvg_top,
            "fvg_bot": trade.fvg_bot,
            "fvg_mid": trade.fvg_mid,
            "fvg_size_pips": trade.fvg_size_pips,
            "htf_bias": trade.htf_bias_at_entry,
            "mss_confirmed": trade.mss_confirmed,
        })
        equity_curve.append({"datetime": str(exit_t), "equity": equity})
        open_trade = None

    def _manage_open(i: int):
        """Apply stop/TP/kill-zone-end exits to the open trade in bar order."""
        nonlocal equity, open_trade
        if open_trade is None:
            return
        t = open_trade
        bar_hi = hi[i]; bar_lo = lo[i]
        # Partial TP at target1 (optional).
        if params.use_partial_tp and not t.partial_filled:
            hit_t1 = (t.direction == "long" and bar_hi >= t.target1) or \
                     (t.direction == "short" and bar_lo <= t.target1)
            if hit_t1:
                half = t.size / 2.0
                if t.direction == "long":
                    partial = (t.target1 - t.entry_price) * half
                else:
                    partial = (t.entry_price - t.target1) * half
                t.partial_pnl = partial
                equity += partial
                t.partial_filled = True
                t.open_size = t.size - half
                t.stop = t.entry_price        # move stop to breakeven
                equity_curve.append({"datetime": str(ind.iloc[i]["datetime"]), "equity": equity})
        # Stop hit.
        stop_hit = (t.direction == "long" and bar_lo <= t.stop) or \
                   (t.direction == "short" and bar_hi >= t.stop)
        target_hit = (t.direction == "long" and bar_hi >= t.target2) or \
                     (t.direction == "short" and bar_lo <= t.target2)
        if stop_hit and target_hit:
            # Pessimistic: stop wins in the same bar.
            _close_trade(t, i, t.stop, "stop")
            return
        if stop_hit:
            _close_trade(t, i, t.stop, "stop")
            return
        if target_hit:
            _close_trade(t, i, t.target2, "target")
            return

    # -------- main loop --------
    for i in range(n):
        row = ind.iloc[i]
        t_now = row["datetime"]

        # --- 1. Register newly-confirmed swings (bar i - lookback). ---
        conf_bar = i - params.swing_lookback
        if conf_bar >= 0:
            if is_sh[conf_bar]:
                price = float(hi[conf_bar])
                match = _detect_equal_levels(recent_highs, conf_bar, price, tol)
                if match is not None:
                    active_levels.append(LiquidityLevel(
                        level_type="EQH", price=price,
                        source_bar=conf_bar, active_since_bar=i,
                    ))
                recent_highs.append((conf_bar, price))
                if len(recent_highs) > 200:
                    recent_highs.pop(0)
            if is_sl[conf_bar]:
                price = float(lo[conf_bar])
                match = _detect_equal_levels(recent_lows, conf_bar, price, tol)
                if match is not None:
                    active_levels.append(LiquidityLevel(
                        level_type="EQL", price=price,
                        source_bar=conf_bar, active_since_bar=i,
                    ))
                recent_lows.append((conf_bar, price))
                if len(recent_lows) > 200:
                    recent_lows.pop(0)

        # --- 2. Activate prev-day / prev-session levels. ---
        _maybe_activate_prev_session_levels(row, i, active_levels, activated_keys)

        # --- 3. Register any new FVG formed at this bar. ---
        if not pd.isna(row.get("fvg_bull_mid")):
            active_fvgs.append(ActiveFVG(
                direction="bull",
                top=float(row["fvg_bull_top"]), bot=float(row["fvg_bull_bot"]),
                mid=float(row["fvg_bull_mid"]), formed_at_bar=i,
            ))
        if not pd.isna(row.get("fvg_bear_mid")):
            active_fvgs.append(ActiveFVG(
                direction="bear",
                top=float(row["fvg_bear_top"]), bot=float(row["fvg_bear_bot"]),
                mid=float(row["fvg_bear_mid"]), formed_at_bar=i,
            ))

        # --- 4. Mark FVG mitigation. ---
        for fvg in active_fvgs:
            if fvg.mitigated:
                continue
            if fvg.direction == "bull" and lo[i] <= fvg.mid:
                fvg.mitigated = True
            if fvg.direction == "bear" and hi[i] >= fvg.mid:
                fvg.mitigated = True
        # Drop stale FVGs (older than max_age).
        active_fvgs = [f for f in active_fvgs
                       if i - f.formed_at_bar <= params.fvg_max_age_candles]

        # --- 5. Mark swept levels (any bar, regardless of kill zone). ---
        for lvl in active_levels:
            if lvl.swept:
                continue
            sw = _check_sweep(row, lvl, params)
            if sw is not None:
                lvl.swept = True
                lvl.swept_at_bar = i

        # --- 6. Manage open trade first. ---
        _manage_open(i)

        # Force-close on kill zone end if configured.
        if open_trade is not None and params.close_at_killzone_end:
            kz_now = _killzone_for_bar(row, params)
            # If trade's kill zone is active but this bar is no longer in it, close.
            if kz_now != open_trade.kill_zone:
                _close_trade(open_trade, i, cl[i], "kill_zone_end")

        # --- 7. Kill zone handling. ---
        kz_now = _killzone_for_bar(row, params)
        if kz_now != current_killzone:
            setup = None
            kz_trade_count = 0
            current_killzone = kz_now
        if not kz_now:
            equity_curve.append({"datetime": str(t_now), "equity": equity})
            continue

        diag["bars_in_killzone"] += 1

        # Basic gates.
        if t_now.weekday() not in params.allowed_days:
            diag["skipped_wrong_day"] += 1
            continue
        if params.enable_news_filter and is_news_day(
            t_now.tz_convert(NY_TZ).date(), news_skip_dates,
        ):
            diag["skipped_news"] += 1
            continue
        dk = _daily_key(t_now); wk = _week_key(t_now)
        if daily_trades.get(dk, 0) >= params.max_trades_per_day:
            diag["skipped_daily_limit"] += 1
            continue
        if kz_trade_count >= params.max_trades_per_killzone:
            diag["skipped_killzone_limit"] += 1
            continue
        # Circuit breakers.
        if params.enable_daily_circuit_breaker and \
                daily_pnl.get(dk, 0.0) <= -params.starting_capital * params.daily_loss_limit_pct / 100.0:
            diag["skipped_circuit_breaker"] += 1
            continue
        if params.enable_weekly_circuit_breaker and \
                weekly_pnl.get(wk, 0.0) <= -params.starting_capital * params.weekly_loss_limit_pct / 100.0:
            diag["skipped_circuit_breaker"] += 1
            continue
        if open_trade is not None:
            diag["skipped_open_trade"] += 1
            continue

        # --- 8. State machine: sweep → displacement → FVG → MSS → entry. ---
        if setup is None:
            # Look for a new sweep that was confirmed on THIS bar.
            for lvl in active_levels:
                if lvl.swept and lvl.swept_at_bar == i:
                    sw = _check_sweep(row, lvl, params)
                    if sw is None:
                        continue
                    setup = SetupState(
                        kill_zone=kz_now,
                        sweep_bar=i, sweep_type=sw["type"],
                        sweep_level_type=lvl.level_type,
                        sweep_level_price=lvl.price,
                        sweep_wick_extreme=sw["wick_extreme"],
                    )
                    diag["sweeps_detected"] += 1
                    break

        if setup is None:
            continue

        # Timeout: sweep too old.
        if i - setup.sweep_bar > DISPLACEMENT_SEARCH_BARS and setup.displacement_bar < 0:
            setup = None
            continue

        # Displacement.
        if setup.displacement_bar < 0:
            if setup.sweep_type == "bullish" and bool(row.get("is_bull_disp", False)):
                setup.displacement_bar = i
                diag["displacements_after_sweep"] += 1
            elif setup.sweep_type == "bearish" and bool(row.get("is_bear_disp", False)):
                setup.displacement_bar = i
                diag["displacements_after_sweep"] += 1
            else:
                continue

        # FVG (we look at FVGs formed at or after displacement bar).
        if setup.fvg is None:
            if i - setup.displacement_bar > FVG_SEARCH_BARS:
                setup = None
                continue
            direction_key = "bull" if setup.sweep_type == "bullish" else "bear"
            candidate = None
            for f in active_fvgs:
                if f.mitigated:
                    continue
                if f.direction != direction_key:
                    continue
                if f.formed_at_bar < setup.displacement_bar:
                    continue
                if candidate is None or f.formed_at_bar > candidate.formed_at_bar:
                    candidate = f
            if candidate is None:
                continue
            setup.fvg = candidate
            diag["fvgs_after_displacement"] += 1

        # MSS (optional).
        if params.require_mss and not setup.mss_confirmed:
            if i - setup.sweep_bar > MSS_SEARCH_BARS + DISPLACEMENT_SEARCH_BARS:
                setup = None
                continue
            # Bullish MSS: current close breaks the highest high between sweep+1 and i-1.
            window_hi = hi[setup.sweep_bar + 1 : i]
            window_lo = lo[setup.sweep_bar + 1 : i]
            if setup.sweep_type == "bullish" and window_hi.size and cl[i] > window_hi.max():
                setup.mss_confirmed = True
                diag["mss_confirmations"] += 1
            elif setup.sweep_type == "bearish" and window_lo.size and cl[i] < window_lo.min():
                setup.mss_confirmed = True
                diag["mss_confirmations"] += 1
            else:
                continue

        # HTF bias.
        htf = str(htf_arr[i] or "neutral")
        if params.require_htf_alignment:
            if htf == "neutral" and params.htf_neutral_action == "Skip trade":
                continue
            if setup.sweep_type == "bullish" and htf == "bearish":
                continue
            if setup.sweep_type == "bearish" and htf == "bullish":
                continue
            diag["htf_aligned_passes"] += 1

        # --- 9. Trigger: price trades into FVG. ---
        f = setup.fvg
        if i - f.formed_at_bar > params.fvg_max_age_candles:
            setup = None
            continue
        if f.mitigated:
            diag["skipped_fvg_mitigated"] += 1
            setup = None
            continue

        entry_mode = params.fvg_entry_type
        hit = False
        if setup.sweep_type == "bullish":
            if entry_mode == "50% midpoint" and lo[i] <= f.mid:
                hit = True
            elif entry_mode == "FVG touch" and lo[i] <= f.top:
                hit = True
            elif entry_mode == "FVG close" and cl[i] <= f.top and cl[i] >= f.bot:
                hit = True
        else:
            if entry_mode == "50% midpoint" and hi[i] >= f.mid:
                hit = True
            elif entry_mode == "FVG touch" and hi[i] >= f.bot:
                hit = True
            elif entry_mode == "FVG close" and cl[i] >= f.bot and cl[i] <= f.top:
                hit = True

        if not hit:
            continue

        diag["entries_attempted"] += 1

        # --- 10. Size, stop, target, confluence score. ---
        direction = "long" if setup.sweep_type == "bullish" else "short"
        entry_price = f.mid if entry_mode == "50% midpoint" else (
            f.top if direction == "long" else f.bot
        )

        if params.stop_type == "Beyond sweep":
            if direction == "long":
                stop = setup.sweep_wick_extreme - _pip(params, params.stop_buffer_pips)
            else:
                stop = setup.sweep_wick_extreme + _pip(params, params.stop_buffer_pips)
        elif params.stop_type == "Beyond FVG":
            if direction == "long":
                stop = f.bot - _pip(params, params.stop_buffer_pips)
            else:
                stop = f.top + _pip(params, params.stop_buffer_pips)
        else:
            if direction == "long":
                stop = entry_price - _pip(params, params.fixed_stop_pips)
            else:
                stop = entry_price + _pip(params, params.fixed_stop_pips)

        risk = abs(entry_price - stop)
        if risk <= 0:
            setup = None
            continue
        fvg_size = f.top - f.bot
        if fvg_size / risk < params.min_fvg_to_stop_ratio:
            diag["skipped_r_ratio"] += 1
            setup = None
            continue

        if direction == "long":
            target1 = entry_price + risk
            target2 = entry_price + risk * params.rr_ratio
        else:
            target1 = entry_price - risk
            target2 = entry_price - risk * params.rr_ratio

        # Confluence breakdown.
        breakdown = {
            "kill_zone": 1,
            "sweep": 1,
            "displacement": 1,
            "fvg": 1,
            "mss": int(setup.mss_confirmed),
            "htf_aligned": int(
                (direction == "long" and htf == "bullish") or
                (direction == "short" and htf == "bearish")
            ),
            "eq_levels": int(setup.sweep_level_type in ("EQH", "EQL")),
            "large_fvg": int((fvg_size / params.pip_size) >= params.min_fvg_size_pips * 2),
            "prev_session_level": int(setup.sweep_level_type in PREV_SESSION_LEVEL_TYPES),
        }
        ob = _find_order_block(ind, setup.displacement_bar, "bull" if direction == "long" else "bear")
        breakdown["order_block"] = int(ob is not None and ob["low"] <= entry_price <= ob["high"])
        if params.require_ob_confluence and not breakdown["order_block"]:
            setup = None
            continue

        score = sum(breakdown.values())
        if score < params.min_confluence_score:
            diag["skipped_low_confluence"] += 1
            setup = None
            continue

        # Position size.
        dollar_risk = equity * params.risk_per_trade_pct / 100.0
        size = dollar_risk / risk

        trade = OpenTrade(
            id=next_trade_id, direction=direction,
            entry_time=t_now, entry_bar=i, entry_price=entry_price,
            size=size, open_size=size,
            stop=stop, target1=target1, target2=target2,
            kill_zone=kz_now,
            confluence_score=score, confluence_breakdown=breakdown,
            sweep_level_type=setup.sweep_level_type,
            sweep_level_price=setup.sweep_level_price,
            fvg_top=f.top, fvg_bot=f.bot, fvg_mid=f.mid,
            fvg_size_pips=fvg_size / params.pip_size,
            htf_bias_at_entry=htf, mss_confirmed=setup.mss_confirmed,
        )
        next_trade_id += 1
        open_trade = trade
        kz_trade_count += 1
        daily_trades[dk] = daily_trades.get(dk, 0) + 1
        diag["entries_taken"] += 1
        setup = None   # Allow next setup inside same kill zone (subject to kz limit).

    # Close any still-open trade at last bar.
    if open_trade is not None:
        _close_trade(open_trade, n - 1, cl[n - 1], "end_of_data")

    # Final diagnostic funnel.
    diag["setup_funnel"] = {
        "kill_zone_bars": diag["bars_in_killzone"],
        "sweeps": diag["sweeps_detected"],
        "displacements": diag["displacements_after_sweep"],
        "fvgs": diag["fvgs_after_displacement"],
        "mss": diag["mss_confirmations"],
        "htf_aligned": diag["htf_aligned_passes"],
        "entries_taken": diag["entries_taken"],
    }

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "diagnostics": diag,
    }
