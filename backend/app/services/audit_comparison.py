"""Audit 2.0 comparison (Phase 5, §12–14).

Classifies each finding relative to the previous audit window: NEW | PERSISTENT |
IMPROVING | WORSENING | RESOLVED | RECURRING. The comparison is deterministic:
findings are keyed by (domain, category, title); IMPROVING/WORSENING is determined by
whether the estimated financial impact fell/rose vs the previous window (a finding's
impact going down = improving, since findings represent problems). Recurrence reuses
`recurring_detection`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

COMPARISON_WINDOW_DAYS = 14
IMPACT_TOLERANCE = 0.10  # ±10% = "persistent" (no meaningful change)


def _key(domain: str, category: str, title: str) -> str:
    return f"{domain}|{category}|{(title or '').strip().lower()}"


async def compare_audits(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    """Classify current findings vs the previous comparison window."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=COMPARISON_WINDOW_DAYS)

    async def _fetch(since: datetime, until: datetime) -> dict[str, dict[str, Any]]:
        res = await db.execute(text("""
            SELECT domain, category, title, estimated_financial_impact_sar, status, id, created_at
            FROM findings
            WHERE business_id = :b AND created_at >= :since AND created_at < :until
              AND status NOT IN ('rejected', 'failed')
        """), {"b": str(business_id), "since": since, "until": until})
        out: dict[str, dict[str, Any]] = {}
        for r in res.fetchall():
            key = _key(r.domain, r.category, r.title)
            impact = float(r.estimated_financial_impact_sar or 0)
            # keep the most recent occurrence per key
            if key not in out or r.created_at > out[key]["created_at"]:
                out[key] = {
                    "id": str(r.id), "domain": r.domain, "category": r.category, "title": r.title,
                    "impact": impact, "status": r.status, "created_at": r.created_at,
                }
        return out

    current = await _fetch(cutoff, now)
    previous = await _fetch(cutoff - timedelta(days=COMPARISON_WINDOW_DAYS), cutoff)

    from app.services.recurring_detection import find_recurring_problems
    recurring = {_key(r["domain"], r["category"], r["title"]) for r in await find_recurring_problems(db, business_id)}

    classified = []
    for key, cur in current.items():
        prev = previous.get(key)
        if key in recurring:
            status = "recurring"
        elif prev is None:
            status = "new"
        else:
            prev_impact = prev["impact"]
            cur_impact = cur["impact"]
            if prev_impact == 0 and cur_impact == 0:
                status = "persistent"
            elif prev_impact == 0:
                status = "worsening"
            else:
                delta = (cur_impact - prev_impact) / prev_impact
                if abs(delta) <= IMPACT_TOLERANCE:
                    status = "persistent"
                elif delta < 0:
                    status = "improving"
                else:
                    status = "worsening"
        classified.append({
            "id": cur["id"],
            "domain": cur["domain"],
            "category": cur["category"],
            "title": cur["title"],
            "status": status,
            "current_impact_sar": cur["impact"],
            "previous_impact_sar": previous[key]["impact"] if key in previous else None,
            "recovered_sar": round(previous[key]["impact"] - cur["impact"], 2) if key in previous and status == "improving" else None,
        })

    # RESOLVED: previous findings whose key no longer appears in the current window.
    resolved = [
        {"domain": p["domain"], "category": p["category"], "title": p["title"], "impact_sar": p["impact"]}
        for key, p in previous.items() if key not in current
    ]

    return {
        "window_days": COMPARISON_WINDOW_DAYS,
        "findings": classified,
        "resolved": resolved,
        "counts": {
            "new": sum(1 for c in classified if c["status"] == "new"),
            "persistent": sum(1 for c in classified if c["status"] == "persistent"),
            "improving": sum(1 for c in classified if c["status"] == "improving"),
            "worsening": sum(1 for c in classified if c["status"] == "worsening"),
            "recurring": sum(1 for c in classified if c["status"] == "recurring"),
            "resolved": len(resolved),
        },
    }
