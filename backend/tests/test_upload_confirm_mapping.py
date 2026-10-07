"""Phase 2A: upload confirm_mapping marks a failed ingestion row as failed.

The router now dispatches ingestions through the single orchestration layer
(``OP_UPLOAD_INGEST``). With ``USE_TEMPORAL=False`` (local deterministic
runner) the ingestion body runs synchronously to completion on the request; a
pipeline failure must never leave the ``uploaded_files`` row stuck in
``status='processing'``.  This test drives ``confirm_mapping`` directly and
asserts the row transitions to ``failed`` with an ``error_summary``.

The activity opens its own sessions (a sync session plus a fresh async engine)
off ``settings.DATABASE_URL``, so the test points the whole app at a shared
file-backed SQLite database and patches the upload surface to inject failures.
"""
import uuid
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.models import Base, Business, UploadedFile, User
from app.routers.upload import confirm_mapping


def _register_now(sync_engine) -> None:
    """Register NOW() so the app's Postgres-style SQL runs unmodified on SQLite."""
    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "NOW", 0, lambda: datetime.now(timezone.utc).isoformat()
        )


@pytest.fixture
def upload_db(tmp_path, monkeypatch):
    """File-backed SQLite DB + app wiring so worker-thread sessions see shared data."""
    import asyncio

    from app.config import get_settings
    from app.database import connection as conn_mod

    url = f"sqlite+aiosqlite:///{tmp_path / 'upload_test.db'}"

    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    _register_now(engine.sync_engine)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())

    # Route every session the activity path opens at the shared file DB.
    monkeypatch.setattr(conn_mod, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(conn_mod, "_is_sqlite", True)

    def _sync_engine():
        engine_sync = create_engine(
            url.replace("+aiosqlite", ""),
            connect_args={"check_same_thread": False},
        )
        _register_now(engine_sync)
        return engine_sync

    monkeypatch.setattr(conn_mod, "_get_sync_engine", _sync_engine)

    settings = get_settings()
    monkeypatch.setattr(settings, "USE_TEMPORAL", False)  # exercise the local runner
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    yield session_factory

    asyncio.run(engine.dispose())


async def test_confirm_mapping_marks_upload_failed_on_pipeline_error(
    upload_db, monkeypatch, tmp_path
):
    async with upload_db() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"owner-{uuid.uuid4()}@example.com",
            password_hash="x",
            full_name="Owner",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        business = Business(
            id=uuid.uuid4(),
            name="Test Biz",
            type="baqala",
            owner_id=user.id,
        )
        upload = UploadedFile(
            id=uuid.uuid4(),
            business_id=business.id,
            uploaded_by=user.id,
            stored_filename="inventory.csv",
            original_filename="inventory.csv",
            file_type="csv",
            file_size_bytes=100,
            mime_type="text/csv",
            sha256_hash="abc123",
            status="uploaded",
        )
        db.add(business)
        db.add(upload)
        await db.commit()

        (tmp_path / "inventory.csv").write_text(
            "product_name,quantity,unit_price\nx,1,1.0", encoding="utf-8"
        )

        # Parsing is no longer the truth-producing step: confirm_mapping dispatches
        # the canonical Orbit ingestion operation. Inject the failure at that
        # canonical boundary so the test verifies the actual Phase 1 failure path.
        async def boom_ingest(*args, **kwargs):
            raise RuntimeError("boom: ETL failure")

        monkeypatch.setattr(
            "app.services.orbit.ingestion.service.ingest_and_project",
            boom_ingest,
        )

        class FakeUser:
            id = user.id

        resp = await confirm_mapping(
            upload_id=str(upload.id),
            payload={"column_mapping": {"name": "product_name"}},
            business_id=str(business.id),
            current_user=FakeUser(),
            db=db,
        )

        # Unified contract: the local runner completed the (failed) ingestion.
        assert resp["status"] == "failed"
        assert resp["task_id"] == f"upload-{upload.id}"
        assert resp["upload_id"] == str(upload.id)

        # Row must be marked failed, never left stuck in 'processing'.
        result = await db.execute(
            select(UploadedFile)
            .where(UploadedFile.id == upload.id)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one()
        assert row.status == "failed"
        assert row.error_summary == "boom: ETL failure"