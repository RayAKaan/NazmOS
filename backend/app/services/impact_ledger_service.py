"""Impact Ledger service (Phase 2, brief §10–11).

The canonical mechanism for recording value NazmOS created. Every record carries
a verification status that is explicit about whether the figure is ESTIMATED or
OBSERVED — estimates are never represented as realized revenue (§10).

This feeds the Dashboard, Finding detail, action history, and merchant ROI.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return v.isoformat()


async def record_impact(
    db: AsyncSession,
    business_id: UUID | str,
    impact_type: str,
    amount_sar: float,
    *,
    finding_id: UUID | str | None = None,
    agent_action_id: UUID | str | None = None,
    baseline_sar: float | None = None,
    expected_sar: float | None = None,
    actual_sar: float | None = None,
    verified: bool = False,
    verification: str = "estimated",
    attribution: str = "estimated",
    evidence: dict[str, Any] | None = None,
    note: str | None = None,
    source: str = "manual",
    commit: bool = True,
) -> UUID:
    """Append a ledger entry. `verification` must be one of pending|estimated|observed.
    `attribution` is one of direct|partial|business_level|estimated|unattributable (§5)."""
    import uuid
    from datetime import datetime, timezone
    entry_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO impact_ledger
            (id, business_id, finding_id, agent_action_id, impact_type, amount_sar,
             baseline_sar, expected_sar, actual_sar, verification, verified, attribution,
             evidence, note, source, created_at)
        VALUES
            (:id, :b, :fid, :aid, :type, :amount, :baseline, :expected, :actual,
             :verification, :verified, :attribution, CAST(:evidence AS JSON), :note, :source, :now)
    """), {
        "id": str(entry_id),
        "b": str(business_id),
        "fid": str(finding_id) if finding_id else None,
        "aid": str(agent_action_id) if agent_action_id else None,
        "type": impact_type,
        "amount": amount_sar,
        "baseline": baseline_sar,
        "expected": expected_sar,
        "actual": actual_sar,
        "verification": verification,
        "verified": bool(verified),
        "attribution": attribution,
        "evidence": _json(evidence or {}),
        "note": note,
        "source": source,
        "now": datetime.now(timezone.utc),
    })
    if commit:
        await db.commit()
    return entry_id


