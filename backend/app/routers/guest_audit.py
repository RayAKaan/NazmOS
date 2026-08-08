"""Public guest audit router — the free front door for NazmOS.

No authentication is required. Requests are rate-limited by client IP using a
simple in-memory sliding window so the endpoint can run without Redis in the
sandbox and still protect production.
"""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.services.guest_audit_service import run_guest_audit

router = APIRouter(prefix="/api/v1/guest-audit", tags=["Guest Audit"])

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB — guest uploads should be small samples
MAX_ROWS = 5_000
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}

# In-memory per-IP sliding window: 5 requests per 15 minutes per IP.
# Production should replace this with Redis-backed rate limiting.
_rate_windows: dict[str, deque[float]] = {}


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    window = _rate_windows.setdefault(client_ip, deque())
    while window and window[0] < now - 900:
        window.popleft()
    if len(window) >= 5:
        raise HTTPException(429, detail="Too many guest audits from this IP. Please wait 15 minutes or create an account.")
    window.append(now)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _parse_upload(file: UploadFile) -> list[dict[str, Any]]:
    ext = "" if not file.filename else file.filename.lower().split(".")[-1]
    if f".{ext}" not in ALLOWED_EXTENSIONS and ext not in {"csv", "xlsx", "xls", "json"}:
        raise HTTPException(422, detail="Unsupported file type. Upload CSV, XLSX, or JSON.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, detail="Guest audit files must be under 2 MB. Sign up for larger imports.")

    if ext == "json":
        data = json.loads(content.decode("utf-8", errors="ignore"))
        rows = data if isinstance(data, list) else data.get("rows", [])
        return rows

    try:
        if ext == "csv":
            df = pd.read_csv(pd.io.common.BytesIO(content), dtype=str, keep_default_na=False)
        else:
            df = pd.read_excel(pd.io.common.BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise HTTPException(422, detail=f"Could not parse file: {exc}")

    df = df.where(pd.notna(df), None)
    rows = df.head(MAX_ROWS).to_dict(orient="records")
    return rows


@router.post("")
async def guest_audit(request: Request):
    """Run a free Money Audit on a small sales or inventory sample.

    Accepts either:
    - `multipart/form-data` with a `file` field (CSV/XLSX/JSON), or
    - `application/json` body with `{ "rows": [...] }`.

    Returns a simplified Money Audit summary and top recovery actions. No
    account or authentication is required.
    """
    client_ip = _client_ip(request)
    _check_rate_limit(client_ip)

    rows: list[dict[str, Any]] = []
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        # FastAPI File dependency cannot coexist with a JSON body parameter, so
        # we use the raw request form parsing here.
        form = await request.form()
        file_field = form.get("file")
        if file_field and isinstance(file_field, UploadFile):
            rows = await _parse_upload(file_field)
    else:
        body = await request.body()
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
                rows = data.get("rows", []) if isinstance(data, dict) else data
            except Exception as exc:
                raise HTTPException(422, detail=f"Invalid JSON body: {exc}")

    if not rows:
        raise HTTPException(422, detail="No rows provided. Upload a file or send a JSON rows array.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, detail=f"Guest audit supports up to {MAX_ROWS} rows. Sign up for larger imports.")

    result = await run_guest_audit(rows)

    return JSONResponse(
        content=result,
        headers={
            "X-Guest-Session-Id": result["summary"].get("guest_session_id", ""),
            "X-RateLimit-Limit": "5",
            "X-RateLimit-Window": "900",
        },
    )
