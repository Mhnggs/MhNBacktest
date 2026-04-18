"""In-memory session store for uploaded/fetched datasets."""

from __future__ import annotations

import threading
import uuid
from typing import Optional

import pandas as pd

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict] = {}


def save_dataset(df: pd.DataFrame, source: str, symbol: Optional[str] = None) -> str:
    sid = uuid.uuid4().hex[:12]
    with _LOCK:
        _SESSIONS[sid] = {"df": df, "source": source, "symbol": symbol}
    return sid


def get_dataset(session_id: str) -> Optional[dict]:
    with _LOCK:
        return _SESSIONS.get(session_id)


def list_sessions() -> list[dict]:
    with _LOCK:
        return [
            {"session_id": k, "rows": len(v["df"]), "source": v["source"], "symbol": v.get("symbol")}
            for k, v in _SESSIONS.items()
        ]


def delete_session(session_id: str) -> bool:
    with _LOCK:
        return _SESSIONS.pop(session_id, None) is not None