async def record_finding_verification(
    db: AsyncSession,
    business_id: UUID | str,
    finding_id: UUID | str,
    *,
    impact_type: str,
    actual_impact_sar: float | None,
    baseline_sar: float | None = None,
    observed: bool = False,
    note: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Record a verification result on both the Finding and the Impact Ledger (single
    source of IMPACT — §10). `observed=True` marks the figure as measured from data."""
    from app.services.finding_service import verify_finding

    verification = "observed" if observed else "estimated"
    await record_impact(
        db,
        business_id,
        impact_type,
        actual_impact_sar or 0.0,
        finding_id=finding_id,
        baseline_sar=baseline_sar,
        actual_sar=actual_impact_sar,
        verified=observed,
        verification=verification,
        note=note,
        source="verification",
        commit=False,
    )
    result = await verify_finding(
        db, finding_id, verified=True, actual_impact_sar=actual_impact_sar, note=note, commit=False
    )
    if commit:
        await db.commit()
    return result


async def total_impact(
    db: AsyncSession,
    business_id: UUID | str,
    *,
    observed_only: bool = False,
) -> dict[str, Any]:
    """Aggregate the impact ledger for the merchant ROI / Dashboard IMPACT section."""
    where = "business_id = :b"
    params: dict[str, Any] = {"b": str(business_id)}
    if observed_only:
        where += " AND verified = true"
    res = await db.execute(text(f"""
        SELECT impact_type,
               COALESCE(SUM(amount_sar), 0) AS total_sar,
               COUNT(*) AS entries,
               COALESCE(SUM(CASE WHEN verified THEN amount_sar ELSE 0 END), 0) AS observed_sar,
               COALESCE(SUM(CASE WHEN NOT verified THEN amount_sar ELSE 0 END), 0) AS estimated_sar
        FROM impact_ledger
        WHERE {where}
        GROUP BY impact_type
        ORDER BY total_sar DESC
    """), params)  # nosec B608
    by_type = [dict(r._mapping) for r in res.fetchall()]

    totals = await db.execute(text(f"""
        SELECT COALESCE(SUM(amount_sar), 0) AS total_sar,
               COALESCE(SUM(CASE WHEN verified THEN amount_sar ELSE 0 END), 0) AS observed_sar,
               COALESCE(SUM(CASE WHEN NOT verified THEN amount_sar ELSE 0 END), 0) AS estimated_sar
        FROM impact_ledger WHERE {where}
    """), params)  # nosec B608
    t = dict(totals.fetchone()._mapping)

    return {
        "total_sar": float(t["total_sar"]),
        "observed_sar": float(t["observed_sar"]),
        "estimated_sar": float(t["estimated_sar"]),
        "by_type": [
            {
                "impact_type": r["impact_type"],
                "total_sar": float(r["total_sar"]),
                "observed_sar": float(r["observed_sar"]),
                "estimated_sar": float(r["estimated_sar"]),
                "entries": r["entries"],
            }
            for r in by_type
        ],
    }


async def list_ledger(
    db: AsyncSession,
    business_id: UUID | str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    res = await db.execute(text("""
        SELECT id, impact_type, amount_sar, baseline_sar, expected_sar, actual_sar,
               verification, verified, attribution, evidence, note, source, occurred_at,
               finding_id, agent_action_id
        FROM impact_ledger
        WHERE business_id = :b
        ORDER BY occurred_at DESC, created_at DESC
        LIMIT :lim
    """), {"b": str(business_id), "lim": limit})
    out = []
    for r in res.fetchall():
        out.append({
            "id": str(r.id),
            "impact_type": r.impact_type,
            "amount_sar": float(r.amount_sar or 0),
            "baseline_sar": float(r.baseline_sar) if r.baseline_sar is not None else None,
            "expected_sar": float(r.expected_sar) if r.expected_sar is not None else None,
            "actual_sar": float(r.actual_sar) if r.actual_sar is not None else None,
            "verification": r.verification,
            "verified": bool(r.verified),
            "attribution": r.attribution,
            "evidence": r.evidence if isinstance(r.evidence, dict) else json.loads(r.evidence or "{}"),
            "note": r.note,
            "source": r.source,
            "occurred_at": _iso(r.occurred_at),
            "finding_id": str(r.finding_id) if r.finding_id else None,
            "agent_action_id": str(r.agent_action_id) if r.agent_action_id else None,
        })
    return out


async def finding_observed_impact(
    db: AsyncSession,
    business_id: UUID | str,
    finding_id: UUID | str,
) -> dict[str, Any]:
    """Per-finding observed impact (§2): the sum of verified, directly-attributed entries for
    this finding. Never conflated with business-level totals."""
    res = await db.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN verified AND attribution = 'direct' THEN amount_sar ELSE 0 END), 0) AS direct_sar,
            COALESCE(SUM(CASE WHEN verified AND attribution = 'partial' THEN amount_sar ELSE 0 END), 0) AS partial_sar,
            COALESCE(SUM(CASE WHEN verified AND attribution = 'business_level' THEN amount_sar ELSE 0 END), 0) AS business_level_sar,
            COALESCE(SUM(CASE WHEN verified THEN amount_sar ELSE 0 END), 0) AS total_verified_sar,
            COUNT(*) AS entries
        FROM impact_ledger
        WHERE business_id = :b AND finding_id = :fid
    """), {"b": str(business_id), "fid": str(finding_id)})
    r = res.fetchone()
    return {
        "finding_id": str(finding_id),
        "direct_sar": float(r.direct_sar or 0),
        "partial_sar": float(r.partial_sar or 0),
        "business_level_sar": float(r.business_level_sar or 0),
        "total_verified_sar": float(r.total_verified_sar or 0),
        "entries": int(r.entries or 0),
    }
