import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import text

from app.config import get_settings
from app.database.connection import get_sync_session
from app.services.etl_pipeline import ETLPipeline
from app.services.upload_service import UploadService
from app.services.schema_detector import SchemaDetector

settings = get_settings()


def run_process_upload(upload_id: str, business_id: str, column_mapping: dict):
    """Core ingestion logic — called by both Celery task and BackgroundTasks fallback."""
    from app.services.cache_service import CacheService

    with get_sync_session() as session:
        result = session.execute(
            text("SELECT * FROM uploaded_files WHERE id = :upload_id"),
            {"upload_id": upload_id}
        )
        upload = result.fetchone()

        if not upload:
            return {"status": "failed", "error": "Upload not found"}

        file_path = Path(settings.UPLOAD_DIR) / upload.stored_filename
        if not file_path.exists():
            return {"status": "failed", "error": "File not found"}

        session.execute(
            text("UPDATE uploaded_files SET status = 'processing', etl_started_at = NOW() WHERE id = :id"),
            {"id": upload_id}
        )
        session.commit()

        try:
            df = UploadService.parse_file(
                file_path,
                f".{upload.file_type}",
                "utf-8"
            )

            if column_mapping:
                clean_mapping = {k: v for k, v in column_mapping.items() if v is not None}
            else:
                detection = SchemaDetector().detect(df)
                clean_mapping = detection["detected_columns"]

            pipeline = ETLPipeline(upload_id, business_id, df, clean_mapping)
            import asyncio
            stats = asyncio.run(pipeline.run())

            session.execute(
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
            session.commit()

            CacheService.invalidate_business_cache(business_id)

            try:
                os.unlink(file_path)
            except:
                pass

            return {
                "status": "completed",
                "upload_id": upload_id,
                "stats": stats,
            }

        except Exception as e:
            session.execute(
                text("UPDATE uploaded_files SET status = 'failed', error_summary = :error WHERE id = :id"),
                {"id": upload_id, "error": str(e)}
            )
            session.commit()
            return {"status": "failed", "error": str(e)}


def run_cleanup_stale_uploads():
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
            file_path = Path(settings.UPLOAD_DIR) / upload.stored_filename
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


if settings.USE_CELERY:
    from celery import Task
    from app.celery_app import celery_app

    @celery_app.task(name="app.tasks.ingestion_tasks.process_upload")
    def process_upload_task(upload_id: str, business_id: str, column_mapping: dict):
        return run_process_upload(upload_id, business_id, column_mapping)

    @celery_app.task(name="app.tasks.ingestion_tasks.cleanup_stale_uploads")
    def cleanup_stale_uploads():
        return run_cleanup_stale_uploads()

    @celery_app.task(name="app.tasks.ingestion_tasks.nightly_recovery_match_scan")
    def nightly_recovery_match_scan():
        from app.database.connection import get_sync_session
        from app.services.recovery_match_matcher import run_nightly_recovery_match_scan
        import asyncio

        with get_sync_session() as session:
            return asyncio.run(run_nightly_recovery_match_scan(session))
