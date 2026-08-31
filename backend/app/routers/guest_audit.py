"""Public guest audit router — the free front door for NazmOS.

No authentication is required. Requests are rate-limited by client IP using a
simple in-memory sliding window so the endpoint needs no extra infrastructure
and still protects production.

Guardrails (C7): max file size, max rows, max sheets, max paired products,
processing timeout, malformed-file rejection, in-memory parsing (nothing
written to disk) and deterministic fuzzy-match bounds.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi.responses import JSONResponse

from app.services.file_ingestion import analyze_file_metadata, resolve_columns
from app.services.guest_audit_service import run_guest_audit, run_two_file_audit
from app.services.telemetry import record_guest_audit
from app.services.workbook_loader import DataQualityError, load_workbook

router = APIRouter(prefix="/api/v1/guest-audit", tags=["Guest Audit"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB — guest uploads should remain small samples
MAX_ROWS = 5_000
MAX_SHEETS = 20
PROCESSING_TIMEOUT_SECONDS = 20
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}

# In-memory per-IP sliding window: 5 requests per 15 minutes per IP.
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


async def _read_upload(file: UploadFile) -> bytes:
    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in {"csv", "xlsx", "xlsm", "xls", "json"}:
        raise HTTPException(422, detail="Unsupported file type. Upload CSV, XLSX, or JSON.")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(413, detail="Guest audit files must be under 10 MB. Sign up for larger imports.")
        chunks.append(chunk)
    try:
        await file.close()
    except Exception:
        pass
    return b"".join(chunks)


def _load_frame(content: bytes, filename: str) -> tuple[pd.DataFrame, dict[str, Any], Any]:
    try:
        load = load_workbook(content, filename)
    except DataQualityError as exc:
        raise HTTPException(422, detail=exc.parse_failure_reason)
    df = load.df
    if len(df) == 0:
        raise HTTPException(422, detail="File contains no data rows.")
    if len(df) > MAX_ROWS:
        raise HTTPException(413, detail=f"Guest audit supports up to {MAX_ROWS} rows per file. Sign up for larger imports.")
    if (load.sheet_count or 1) > MAX_SHEETS:
        raise HTTPException(422, detail=f"Workbook has too many sheets (max {MAX_SHEETS}). Please combine into one sheet.")
    resolution = resolve_columns(df)
    metadata = analyze_file_metadata(df, load.file_type, load.meta())
    return df, load.meta(), resolution


def _rows_from_json(body: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(422, detail=f"Invalid JSON body: {exc}")
    rows = data.get("rows", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise HTTPException(422, detail="JSON body must be an object with a `rows` list, or a list of row objects.")
    return rows


@router.post("")
async def guest_audit(request: Request):
    """Run a free Money Audit on a sales/inventory sample.

    Accepts either:
    - `multipart/form-data` with a `file` field (CSV/XLSX/JSON) — single file, or
    - `multipart/form-data` with `sales_file` + `inventory_file` fields — the
      full two-file flow (pairs products by name, no AI), or
    - `application/json` body with `{ "rows": [...] }`.

    Returns a simplified Money Audit summary and top recovery actions. No
    account or authentication is required.
    """
    client_ip = _client_ip(request)
    _check_rate_limit(client_ip)
    started = time.time()

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        sales_file = form.get("sales_file")
        inventory_file = form.get("inventory_file")
        file_field = form.get("file")

        if isinstance(sales_file, StarletteUploadFile) and isinstance(inventory_file, StarletteUploadFile):
            sales_bytes = await _read_upload(sales_file)
            inventory_bytes = await _read_upload(inventory_file)
            sales_df, sales_extra, sales_resolution = _load_frame(sales_bytes, sales_file.filename or "sales.csv")
            inventory_df, inventory_extra, inventory_resolution = _load_frame(inventory_bytes, inventory_file.filename or "inventory.csv")

            sales_meta = analyze_file_metadata(sales_df, "xlsx" if sales_extra.get("selected_sheet") else "csv", sales_extra)
            inventory_meta = analyze_file_metadata(inventory_df, "xlsx" if inventory_extra.get("selected_sheet") else "csv", inventory_extra)

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(run_two_file_audit, sales_df, inventory_df, sales_resolution, inventory_resolution),
                    timeout=PROCESSING_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                record_guest_audit("guest_audit_request", status="timeout", source="two_file",
                                   file_type="paired_csv", row_count=min(len(sales_df), MAX_ROWS) + min(len(inventory_df), MAX_ROWS))
                for df, meta in ((sales_df, sales_meta), (inventory_df, inventory_meta)):
                    record_guest_audit(
                        "guest_audit_upload", source="two_file", file_type=meta.file_type,
                        selected_sheet=meta.selected_sheet, sheet_count=meta.sheet_count,
                        header_row_index=meta.header_row_index, row_count=len(df),
                        detected_columns=meta.detected_columns, column_confidence=meta.column_confidence,
                    )
                raise HTTPException(504, detail="Analysis timed out. Please upload smaller files.")

            code = "two_file"
            for df, meta in ((sales_df, sales_meta), (inventory_df, inventory_meta)):
                record_guest_audit(
                    "guest_audit_upload", source="two_file", file_type=meta.file_type,
                    selected_sheet=meta.selected_sheet, sheet_count=meta.sheet_count,
                    header_row_index=meta.header_row_index, row_count=len(df),
                    detected_columns=meta.detected_columns, column_confidence=meta.column_confidence,
                    is_arabic_headers=meta.is_arabic_headers, is_arabic_data=meta.is_arabic_data,
                )
        elif isinstance(file_field, StarletteUploadFile):
            content = await _read_upload(file_field)
            df, meta, resolution = _load_frame(content, file_field.filename or "upload.csv")
            rows = df.head(MAX_ROWS).to_dict(orient="records")
            if not rows:
                raise HTTPException(422, detail="File contains no data rows.")
            try:
                result = await asyncio.wait_for(run_guest_audit(rows), timeout=PROCESSING_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                record_guest_audit("guest_audit_request", status="timeout", source="single_file", file_type=meta.get("file_type", "csv"))
                raise HTTPException(504, detail="Analysis timed out. Please upload smaller files.")
            file_meta = analyze_file_metadata(df, meta.get("file_type", "csv"), meta)
            record_guest_audit(
                "guest_audit_upload", source="single_file", file_type=file_meta.file_type,
                selected_sheet=file_meta.selected_sheet, sheet_count=file_meta.sheet_count,
                header_row_index=file_meta.header_row_index, row_count=len(df),
                detected_columns=file_meta.detected_columns, column_confidence=file_meta.column_confidence,
                is_arabic_headers=file_meta.is_arabic_headers, is_arabic_data=file_meta.is_arabic_data,
            )
            code = "single_file"
        else:
            raise HTTPException(422, detail="Upload a `file`, or both `sales_file` and `inventory_file`.")
    else:
        body = await request.body()
        if len(body) > 512 * 1024:
            raise HTTPException(413, detail="JSON payload too large for the guest audit.")
        rows = _rows_from_json(body) if body else []
        if not rows:
            raise HTTPException(422, detail="No rows provided. Upload a file or send a JSON rows array.")
        if len(rows) > MAX_ROWS:
            raise HTTPException(413, detail=f"Guest audit supports up to {MAX_ROWS} rows. Sign up for larger imports.")
        result = await asyncio.wait_for(run_guest_audit(rows), timeout=PROCESSING_TIMEOUT_SECONDS)
        code = "json"

    processed = result.get("summary", {})
    pairing = (processed.get("pairing") or {}).get("success_rate")
    record_guest_audit(
        "guest_audit_request", status="success", source=code, row_count=processed.get("row_count", 0),
        pairing_attempted=(processed.get("pairing") or {}).get("attempted"),
        paired_products=(processed.get("pairing") or {}).get("paired"),
        pairing_success_rate=pairing,
        products_with_risk=processed.get("products_needing_attention"),
        processing_time_ms=(time.time() - started) * 1000,
    )

    return JSONResponse(
        content=result,
        headers={
            "X-Guest-Session-Id": str(result["summary"].get("guest_session_id", "")),
            "X-RateLimit-Limit": "5",
            "X-RateLimit-Window": "900",
        },
    )