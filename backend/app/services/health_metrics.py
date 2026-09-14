"""NazmOS canonical health metrics — single source of truth for health scores.

Every surface that renders a health score imports from here so "health" is one
of exactly two explicitly-named metrics and nothing else:

* ``inventory_health_score`` — inventory composite (canonical dashboard health).
  Items bucket (critical/low/healthy) drive 40 pts, stuck capital 30 pts, trend
  20 pts, data 10 pts.  Delegates to ``analytics_service.calculate_health_score``.

* ``findings_health_score`` (+ breakdown/trend) — severity-penalty business
  health: ``100 - (12 * critical + 6 * high + 2 * medium)``; low/info findings
  carry no penalty.  Traceable to ``findings`` rows per dimension.

These are intentionally different metrics: the dashboard shows inventory health;
the weekly report shows findings health.  Consumers must label which one they
render (payloads include ``metric`` and ``basis`` keys).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Findings-based health constants
# ---------------------------------------------------------------------------

FINDINGS_SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 12,
    "high": 6,
    "medium": 2,
    "low": 0,
    "info": 0,
}

# Findings that are resolved or out-of-scope never drag health.
EXCLUDED_FINDING_STATUSES = ("rejected", "failed", "verified")

_ACTIVE_CLAUSE = "status NOT IN ('rejected', 'failed', 'verified')"

# ---------------------------------------------------------------------------
# Domain → dashboard dimension mapping (shared by breakdown)
# ---------------------------------------------------------------------------

DOMAIN_DIMENSION = {
    "money_audit": "margins",
    "inventory": "inventory",
    "recovery_match": "inventory",
    "compliance": "compliance",
    "procurement": "procurement",
    "cash": "cash",
    "sales": "sales",
}

DIMENSIONS = [
    "inventory",
    "margins",
    "procurement",
    "cash",
    "sales",
    "compliance",
    "operations",
]


def _findings_penalty(rows: list[Any]) -> tuple[int, dict[str, int]]:
    """Compute severity penalty + per-severity counts."""
    counts: dict[str, int] = {sev: 0 for sev in FINDINGS_SEVERITY_WEIGHTS}
    penalty = 0
    for row in rows:
        sev = getattr(row, "severity", None)
        n = int(getattr(row, "n", 0) or 0)
        if sev in FINDINGS_SEVERITY_WEIGHTS:
            counts[sev] = n
            penalty += FINDINGS_SEVERITY_WEIGHTS[sev] * n
    return penalty, counts


def _penalty_to_score(penalty: int) -> int:
    return max(0, 100 - penalty)


# ---------------------------------------------------------------------------
# Inventory health (dashboard canonical — delegated, not duplicated)
# ---------------------------------------------------------------------------


async def inventory_health_score(db: AsyncSession, business_id: UUID | str) -> int:
    """Canonical inventory-based business health (dashboard KPI).

    Delegates to ``analytics_service.calculate_health_score`` so there is
    exactly one implementation of this composite.
    """
    from app.services.analytics_service import calculate_health_score

    return await calculate_health_score(db, business_id)


# ---------------------------------------------------------------------------
# Findings health (weekly / audit-report canonical)
# ---------------------------------------------------------------------------


async def findings_health_score(
    db: AsyncSession,
    business_id: UUID | str,
) -> dict[str, Any]:
    """Severity-penalty health: ``100 - (12*critical + 6*high + 2*medium)``.

    Returns ``overall_health`` plus metadata so consumers can label the metric.
    """
    rows = await db.execute(
        text(
            f"SELECT severity, COUNT(*) AS n "
            f"FROM findings "
            f"WHERE business_id = :b AND {_ACTIVE_CLAUSE} "
            f"GROUP BY severity"
        ),
        {"b": str(business_id)},
    )
    penalty, counts = _findings_penalty(rows.fetchall())
    return {
        "overall_health": _penalty_to_score(penalty),
        "metric": "findings_health",
        "basis": "100 - (12*critical + 6*high + 2*medium) severity-weighted penalties",
        "formula": {
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "info": counts["info"],
            "penalty": penalty,
        },
    }


async def findings_health_breakdown(
    db: AsyncSession,
    business_id: UUID | str,
) -> dict[str, Any]:
    """Findings health broken into traceable dimensions.

    Same severity weights as ``findings_health_score``; each dimension's score
    is ``100 - dimension_penalty``.
    """
    rows = await db.execute(
        text(
            f"SELECT domain, severity, COUNT(*) AS n "
            f"FROM findings "
            f"WHERE business_id = :b AND {_ACTIVE_CLAUSE} "
            f"GROUP BY domain, severity"
        ),
        {"b": str(business_id)},
    )

    dim_penalty: dict[str, int] = {d: 0 for d in DIMENSIONS}
    dim_counts: dict[str, int] = {d: 0 for d in DIMENSIONS}
    for r in rows.fetchall():
        dim = DOMAIN_DIMENSION.get(r.domain, "operations")
        w = FINDINGS_SEVERITY_WEIGHTS.get(r.severity, 0)
        dim_penalty[dim] += w * int(r.n)
        dim_counts[dim] += int(r.n)

    overall = await findings_health_score(db, business_id)

    dimensions = [
        {
            "dimension": d,
            "score": _penalty_to_score(dim_penalty[d]),
            "findings": dim_counts[d],
        }
        for d in DIMENSIONS
    ]

    return {
        "overall_health": overall["overall_health"],
        "metric": overall["metric"],
        "basis": overall["basis"],
        "dimensions": dimensions,
    }


async def findings_health_trend(
    db: AsyncSession,
    business_id: UUID | str,
) -> dict[str, Any]:
    """Current-week vs previous-week findings health trend."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    async def _score(since: datetime, until: datetime) -> int:
        rows = await db.execute(
            text(
                f"SELECT severity, COUNT(*) AS n "
                f"FROM findings "
                f"WHERE business_id = :b "
                f"AND created_at >= :since AND created_at < :until "
                f"AND {_ACTIVE_CLAUSE} "
                f"GROUP BY severity"
            ),
            {"b": str(business_id), "since": since, "until": until},
        )
        penalty, _counts = _findings_penalty(rows.fetchall())
        return _penalty_to_score(penalty)

    current = await _score(week_ago, now)
    previous = await _score(two_weeks_ago, week_ago)
    delta = current - previous

    return {
        "current_health": current,
        "previous_health": previous,
        "metric": "findings_health",
        "trend": "up" if delta > 0 else "down" if delta < 0 else "flat",
        "delta": delta,
        "note": "Health is derived from finding severity within each window; every score is traceable to findings.",
        "basis": "100 - severity penalty per 7-day window",
    }
