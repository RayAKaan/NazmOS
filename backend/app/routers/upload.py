from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, Body, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
import aiofiles
import uuid
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import text

from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.middleware.feature_gate import enforce_upload_limit
from app.database import get_db, User, Business, UploadedFile as UploadedFileModel
from app.services.file_validator import FileValidator, FileValidationError
from app.services.schema_detector import SchemaDetector
from app.services.upload_service import UploadService
from app.services.storage import storage
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/upload", tags=["upload"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)


def _looks_like_local_path(value: str) -> bool:
    """Return True if the stored filename is a local filesystem path."""
    if not value:
        return True
    return value.startswith(("/", ".", "\\")) or "://" not in value


async def _resolve_local_parse_path(stored_filename: str, upload_id: str) -> tuple[Path, bool]:
    """Resolve an uploaded file to a local path suitable for parsing.

    Returns:
        (local_path, cleanup_after_parse).  When ``cleanup_after_parse`` is
        True, the caller must delete ``local_path`` after parsing.
    """
    if settings.STORAGE_BACKEND.lower() == "local" or _looks_like_local_path(stored_filename):
        return Path(stored_filename), False

    # Object storage backend: download to a temporary local file for parsing.
    tmp_name = f"tmp_{upload_id}_{Path(stored_filename).name}"
    local_path = UPLOAD_DIR / tmp_name
    try:
        retrieved = await storage.retrieve(stored_filename)
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to retrieve uploaded file for parsing: {exc}")

    try:
        async with aiofiles.open(local_path, "wb") as f:
            await f.write(retrieved)
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to write temporary parse file: {exc}")

    return local_path, True


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    business_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    # Verify business access and enforce Free Money Audit upload limits.
    await assert_business_access(db, business_id, current_user)
    await enforce_upload_limit(db, business_id)

    # Secure filename – allowlist only
    orig_suffix = Path(file.filename).suffix.lower()
    allowed = [e.strip() for e in settings.ALLOWED_UPLOAD_EXTENSIONS.split(",")]
    if orig_suffix not in allowed:
        raise HTTPException(422, detail=f"Invalid file type {orig_suffix}. Allowed: {', '.join(allowed)}")
    
    upload_id = str(uuid.uuid4())
    safe_filename = f"{upload_id}_{uuid.uuid4().hex[:8]}{orig_suffix}"

    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, detail="File too large. Maximum is 15 MB.")

    # Persist through the configured storage backend (local/S3/MinIO).
    # For local storage this still lands in UPLOAD_DIR; for object storage
    # it uploads to the configured bucket and returns a URI.
    try:
        storage_uri = await storage.store(safe_filename, content, content_type=file.content_type or "application/octet-stream")
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to store uploaded file: {exc}")

    # Build a local path for parsing through the storage abstraction. Object
    # storage backends download to a temporary file; local backends use the
    # stored path directly. Temporary files are always cleaned up after parse.
    try:
        local_parse_path, cleanup_after_parse = await _resolve_local_parse_path(
            storage_uri, upload_id
        )
    except Exception as exc:
        raise HTTPException(500, detail=f"Failed to resolve uploaded file for parsing: {exc}")

    try:
        validation = FileValidator.validate(
            local_parse_path,
            file.filename,
            len(content)
        )

        df = UploadService.parse_file(
            local_parse_path,
            validation["detected_extension"],
            validation["encoding"],
        )
        detection = SchemaDetector().detect(df)

        result = await db.execute(
            text("""
                INSERT INTO uploaded_files
                    (id, business_id, uploaded_by, stored_filename, original_filename, file_type,
                     file_size_bytes, mime_type, sha256_hash, status, row_count_raw,
                     detected_columns, sample_rows, scan_completed_at)
                VALUES
                    (:id, :business_id, :uploaded_by, :stored_filename, :original_filename, :file_type,
                     :file_size_bytes, :mime_type, :sha256_hash, 'mapping_required', :row_count_raw,
                     :detected_columns, :sample_rows, NOW())
                RETURNING id
            """),
            {
                "id": upload_id,
                "business_id": business_id,
                "uploaded_by": str(current_user.id),
                "stored_filename": storage_uri,  # may be a local path or s3:// URI
                "original_filename": file.filename,
                "file_type": validation["detected_extension"].lstrip("."),
                "file_size_bytes": len(content),
                "mime_type": validation["mime_type"],
                "sha256_hash": validation["sha256_hash"],
                "row_count_raw": len(df),
                "detected_columns": json.dumps(detection["detected_columns"]),
                "sample_rows": json.dumps(detection["sample_rows"]),
            }
        )
        await db.commit()

        return {
            "upload_id": upload_id,
            "filename": file.filename,
            "file_size": len(content),
            "mime_type": validation["mime_type"],
            "row_count": len(df),
            "detected_columns": detection["detected_columns"],
            "confidence_scores": detection["confidence_scores"],
            "unmapped_columns": detection["unmapped_columns"],
            "sample_rows": detection["sample_rows"],
            "suggested_file_kind": detection.get("suggested_file_kind"),
            "schema_valid": bool(detection["detected_columns"]),
            "status": "mapping_required",
        }

    except FileValidationError as e:
        raise HTTPException(422, detail={"code": e.code, "message": e.message})
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    finally:
        if cleanup_after_parse:
            try:
                os.unlink(local_parse_path)
            except Exception:
                pass


