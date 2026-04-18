# VWAP + EMA Pullback Backtest Dashboard

Full-stack research dashboard for backtesting a VWAP + EMA pullback day-trading
strategy. Upload MetaTrader CSV exports or pull data from the TwelveData REST
API, tune every strategy parameter, and review trade-by-trade performance with
an equity curve, candlestick chart with overlays, and statistical breakdowns.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · pandas · numpy · pytz |
| Frontend | React (Vite) · Tailwind · Zustand · Recharts · TradingView Lightweight Charts |

## Getting started

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API serves at `http://localhost:8000`. Swagger docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite dev server runs at `http://localhost:5173` and proxies `/api/*` to the
backend on port 8000.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/api/upload` | Upload one or more MT CSV files |
| `POST` | `/api/data/twelvedata` | Fetch + cache OHLCV from TwelveData |
| `GET` | `/api/data/sessions` | List loaded sessions |
| `DELETE` | `/api/data/sessions/{id}` | Drop a session |
| `POST` | `/api/backtest/run` | Run the strategy and return trades + stats |

## Strategy summary

The engine processes bars in order (no lookahead) and looks for pullbacks to
the configurable EMA while price holds above (long) or below (short) the
session-anchored VWAP. Signals require:

- Price above/below VWAP and within `vwap_max_distance_pct`
- EMA slope above the configured threshold
- Previous bar touched the EMA within `ema_touch_pct`
- Current bar closes in the signal direction
- Volume ratio ≥ `volume_multiplier` (optional)
- Bullish/bearish candle pattern (optional)
- Fewer than `chop_filter_crossings` VWAP crossings in the last 10 bars
- Daily trade count below `max_trades_per_day`
- Bar timestamp inside the configured trading session(s)

Trades use entry = signal-bar high/low ± 1 tick, stop = opposite extreme ±
buffer ticks, with optional partial take-profit at 1.5R that moves the stop to
breakeven.

Position sizing uses fixed fractional risk: `equity * risk_per_trade_pct`.

## Notes & caveats

- VWAP resets every trading day (session-anchored), not rolling.
- Naive datetimes in uploaded CSVs are interpreted in the configured timezone.
- TwelveData free-tier rate limits are respected with a delay between paginated
  requests; results are cached to `backend/cache/`.
- This is a research tool. Not investment advice.
