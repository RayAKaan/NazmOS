"""Database backup and restore-drill service.

Exports key tables to JSON snapshots stored on the configured storage backend
(local disk in dev, S3/MinIO in production). Supports restore dry-runs and a
simple retention policy.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Tables critical for merchant operations and compliance.
BACKUP_TABLES = [
    "users",
    "businesses",
    "organizations",
    "team_members",
    "categories",
    "items",
    "inventory",
    "transactions",
    "daily_summaries",
    "uploaded_files",
    "chat_sessions",
    "chat_messages",
    "forecast_cache",
    "decision_log",
    "agent_actions",
    "autonomy_policies",
    "money_audits",
    "money_audit_actions",
    "purchase_orders",
    "recovery_match_settings",
    "stock_recovery_listings",
    "stock_recovery_matches",
    "partners",
    "partner_referrals",
    "events",
    "business_memory",
    "intelligence_decisions",
    "execution_jobs",
]


def _backup_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", "backups"))


def _snapshot_path(name: str | None = None) -> Path:
    backup = _backup_dir()
    backup.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"nazmos_backup_{timestamp}_{name or 'auto'}.json"
    return backup / filename


async def create_backup(
    db: AsyncSession,
    name: str | None = None,
    tables: list[str] | None = None,
) -> dict[str, Any]:
    """Create a JSON snapshot of selected tables."""
    tables = tables or BACKUP_TABLES
    snapshot: dict[str, Any] = {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "name": name or "auto",
            "tables": tables,
            "version": "1",
        },
        "data": {},
    }

    for table in tables:
        try:
            result = await db.execute(text(f"SELECT * FROM {table}"))  # nosec B608
            rows = [dict(r._mapping) for r in result.fetchall()]
            snapshot["data"][table] = rows
        except Exception as exc:
            snapshot["data"][table] = {"error": str(exc)}

    path = _snapshot_path(name)
    path.write_text(json.dumps(snapshot, default=str, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "tables_backed_up": len(tables),
        "row_count": sum(len(v) for v in snapshot["data"].values() if isinstance(v, list)),
    }


def list_backups() -> list[dict[str, Any]]:
    backup = _backup_dir()
    if not backup.exists():
        return []
    files = sorted(backup.glob("nazmos_backup_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for f in files
    ]


def get_backup(filename: str) -> dict[str, Any] | None:
    path = _backup_dir() / filename
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def restore_dry_run(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Summarize what a restore would do without touching the database."""
    data = snapshot.get("data", {})
    summary: dict[str, Any] = {}
    total_rows = 0
    for table, rows in data.items():
        if isinstance(rows, list):
            summary[table] = len(rows)
            total_rows += len(rows)
        else:
            summary[table] = rows
    return {
        "dry_run": True,
        "metadata": snapshot.get("metadata"),
        "tables": list(summary.keys()),
        "row_counts": summary,
        "total_rows": total_rows,
        "warnings": [
            "Restore would truncate existing table data before insert.",
            "Run in a transaction and verify row counts before committing.",
        ],
    }


def apply_retention_policy(max_backups: int = 30) -> dict[str, Any]:
    """Delete oldest backups beyond max_backups."""
    backups = list_backups()
    removed: list[str] = []
    if len(backups) > max_backups:
        for old in backups[max_backups:]:
            try:
                Path(old["path"]).unlink()
                removed.append(old["filename"])
            except Exception:
                continue
    return {"removed": removed, "remaining": len(backups) - len(removed)}


async def restore_table(
    db: AsyncSession,
    table: str,
    rows: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Restore a single table from a snapshot. Dry-run returns the plan."""
    if dry_run:
        return {"table": table, "dry_run": True, "rows_to_insert": len(rows)}

    # Naive restore: clear and insert. Production should use COPY/upsert.
    await db.execute(text(f"DELETE FROM {table}"))  # nosec B608
    inserted = 0
    for row in rows:
        columns = list(row.keys())
        values = [row[c] for c in columns]
        placeholders = ", ".join(f":c{i}" for i in range(len(columns)))
        cols = ", ".join(columns)
        stmt = text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})")  # nosec B608
        params = {f"c{i}": v for i, v in enumerate(values)}
        await db.execute(stmt, params)
        inserted += 1
    return {"table": table, "dry_run": False, "rows_inserted": inserted}