@router.post("/{upload_id}/map")
async def confirm_mapping(
    upload_id: str,
    payload: dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    business_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Save merchant-confirmed mappings and start import.

    Accepts both the old raw mapping body and the newer UX body:
    {"business_id": "...", "column_mapping": {...}}
    {"business_id": "...", "column_mappings": {...}}
    """
    effective_business_id = business_id or payload.get("business_id")
    if not effective_business_id:
        raise HTTPException(422, detail="business_id is required")

    if "column_mapping" in payload or "column_mappings" in payload:
        incoming_mapping = payload.get("column_mapping") or payload.get("column_mappings") or {}
    else:
        incoming_mapping = payload

    if not isinstance(incoming_mapping, dict):
        raise HTTPException(422, detail="column_mapping must be an object")

    clean_mapping = {k: v for k, v in incoming_mapping.items() if v not in (None, "")}

    ownership = await db.execute(
        text("""
            SELECT u.id FROM uploaded_files u
            JOIN businesses b ON b.id = u.business_id
            WHERE u.id = :id
              AND u.business_id = :business_id
              AND (u.uploaded_by = :uid OR b.owner_id = :uid)
        """),
        {"id": upload_id, "business_id": effective_business_id, "uid": str(current_user.id)}
    )
    if not ownership.fetchone():
        raise HTTPException(404, detail="Upload not found")

    await db.execute(
        text("""
            UPDATE uploaded_files
            SET column_mapping = :mapping,
                status = 'processing',
                mapping_saved_at = NOW(),
                etl_started_at = COALESCE(etl_started_at, NOW())
            WHERE id = :id
        """),
        {"id": upload_id, "mapping": json.dumps(clean_mapping)}
    )
    await db.commit()

    task_id = f"bt_{upload_id}"

    if settings.USE_CELERY:
        from app.tasks.ingestion_tasks import process_upload_task
        task = process_upload_task.apply_async(
            args=[upload_id, effective_business_id, clean_mapping],
            queue="ingestion",
            countdown=1,
        )
        task_id = task.id

        await db.execute(
            text("UPDATE uploaded_files SET celery_task_id = :task_id WHERE id = :id"),
            {"id": upload_id, "task_id": task.id}
        )
        await db.commit()
    else:
        # Zero-cost mode: run ingestion inline on the main event loop. The file
        # sizes for Money Audit are small enough that blocking the response is
        # acceptable for pilot validation without Celery/Redis.
        from app.services.etl_pipeline import ETLPipeline
        from app.services.upload_service import UploadService
        from app.services.schema_detector import SchemaDetector
        from pathlib import Path

        upload_row = await db.execute(
            text("SELECT stored_filename, file_type FROM uploaded_files WHERE id = :id"),
            {"id": upload_id},
        )
        upload_meta = upload_row.fetchone()
        local_parse_path, cleanup_after_parse = await _resolve_local_parse_path(
            upload_meta.stored_filename, upload_id
        )
        try:
            try:
                df = UploadService.parse_file(local_parse_path, f".{upload_meta.file_type}", "utf-8")
                if not clean_mapping:
                    detection = SchemaDetector().detect(df)
                    clean_mapping = detection["detected_columns"]
                pipeline = ETLPipeline(upload_id, effective_business_id, df, clean_mapping)
                stats = await pipeline.run()
            except Exception as e:
                # Mark the upload failed so it never gets stuck in 'processing'.
                await db.execute(
                    text("UPDATE uploaded_files SET status = 'failed', error_summary = :error WHERE id = :id"),
                    {"id": upload_id, "error": str(e)}
                )
                await db.commit()
                raise
        finally:
            if cleanup_after_parse:
                try:
                    os.unlink(local_parse_path)
                except Exception:
                    pass

        # Persist import counters so /result and /status report real numbers.
        imported = int(stats.get("imported", 0))
        failed = int(stats.get("failed", 0))
        await db.execute(
            text("""
                UPDATE uploaded_files
                SET status = 'completed',
                    row_count_imported = :imported,
                    row_count_failed = :failed,
                    etl_completed_at = NOW()
                WHERE id = :id
            """),
            {"id": upload_id, "imported": imported, "failed": failed}
        )
        await db.commit()

    return {
        "task_id": task_id,
        "upload_id": upload_id,
        "status": "completed" if not settings.USE_CELERY else "processing",
        "progress": 100 if not settings.USE_CELERY else 35,
        "rows_processed": imported if not settings.USE_CELERY else 0,
        "rows_imported": imported if not settings.USE_CELERY else 0,
        "rows_failed": failed if not settings.USE_CELERY else 0,
    }


@router.get("/{upload_id}/progress")
async def stream_progress(
    upload_id: str,
    current_user: User = Depends(get_current_user),
):
    async def progress_stream():
        import redis.asyncio as aioredis
        r = None
        pubsub = None
        try:
            r = aioredis.from_url(settings.REDIS_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"etl_progress:{upload_id}")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                    try:
                        parsed = json.loads(data)
                        if parsed.get("percent") in (100, -1):
                            break
                    except:
                        pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Progress stream interrupted: {e}'})}\n\n"
        finally:
            if pubsub:
                try:
                    await pubsub.close()
                except:
                    pass
            if r:
                try:
                    await r.aclose()
                except:
                    pass
            yield f"data: {json.dumps({'type': 'error', 'message': 'Redis connection failed'})}\n\n"

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _upload_errors(upload) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    validation_errors = getattr(upload, "validation_errors", None) or []
    if isinstance(validation_errors, str):
        try:
            validation_errors = json.loads(validation_errors)
        except Exception:
            validation_errors = []
    if isinstance(validation_errors, list):
        for err in validation_errors[:25]:
            if isinstance(err, dict):
                errors.append({
                    "row": err.get("row", 0),
                    "column": err.get("column", "file"),
                    "value": err.get("value", ""),
                    "error": err.get("error") or err.get("message") or "Validation issue",
                })

    if getattr(upload, "error_summary", None):
        errors.insert(0, {
            "row": 0,
            "column": "file",
            "value": "",
            "error": str(upload.error_summary),
        })
    return errors


def _duration_seconds(upload) -> float:
    started = getattr(upload, "etl_started_at", None) or getattr(upload, "mapping_saved_at", None)
    finished = getattr(upload, "etl_completed_at", None) or datetime.utcnow()
    if not started:
        return 0.0
    try:
        if getattr(started, "tzinfo", None) and not getattr(finished, "tzinfo", None):
            finished = finished.replace(tzinfo=started.tzinfo)
        return max(0.0, (finished - started).total_seconds())
    except Exception:
        return 0.0


def _progress_for(upload) -> int:
    status = str(upload.status or "uploaded")
    if status == "completed":
        return 100
    if status == "failed":
        return 100
    if status == "processing":
        return 65
    if status == "mapping_required":
        return 30
    return 15


@router.get("/{upload_id}/status")
@router.get("/status/{upload_id}")
async def get_upload_status(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT u.* FROM uploaded_files u
            JOIN businesses b ON b.id = u.business_id
            LEFT JOIN team_members tm ON tm.business_id = u.business_id AND tm.user_id = :uid AND tm.is_active = true
            WHERE u.id = :id AND (u.uploaded_by = :uid OR b.owner_id = :uid OR tm.user_id IS NOT NULL)
        """),
        {"id": upload_id, "uid": str(current_user.id)}
    )
    upload = result.fetchone()

    if not upload:
        raise HTTPException(404, detail="Upload not found")

    imported = _as_int(upload.row_count_imported)
    failed = _as_int(upload.row_count_failed)
    total = _as_int(upload.row_count_raw, imported + failed)
    status = str(upload.status or "uploaded")
    rows_processed = imported + failed if status in {"completed", "failed"} else min(imported + failed, total)

    return {
        "upload_id": str(upload.id),
        "filename": upload.original_filename,
        "status": status,
        "progress": _progress_for(upload),
        "rows_processed": rows_processed,
        "total_rows": total,
        "errors": _upload_errors(upload),
        "started_at": upload.etl_started_at.isoformat() if upload.etl_started_at else None,
        "estimated_completion": None,
        "row_count_raw": total,
        "row_count_imported": imported,
        "row_count_failed": failed,
        "created_at": upload.created_at.isoformat() if upload.created_at else None,
    }


