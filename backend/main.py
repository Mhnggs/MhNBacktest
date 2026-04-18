"""FastAPI entry point for the VWAP + EMA backtest dashboard."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import backtest, data, upload

app = FastAPI(title="VWAP + EMA Backtest Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(data.router)
app.include_router(backtest.router)


@app.get("/")
def health():
    return {"status": "ok", "service": "vwap-ema-backtest"}
