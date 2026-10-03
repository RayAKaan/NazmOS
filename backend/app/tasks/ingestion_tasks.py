import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session

settings = get_settings()


def _resolve_stored_path(stored_filename: str) -> Path:
    """Resolve ``uploaded_files.stored_filename`` to a local path.

    ``storage.store`` already returns a path rooted at ``UPLOAD_DIR`` (e.g.
    ``uploads\\<name>.csv``) and the uploader consumes it verbatim
    (``app.routers.upload._resolve_local_parse_path``). Re-joining
    ``UPLOAD_DIR`` here produced ``uploads/uploads/<name>.csv``, which never
    exists, so ingestion reported "File not found" for every upload while the
    row was already marked ``processing``.

    Mirrors the uploader: honour an absolute path, otherwise use the stored
    value as-is, falling back to a UPLOAD_DIR join only if that resolves.
    """
    stored = Path(stored_filename)
    if stored.is_absolute():
        return stored
    joined = Path(settings.UPLOAD_DIR) / stored
    return joined if joined.exists() else stored


def _mark_failed(session, upload_id: str, error: str) -> dict:
    """Put the row in a terminal state so callers never poll a stuck upload.

    The early returns below used to leave ``status='processing'`` in place,
    which surfaced to clients as an indefinite "processing" rather than an
    error.
    """
    session.execute(
        text(
            "UPDATE uploaded_files SET status = 'failed', error_summary = :error "
            "WHERE id = :id"
        ),
        {"id": upload_id, "error": error},
    )
    session.commit()
    return {"status": "failed", "error": error}


def run_process_upload(upload_id: str, business_id: str, column_mapping: dict):
    """Process an authenticated upload through the single canonical Orbit path."""
    import asyncio
    from app.services.cache_service import CacheService
    from app.services.orbit.contracts import SourceType
    from app.services.orbit.ingestion.service import ingest_and_project

    with get_sync_session(tenant_id=business_id) as session:
        row = session.execute(
            text("SELECT * FROM uploaded_files WHERE id = :upload_id AND business_id = :business_id"),
            {"upload_id": upload_id, "business_id": business_id},
        ).fetchone()
        if not row:
            return {"status": "failed", "error": "Upload not found"}

        file_path = _resolve_stored_path(row.stored_filename)
        if not file_path.exists():
            return _mark_failed(session, upload_id, f"File not found: {file_path}")

        session.execute(
            text("UPDATE uploaded_files SET status = 'processing', etl_started_at = NOW() WHERE id = :id"),
            {"id": upload_id},
        )
        session.commit()

        try:
            content = file_path.read_bytes()

            async def _run():
                from contextlib import asynccontextmanager
                from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

                engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
                factory = async_sessionmaker(
                    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
                )

                @asynccontextmanager
                async def scope():
                    async with factory() as db:
                        if not settings.DATABASE_URL.startswith("sqlite"):
                            from app.database.connection import _set_rls_context
                            await _set_rls_context(db)
                        try:
                            yield db
                            await db.commit()
                        except Exception:
                            await db.rollback()
                            raise

                try:
                    async with scope() as db:
                        return await ingest_and_project(
                            db,
                            content,
                            business_id=business_id,
                            source_name=str(row.original_filename),
                            source_type=SourceType.FILE,
                            mime_type=getattr(row, "mime_type", None),
                            source_location=str(row.stored_filename),
                        )
                finally:
                    await engine.dispose()

            canonical, projection = asyncio.run(_run())
            status_value = "completed" if canonical.succeeded else "needs_review"
            session.execute(
                text("UPDATE uploaded_files SET status = :status, row_count_imported = :imported, row_count_failed = :failed, etl_completed_at = NOW(), error_summary = :error WHERE id = :id"),
                {
                    "id": upload_id,
                    "status": status_value,
                    "imported": canonical.records_accepted,
                    "failed": canonical.records_rejected,
                    "error": None if canonical.succeeded else "; ".join(canonical.warnings[:5]),
                },
            )
            session.commit()
            CacheService.invalidate_business_cache(business_id)
            try:
                os.unlink(file_path)
            except OSError:
                pass

            return {
                "status": status_value,
                "upload_id": upload_id,
                "stats": {
                    "imported": canonical.records_accepted,
                    "failed": canonical.records_rejected,
                    "ambiguous": canonical.records_ambiguous,
                    "conflicts": len(canonical.conflicts),
                    "state_version": canonical.state_version_after,
                    "projection": projection.to_dict(),
                },
            }
        except Exception as exc:
            session.execute(
                text("UPDATE uploaded_files SET status = 'failed', error_summary = :error WHERE id = :id"),
                {"id": upload_id, "error": str(exc)},
            )
            session.commit()
            return {"status": "failed", "error": str(exc)}

def run_cleanup_stale_uploads():
    # Supervisor scope: purging stale uploads is a cross-tenant maintenance
    # job by design, so no tenant context is applied here.
    cutoff = datetime.utcnow() - timedelta(hours=48)

    with get_sync_session() as session:
        result = session.execute(
            text("""
                SELECT id, stored_filename FROM uploaded_files
                WHERE status IN ('uploaded', 'mapping_required', 'mapping_saved')
                AND created_at < :cutoff
            """),
            {"cutoff": cutoff}
        )
        stale = result.fetchall()

        deleted = 0
        for upload in stale:
            file_path = _resolve_stored_path(upload.stored_filename)
            try:
                if file_path.exists():
                    os.unlink(file_path)
                session.execute(
                    text("DELETE FROM uploaded_files WHERE id = :id"),
                    {"id": upload.id}
                )
                deleted += 1
            except:
                pass

        session.commit()
        return {"deleted": deleted}


def run_nightly_recovery_match_scan() -> dict:
    """Preserved body of the formerly-dormant nightly recovery-match scan.

    Kept as a first-class NazmOS function (previously only existed inside a
    Celery task definition body); not part of any default schedule — callable
    on demand via the ``nightly_recovery_match_scan`` operation.
    """
    import asyncio
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from app.services.recovery_match_matcher import run_nightly_recovery_match_scan as _scan

    _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5)
    _sf = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _scope():
        async with _sf() as session:
            from app.database.connection import _set_rls_context
            if not settings.DATABASE_URL.startswith("sqlite"):
                await _set_rls_context(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def _run():
        async with _scope() as session:
            return await _scan(session)

    try:
        result = asyncio.run(_run())
    finally:
        asyncio.run(_engine.dispose())
    return result