@router.get("/{upload_id}/result")
async def get_upload_result(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT u.* FROM uploaded_files u
            JOIN businesses b ON b.id = u.business_id
            LEFT JOIN team_members tm ON tm.business_id = u.business_id AND tm.user_id = :uid AND tm.is_active = true
            WHERE u.id = :id AND (u.uploaded_by = :uid OR b.owner_id = :uid OR tm.user_id IS NOT NULL)
        """),
        {"id": upload_id, "uid": str(current_user.id)}
    )
    upload = result.fetchone()
    if not upload:
        raise HTTPException(404, detail="Upload not found")

    imported = _as_int(upload.row_count_imported)
    failed = _as_int(upload.row_count_failed)
    status = "failed" if upload.status == "failed" else "partial" if failed > 0 else "completed"
    return {
        "upload_id": str(upload.id),
        "status": status,
        "rows_imported": imported,
        "rows_failed": failed,
        "errors": _upload_errors(upload),
        "duration_seconds": _duration_seconds(upload),
    }


@router.get("/history")
async def get_upload_history(
    business_id: str,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await assert_business_access(db, business_id, current_user)
    offset = (page - 1) * limit

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM uploaded_files WHERE business_id = :business_id"),
        {"business_id": business_id}
    )
    total = count_result.scalar()

    result = await db.execute(
        text("""
            SELECT * FROM uploaded_files
            WHERE business_id = :business_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"business_id": business_id, "limit": limit, "offset": offset}
    )
    uploads = result.fetchall()

    return {
        "uploads": [
            {
                "upload_id": str(u.id),
                "filename": u.original_filename,
                "status": u.status,
                "row_count_imported": u.row_count_imported,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in uploads
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/ingest-json")
async def ingest_json(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Zero-cost client-side ETL endpoint.

    Accepts pre-parsed CSV rows as JSON from the frontend (PapaParse).
    Runs the same ETL pipeline but skips server-side file parsing.

    Body: {
        "business_id": "...",
        "column_mapping": { "source_col": "target_field", ... },
        "rows": [ { "source_col": "value", ... }, ... ],
        "filename": "sales_jan.csv"
    }
    """
    import pandas as pd

    business_id = payload.get("business_id")
    column_mapping = payload.get("column_mapping", {})
    rows = payload.get("rows", [])
    filename = payload.get("filename", "client_upload.csv")

    if not business_id:
        raise HTTPException(422, detail="business_id is required")
    if not rows:
        raise HTTPException(422, detail="rows array is required")

    await assert_business_access(db, business_id, current_user)
    await enforce_upload_limit(db, business_id)

    upload_id = str(uuid.uuid4())

    await db.execute(
        text("""
            INSERT INTO uploaded_files
                (id, business_id, uploaded_by, original_filename, file_type,
                 file_size_bytes, mime_type, status, row_count_raw,
                 column_mapping, scan_completed_at, etl_started_at)
            VALUES
                (:id, :business_id, :uploaded_by, :original_filename, 'csv',
                 :file_size_bytes, 'application/json', 'processing', :row_count_raw,
                 :column_mapping, NOW(), NOW())
        """),
        {
            "id": upload_id,
            "business_id": business_id,
            "uploaded_by": str(current_user.id),
            "original_filename": filename,
            "file_size_bytes": len(json.dumps(rows)),
            "row_count_raw": len(rows),
            "column_mapping": json.dumps(column_mapping),
        }
    )
    await db.commit()

    clean_mapping = {k: v for k, v in column_mapping.items() if v not in (None, "")}

    try:
        df = pd.DataFrame(rows)
        from app.services.etl_pipeline import ETLPipeline
        pipeline = ETLPipeline(upload_id, business_id, df, clean_mapping)
        stats = await pipeline.run()

        await db.execute(
            text("""
                UPDATE uploaded_files
                SET status = 'completed',
                    row_count_imported = :imported,
                    row_count_failed = :failed,
                    etl_completed_at = NOW()
                WHERE id = :id
            """),
            {
                "id": upload_id,
                "imported": stats.get("imported", 0),
                "failed": stats.get("failed", 0),
            }
        )
        await db.commit()

        from app.services.cache_service import CacheService
        CacheService.invalidate_business_cache(business_id)

        return {
            "upload_id": upload_id,
            "status": "completed",
            "rows_imported": stats.get("imported", 0),
            "rows_failed": stats.get("failed", 0),
            "errors": [],
            "duration_seconds": 0,
        }

    except Exception as e:
        await db.execute(
            text("UPDATE uploaded_files SET status = 'failed', error_summary = :error WHERE id = :id"),
            {"id": upload_id, "error": str(e)}
        )
        await db.commit()
        raise HTTPException(500, detail=str(e))
