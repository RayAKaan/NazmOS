"""Unit tests for backup service."""
import json
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from app.services.backup_service import create_backup, list_backups, get_backup, restore_dry_run, apply_retention_policy


@pytest.mark.asyncio
async def test_create_backup(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    db = MagicMock()

    async def _execute(stmt, params=None):
        res = MagicMock()
        res.fetchall = MagicMock(return_value=[MagicMock(_mapping={"id": str(uuid4()), "name": "Test"})])
        return res

    db.execute = AsyncMock(side_effect=_execute)
    result = await create_backup(db, name="test")
    assert result["ok"] is True
    assert result["tables_backed_up"] > 0
    assert os.path.exists(result["path"])


def test_list_and_get_backup(tmp_path):
    snapshot = {"metadata": {"name": "x"}, "data": {"items": [{"id": "1"}]}}
    path = tmp_path / "nazmos_backup_20260101_000000_x.json"
    path.write_text(json.dumps(snapshot))
    os.environ["BACKUP_DIR"] = str(tmp_path)
    backups = list_backups()
    assert len(backups) == 1
    loaded = get_backup(backups[0]["filename"])
    assert loaded["metadata"]["name"] == "x"


def test_restore_dry_run():
    snapshot = {"metadata": {"name": "x"}, "data": {"items": [{"id": "1"}, {"id": "2"}]}}
    result = restore_dry_run(snapshot)
    assert result["dry_run"] is True
    assert result["total_rows"] == 2


def test_retention_policy(tmp_path):
    os.environ["BACKUP_DIR"] = str(tmp_path)
    for i in range(5):
        (tmp_path / f"nazmos_backup_2026010{i}_000000_auto.json").write_text("{}")
    result = apply_retention_policy(max_backups=2)
    assert len(result["removed"]) == 3
    assert result["remaining"] == 2
