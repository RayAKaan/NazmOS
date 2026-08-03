#!/usr/bin/env python3
"""Automated PostgreSQL backup for NazmOS.

Production methodology:
  - Backups are taken with pg_dump and compressed.
  - The resulting artifact is uploaded to the configured storage backend
    (local disk, S3, or MinIO) so it survives disk loss.
  - Old backups are pruned according to a retention policy.
  - A restore drill should be run periodically; this script only produces the
    backup artifact, it does not prove it can be restored.

Environment variables used:
  DATABASE_URL          PostgreSQL URL (postgresql+asyncpg://... supported)
  STORAGE_BACKEND       local | s3 | minio  (default: local)
  BACKUP_RETENTION_DAYS Number of daily backups to keep (default: 7)
  BACKUP_DIR            Local directory for backups (default: ./backups)
  STORAGE_BUCKET, STORAGE_ENDPOINT, STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY,
  STORAGE_PREFIX        Object-store settings (see app/services/storage.py)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow importing app code for storage and config.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.storage import storage
from app.utils.logger import setup_logger

logger = setup_logger("backup")


def _pg_url_for_pg_dump(url: str) -> str:
    """Convert SQLAlchemy asyncpg URL into a libpq-compatible URL."""
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


def _run_pg_dump(target_path: Path) -> None:
    db_url = os.environ.get("DATABASE_URL", "postgresql://nazmos:nazmos_dev@localhost:5432/nazmos")
    pg_url = _pg_url_for_pg_dump(db_url)

    target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Starting PostgreSQL backup", extra={"target": str(target_path)})

    # Use pg_dump's built-in compression; requires pg_dump in PATH.
    cmd = ["pg_dump", "-Fc", "-Z", "9", "--verbose", "--no-owner", "--no-privileges", "-f", str(target_path), pg_url]

    env = os.environ.copy()
    # pg_dump with a connection URL does not need PGPASSWORD, but libpq-based
    # password prompts would hang. Force no password prompt.
    env["PGPASSWORD"] = env.get("PGPASSWORD", "")

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("pg_dump failed", extra={"stderr": result.stderr, "stdout": result.stdout})
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    logger.info("pg_dump completed", extra={"size_bytes": target_path.stat().st_size})


def _prune_old_backups(backup_dir: Path, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for path in backup_dir.glob("nazmos_*.sql.gz"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                path.unlink()
                logger.info("Pruned old backup", extra={"file": path.name})
        except Exception as exc:
            logger.warning("Failed to prune backup", extra={"file": path.name, "error": str(exc)})


async def main() -> None:
    backup_dir = Path(os.environ.get("BACKUP_DIR", "./backups"))
    retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    local_name = f"nazmos_{timestamp}.sql.gz"
    local_path = backup_dir / local_name

    _run_pg_dump(local_path)

    # Upload to configured object store (defaults to local disk / backup_dir).
    with open(local_path, "rb") as f:
        content = f.read()

    stored_uri = await storage.store(local_name, content, content_type="application/gzip")
    logger.info("Backup stored", extra={"stored_uri": stored_uri, "local_path": str(local_path)})

    _prune_old_backups(backup_dir, retention_days)

    print(f"Backup completed: {stored_uri}")


if __name__ == "__main__":
    asyncio.run(main())
