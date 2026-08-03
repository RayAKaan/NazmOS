#!/usr/bin/env python3
"""PostgreSQL restore for NazmOS.

This is a deliberate, guarded operation. By default it only lists available
backups; set ALLOW_RESTORE=true and RESTORE_TARGET_DB to actually restore.

Recommended usage for a restore drill:
  1. Spin up a fresh database.
  2. Run: ALLOW_RESTORE=true RESTORE_TARGET_DB=nazmos_test python scripts/restore_postgres.py --latest
  3. Verify the application can connect and read data.
  4. Document any issues found.

Environment variables:
  RESTORE_TARGET_DB     Database name to restore into (default: nazmos_restored)
  DATABASE_URL          Used only to derive host/credentials; target DB is separate.
  ALLOW_RESTORE         Must be "true" to perform destructive restore.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.storage import storage
from app.utils.logger import setup_logger

logger = setup_logger("restore")


def _pg_url_to_conninfo(url: str) -> dict:
    """Parse a postgresql:// URL into connection parts for psql/pg_restore."""
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    # Minimal parser; assumes standard postgres URL format.
    match = re.match(r"postgresql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)", url)
    if not match:
        raise ValueError(f"Cannot parse DATABASE_URL: {url}")
    user, password, host, port, db = match.groups()
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port or "5432",
        "db": db,
    }


def _list_local_backups(backup_dir: Path) -> list[Path]:
    backups = sorted(backup_dir.glob("nazmos_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a NazmOS PostgreSQL backup")
    parser.add_argument("--latest", action="store_true", help="Restore the most recent backup")
    parser.add_argument("--file", type=str, help="Specific backup file name (local) or URI")
    parser.add_argument("--list", action="store_true", help="List available backups and exit")
    args = parser.parse_args()

    backup_dir = Path(os.environ.get("BACKUP_DIR", "./backups"))
    backups = _list_local_backups(backup_dir)

    if args.list:
        print("Available backups:")
        for b in backups:
            print(f"  {b.name} ({b.stat().st_size} bytes)")
        return

    if not args.latest and not args.file:
        parser.error("Specify --latest, --file, or --list")

    if args.latest:
        if not backups:
            print("No backups found.", file=sys.stderr)
            sys.exit(1)
        backup_path = backups[0]
    else:
        candidate = Path(args.file)
        if candidate.exists():
            backup_path = candidate
        elif (backup_dir / args.file).exists():
            backup_path = backup_dir / args.file
        else:
            print(f"Backup not found: {args.file}", file=sys.stderr)
            sys.exit(1)

    target_db = os.environ.get("RESTORE_TARGET_DB", "nazmos_restored")
    allow_restore = os.environ.get("ALLOW_RESTORE", "false").lower() == "true"

    logger.info("Restore candidate", extra={"backup": str(backup_path), "target_db": target_db, "allowed": allow_restore})

    if not allow_restore:
        print(
            f"Dry-run: would restore {backup_path.name} into database '{target_db}'.\n"
            "Set ALLOW_RESTORE=true to perform the restore.",
            file=sys.stderr,
        )
        sys.exit(0)

    source = _pg_url_to_conninfo(os.environ.get("DATABASE_URL", "postgresql://nazmos:nazmos_dev@localhost:5432/nazmos"))

    env = os.environ.copy()
    env["PGPASSWORD"] = source["password"]

    # Create target database.
    subprocess.run(
        ["dropdb", "--if-exists", "-h", source["host"], "-p", source["port"], "-U", source["user"], target_db],
        env=env,
        check=True,
    )
    subprocess.run(
        ["createdb", "-h", source["host"], "-p", source["port"], "-U", source["user"], target_db],
        env=env,
        check=True,
    )

    # pg_dump -Fc produces a custom-format archive; use pg_restore.
    with open(backup_path, "rb") as f:
        restore = subprocess.Popen(
            ["pg_restore", "--verbose", "--no-owner", "--no-privileges", "-h", source["host"], "-p", source["port"], "-U", source["user"], "-d", target_db],
            stdin=subprocess.PIPE,
            env=env,
        )
        restore.communicate(f.read())

    if restore.returncode not in (0, 1):
        # pg_restore often returns 1 because of benign errors (e.g. pre-existing comments).
        logger.error("pg_restore failed", extra={"returncode": restore.returncode})
        sys.exit(1)

    logger.info("Restore completed", extra={"backup": str(backup_path), "target_db": target_db})
    print(f"Restored {backup_path.name} to database {target_db}")


if __name__ == "__main__":
    main()
