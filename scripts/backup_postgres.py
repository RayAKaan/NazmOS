#!/usr/bin/env python3
"""Automated PostgreSQL backup for NazmOS.

Production methodology:
  - Backups are taken with pg_dump and compressed.
  - The resulting artifact is uploaded to the configured storage backend
    (local disk, S3, or MinIO) so it survives disk loss.
  - Old backups are pruned according to a retention policy.
  - A restore drill proves the latest backup can actually be restored:
    it restores into a throwaway database, validates row counts/schema, and
    drops the database. A failed drill exits non-zero so schedulers/CI go red.

Environment variables used:
  DATABASE_URL          PostgreSQL URL (postgresql+asyncpg://... supported)
  STORAGE_BACKEND       local | s3 | minio  (default: local)
  BACKUP_RETENTION_DAYS Number of daily backups to keep (default: 7)
  BACKUP_DIR            Local directory for backups (default: ./backups)
  STORAGE_BUCKET, STORAGE_ENDPOINT, STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY,
  STORAGE_PREFIX        Object-store settings (see app/services/storage.py)

Usage:
  python backup_postgres.py                  Take + store + prune a backup.
  python backup_postgres.py --restore-drill  Backup, then validate restorability.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote

# Allow importing app code for storage and config.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.storage import storage
from app.utils.logger import setup_logger

logger = setup_logger("backup")


def _pg_url_for_pg_dump(url: str) -> str:
    """Convert SQLAlchemy asyncpg URL into a libpq-compatible URL."""
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)


def _parse_pg_url(url: str) -> tuple:
    """Parse a libpq URL into (host, port, user, password, dbname)."""
    parsed = urlsplit(url)
    return (
        parsed.hostname or "localhost",
        parsed.port or 5432,
        unquote(parsed.username or "nazmos"),
        unquote(parsed.password or ""),
        parsed.path.lstrip("/") or "nazmos",
    )


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


def restore_drill(backup_file: Path | None = None) -> bool:
    """Restore the most recent backup into a throwaway DB and validate it.

    Runs three validation queries:
      1. Count of rows in the businesses table (must be > 0).
      2. Count of rows in the executed_actions table (must be >= 0; proves schema).
      3. SELECT 1 (proves connectivity).

    The temporary database is always dropped. This function never raises; a
    failed drill returns False and logs RESTORE_DRILL_FAIL.
    """
    db_url = os.environ.get("DATABASE_URL", "postgresql://nazmos:nazmos_dev@localhost:5432/nazmos")
    pg_url = _pg_url_for_pg_dump(db_url)
    host, port, user, password, _ = _parse_pg_url(pg_url)

    if backup_file is None:
        backup_dir = Path(os.environ.get("BACKUP_DIR", "./backups"))
        candidates = sorted(
            backup_dir.glob("nazmos_*.sql.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            logger.error("RESTORE_DRILL_FAIL", extra={"stage": "find_backup", "error": "no backup files found"})
            return False
        backup_file = candidates[0]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_db = f"nazmos_restore_drill_{timestamp}"
    env = os.environ.copy()
    env["PGPASSWORD"] = password

    def run(cmd: list) -> tuple:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    try:
        logger.info(
            "Restore drill starting",
            extra={"backup": str(backup_file), "target_db": target_db},
        )

        run(["dropdb", "--if-exists", "-h", host, "-p", str(port), "-U", user, target_db])
        code, _, err = run(["createdb", "-h", host, "-p", str(port), "-U", user, target_db])
        if code != 0:
            logger.error("RESTORE_DRILL_FAIL", extra={"stage": "createdb", "error": err})
            return False

        code, _, err = run([
            "pg_restore", "--no-owner", "--no-privileges", "--dbname", target_db,
            "-h", host, "-p", str(port), "-U", user, str(backup_file),
        ])
        if code not in (0, 1):
            logger.error("RESTORE_DRILL_FAIL", extra={"stage": "pg_restore", "error": err})
            return False
        if code == 1:
            logger.warning("pg_restore completed with benign warnings")

        counts: dict = {}
        ok = True
        for name, sql, min_value in (
            ("businesses", "SELECT COUNT(*) FROM businesses;", 0),
            ("executed_actions", "SELECT COUNT(*) FROM executed_actions;", -1),
            ("connectivity", "SELECT 1;", 0),
        ):
            code, out, err = run(["psql", "-h", host, "-p", str(port), "-U", user, "-d", target_db, "-tAc", sql])
            if code != 0:
                logger.error("RESTORE_DRILL_FAIL", extra={"stage": "validation", "query": name, "error": err})
                counts[name] = None
                ok = False
                continue
            try:
                value = int(out.strip())
            except ValueError:
                logger.error("RESTORE_DRILL_FAIL", extra={"stage": "validation", "query": name, "output": out})
                counts[name] = None
                ok = False
                continue
            counts[name] = value
            if value <= min_value:
                logger.error("RESTORE_DRILL_FAIL", extra={"stage": "validation", "query": name, "count": value})
                ok = False

        if ok:
            logger.info("RESTORE_DRILL_PASS", extra=counts)
            return True

        logger.error("RESTORE_DRILL_FAIL", extra=counts)
        return False

    except Exception as exc:
        logger.error("RESTORE_DRILL_FAIL", extra={"stage": "drill", "error": str(exc)})
        return False
    finally:
        try:
            run(["dropdb", "--if-exists", "-h", host, "-p", str(port), "-U", user, target_db])
        except Exception:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="NazmOS PostgreSQL backup tool")
    parser.add_argument(
        "--restore-drill",
        action="store_true",
        help="After taking the backup, restore it into a throwaway DB to validate restorability.",
    )
    args = parser.parse_args()

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

    if args.restore_drill:
        ok = restore_drill(local_path)
        if not ok:
            print("Restore drill FAILED — backup is not proven restorable.", file=sys.stderr)
            sys.exit(1)
        print("Restore drill PASSED — backup is restorable.")


if __name__ == "__main__":
    asyncio.run(main())
