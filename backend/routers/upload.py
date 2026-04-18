"""CSV upload endpoint."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.data_loader import merge_frames, parse_mt_csv, summarise
from ..services.store import save_dataset

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_csv(
    files: list[UploadFile] = File(...),
    source_tz: str = Form("UTC"),
):
    if not files:
        raise HTTPException(400, "No files uploaded")
    frames = []
    for f in files:
        try:
            raw = await f.read()
            frames.append(parse_mt_csv(raw, source_tz=source_tz))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Failed to parse {f.filename}: {exc}") from exc

    df = merge_frames(frames)
    df.attrs["source_tz"] = source_tz
    if df.empty:
        raise HTTPException(400, "Uploaded files produced an empty dataset")

    symbol = files[0].filename.split(".")[0] if files[0].filename else None
    sid = save_dataset(df, source="upload", symbol=symbol)
    info = summarise(df)
    sample = df.head(5).assign(datetime=lambda d: d["datetime"].astype(str)).to_dict("records")
    return {
        "session_id": sid,
        "rows_loaded": info["rows"],
        "date_range": {"start": info["start"], "end": info["end"]},
        "symbol_detected": symbol,
        "sample": sample,
    }
