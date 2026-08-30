"""Recurring-problem detection (Phase 4, §23).

Detects findings that keep returning (fixed → returns → fixed → returns) and escalates
them, so NazmOS triggers deeper investigation instead of emitting the same recommendation
again. Deterministic: counts occurrences of the same (domain, category, entity) within a
window.
"""
from __future__ import annotations
from app.utils.clock import utcnow

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _iso(v: Any) -> str | None:
    """Dialect-safe timestamp serialization (SQLite returns str, Postgres returns datetime)."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return v.isoformat()

RECURRENCE_WINDOW_DAYS = 60
RECURRENCE_THRESHOLD = 3  # ≥3 occurrences in the window = recurring


async def find_recurring_problems(db: AsyncSession, business_id: UUID | str) -> list[dict[str, Any]]:
    """Return (domain, category, title, occurrences) for findings that recur within the window."""
    from datetime import datetime, timedelta, timezone
    cutoff = utcnow() - timedelta(days=RECURRENCE_WINDOW_DAYS)
    res = await db.execute(text("""
        SELECT domain, category, title, COUNT(*) AS occurrences,
               MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
        FROM findings
        WHERE business_id = :b AND created_at >= :cutoff
        GROUP BY domain, category, title
        HAVING COUNT(*) >= :threshold
        ORDER BY occurrences DESC
    """), {"b": str(business_id), "cutoff": cutoff, "threshold": RECURRENCE_THRESHOLD})

    out = []
    for r in res.fetchall():
        out.append({
            "domain": r.domain,
            "category": r.category,
            "title": r.title,
            "occurrences": r.occurrences,
            "first_seen": _iso(r.first_seen),
            "last_seen": _iso(r.last_seen),
            "escalation": (
                f"Recurring issue: appeared {r.occurrences} times in {RECURRENCE_WINDOW_DAYS} days. "
                "Previous interventions did not resolve the underlying cause — deeper investigation recommended."
            ),
        })
    return out
