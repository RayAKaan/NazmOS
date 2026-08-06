"""Tests for Phase 2.3: inline ETL failure handling in upload confirm_mapping.

The non-Celery path of ``POST /api/v1/upload/{upload_id}/map`` runs the ETL
pipeline inline on the request.  Previously a pipeline exception left the
``uploaded_files`` row stuck in ``status='processing'`` forever (the parse file
was cleaned up in ``finally`` but the row was never marked failed).  This test
drives ``confirm_mapping`` directly against SQLite and asserts the row
transitions to ``failed`` with an ``error_summary``.
"""
import uuid
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Base, Business, UploadedFile, User
from app.routers.upload import confirm_mapping


def _register_now(engine) -> None:
    """Make NOW() available so Postgres-style SQL runs unmodified on SQLite."""
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "NOW", 0, lambda: datetime.now(timezone.utc).isoformat()
        )


@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _register_now(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


async def test_confirm_mapping_marks_upload_failed_on_pipeline_error(
    sqlite_session, monkeypatch
):
    user = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4()}@example.com",
        password_hash="x",
        full_name="Owner",
    )
    sqlite_session.add(user)
    await sqlite_session.commit()
    await sqlite_session.refresh(user)

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
        status="processing",
    )
    sqlite_session.add(business)
    sqlite_session.add(upload)
    await sqlite_session.commit()

    # Parse succeeds, but the ETL pipeline blows up.
    monkeypatch.setattr(
        "app.routers.upload.UploadService.parse_file",
        staticmethod(
            lambda *a, **k: pd.DataFrame(
                {"product_name": ["x"], "quantity": [1], "unit_price": [1.0]}
            )
        ),
    )

    class BoomPipeline:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self):
            raise RuntimeError("boom: ETL failure")

    monkeypatch.setattr("app.services.etl_pipeline.ETLPipeline", BoomPipeline)

    class FakeUser:
        id = user.id

    with pytest.raises(RuntimeError, match="boom"):
        await confirm_mapping(
            upload_id=str(upload.id),
            payload={"column_mapping": {"name": "product_name"}},
            background_tasks=None,
            business_id=str(business.id),
            current_user=FakeUser(),
            db=sqlite_session,
        )

    # Row must be marked failed, never left stuck in 'processing'.
    result = await sqlite_session.execute(
        select(UploadedFile)
        .where(UploadedFile.id == upload.id)
        .execution_options(populate_existing=True)
    )
    row = result.scalar_one()
    assert row.status == "failed"
    assert row.error_summary == "boom: ETL failure"
