"""Data fetching endpoints (TwelveData, session management)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import TwelveDataRequest
from ..services.data_loader import fetch_twelvedata, summarise
from ..services.store import delete_session, list_sessions, save_dataset

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/twelvedata")
def twelvedata(req: TwelveDataRequest):
    try:
        df = fetch_twelvedata(
            symbol=req.symbol,
            interval=req.interval,
            start_date=req.start_date,
            end_date=req.end_date,
            api_key=req.api_key,
            use_cache=req.use_cache,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc

    if df.empty:
        raise HTTPException(404, "TwelveData returned no rows for that range")

    sid = save_dataset(df, source="twelvedata", symbol=req.symbol)
    info = summarise(df)
    sample = df.head(5).assign(datetime=lambda d: d["datetime"].astype(str)).to_dict("records")
    return {
        "session_id": sid,
        "rows_loaded": info["rows"],
        "date_range": {"start": info["start"], "end": info["end"]},
        "symbol_detected": req.symbol,
        "sample": sample,
    }


@router.get("/sessions")
def sessions():
    return {"sessions": list_sessions()}


@router.delete("/sessions/{session_id}")
def remove_session(session_id: str):
    if not delete_session(session_id):
        raise HTTPException(404, "Session not found")
    return {"deleted": session_id}
