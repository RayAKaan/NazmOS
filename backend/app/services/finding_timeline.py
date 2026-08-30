"""Finding decision timeline (Phase 7, §7).

Builds a concise, chronological, evidence-based timeline for a finding from the actual
records (Finding.status history is not stored, so the timeline is reconstructed from the
linked AgentAction / LearnedOutcome / ImpactLedger, plus the finding's own fields).

Events exposed: found → analyzed → recommended → approval-requested → approved/rejected →
executed/failed → verified → impact-measured → learned. Never exposes chain-of-thought.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return v.isoformat()


async def build_finding_timeline(db: AsyncSession, finding_id: UUID | str, business_id: UUID | str) -> list[dict[str, Any]]:
    """Return an ordered list of {step, label, at, detail} timeline events."""
    events: list[dict[str, Any]] = []

    # 1. Finding's own lifecycle (created → current status).
    f = await db.execute(text("""
        SELECT status, created_at, updated_at, confidence
        FROM findings WHERE id = :id AND business_id = :b
    """), {"id": str(finding_id), "b": str(business_id)})
    row = f.fetchone()
    if not row:
        return events

    events.append({"step": "found", "label": "Problem found", "at": _iso(row.created_at), "status": row.status})

    # 2. Actions linked to this finding (there may be several, §3).
    actions = await db.execute(text("""
        SELECT id, action_type, status, decision_note, outcome_json, applied_at, decided_at, created_at
        FROM agent_actions
        WHERE finding_id = :id AND business_id = :b
        ORDER BY created_at ASC
    """), {"id": str(finding_id), "b": str(business_id)})
    for a in actions.fetchall():
        outcome = a.outcome_json if isinstance(a.outcome_json, dict) else (json.loads(a.outcome_json) if a.outcome_json else {})
        executed = bool(outcome.get("executed")) if isinstance(outcome, dict) else False

        if a.status in ("pending_approval",):
            events.append({"step": "approval_requested", "label": "Approval requested",
                           "at": _iso(a.created_at), "action_id": str(a.id), "action_type": a.action_type})
        elif a.status == "rejected":
            events.append({"step": "rejected", "label": "Rejected", "at": _iso(a.decided_at),
                           "action_id": str(a.id), "rejection_reason": a.decision_note})
        elif a.status in ("approved", "executed", "auto_executed"):
            events.append({"step": "approved", "label": "Approved" if a.status != "auto_executed" else "Auto-executed",
                           "at": _iso(a.decided_at or a.applied_at), "action_id": str(a.id)})
            if executed:
                events.append({"step": "executed", "label": "Executed", "at": _iso(a.applied_at),
                               "action_id": str(a.id), "outcome": outcome})
            else:
                events.append({"step": "failed", "label": "Execution failed", "at": _iso(a.applied_at),
                               "action_id": str(a.id), "outcome": outcome})
        elif a.status == "failed":
            events.append({"step": "failed", "label": "Failed", "at": _iso(a.applied_at),
                           "action_id": str(a.id), "outcome": outcome})

    # 3. Verification + impact.
    impact = await db.execute(text("""
        SELECT actual_sar, verification, verified, note, occurred_at
        FROM impact_ledger
        WHERE finding_id = :id AND business_id = :b
        ORDER BY occurred_at ASC
    """), {"id": str(finding_id), "b": str(business_id)})
    for i in impact.fetchall():
        if i.verified:
            events.append({"step": "impact_measured", "label": "Impact measured",
                           "at": _iso(i.occurred_at), "actual_impact_sar": float(i.actual_sar or 0),
                           "verification": i.verification})

    # 4. Learned outcome.
    learned = await db.execute(text("""
        SELECT action_type, approval, rejection_reason, actual_impact_sar, confidence, created_at
        FROM learned_outcomes
        WHERE finding_id = :id AND business_id = :b
        ORDER BY created_at ASC
    """), {"id": str(finding_id), "b": str(business_id)})
    for l in learned.fetchall():
        events.append({"step": "learned", "label": "NazmOS learned",
                       "at": _iso(l.created_at), "action_type": l.action_type,
                       "approval": l.approval, "actual_impact_sar": float(l.actual_impact_sar or 0) if l.actual_impact_sar is not None else None})

    events.sort(key=lambda e: e.get("at") or "")
    return events
