"""Canonical Finding service (Phase 1).

Findings are the umbrella over MoneyAuditAction and AgentAction. This module owns:
  - creating findings,
  - advancing the explicit FindingStatus lifecycle (brief §4),
  - recording verification / actual impact (brief §10: AUDIT → FINDING → ACTION →
    APPROVAL → EXECUTION → VERIFICATION → IMPACT).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


# Ordered lifecycle — statuses may only advance forward, except to FAILED.
_FINDING_FLOW = {
    "detected": "analyzed",
    "analyzed": "recommended",
    "recommended": "awaiting_approval",
    "awaiting_approval": "approved",  # rejected is a terminal branch
    "approved": "executing",
    "executing": "completed",
    "completed": "verified",
}


async def create_finding(db: AsyncSession, business_id: UUID | str, **fields: Any) -> UUID:
    finding_id = UUID(fields.pop("id", None) or _new_uuid())
    now = datetime.now(timezone.utc)
    await db.execute(text("""
        INSERT INTO findings
            (id, business_id, domain, category, severity, title, explanation, evidence,
             affected_entities, estimated_financial_impact_sar, confidence, recommended_action,
             action_risk, status, source, created_at, updated_at)
        VALUES
            (:id, :b, :domain, :category, :severity, :title, :explanation,
             CAST(:evidence AS JSON), CAST(:entities AS JSON), :impact, :confidence,
             CAST(:recommended AS JSON), :risk, 'detected', :source, :now, :now)
    """), {
        "id": str(finding_id),
        "b": str(business_id),
        "domain": fields.get("domain", "general"),
        "category": fields.get("category", "general"),
        "severity": fields.get("severity", "medium"),
        "title": fields.get("title", "Finding"),
        "explanation": fields.get("explanation"),
        "evidence": _json(fields.get("evidence") or {}),
        "entities": _json(fields.get("affected_entities") or []),
        "impact": fields.get("estimated_financial_impact_sar"),
        "confidence": fields.get("confidence"),
        "recommended": _json(fields.get("recommended_action") or {}),
        "risk": fields.get("action_risk", "low"),
        "source": fields.get("source", "manual"),
        "now": now,
    })
    return finding_id


def _new_uuid() -> UUID:
    import uuid
    return uuid.uuid4()


async def advance_status(db: AsyncSession, finding_id: UUID | str, to_status: str, commit: bool = True) -> dict[str, Any]:
    """Move a finding along the lifecycle (or to a terminal rejected/failed state)."""
    res = await db.execute(text("SELECT status FROM findings WHERE id = :id"), {"id": str(finding_id)})
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Finding not found"}
    current = row.status

    allowed_next = _FINDING_FLOW.get(current)
    terminal = to_status in {"rejected", "failed"}
    if not terminal and allowed_next != to_status:
        return {"ok": False, "reason": f"Cannot move {current} -> {to_status}; expected {allowed_next}"}

    now = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE findings
        SET status = :s,
            resolved_at = CASE WHEN :s IN ('verified', 'rejected', 'failed') THEN :now ELSE resolved_at END,
            updated_at = :now
        WHERE id = :id
    """), {"id": str(finding_id), "s": to_status, "now": now})
    if commit:
        await db.commit()
    return {"ok": True, "finding_id": str(finding_id), "status": to_status}


async def verify_finding(
    db: AsyncSession,
    finding_id: UUID | str,
    verified: bool,
    actual_impact_sar: float | None = None,
    note: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Record the verification result + actual (revised) financial impact (brief §10)."""
    res = await db.execute(text("SELECT id FROM findings WHERE id = :id"), {"id": str(finding_id)})
    if not res.fetchone():
        return {"ok": False, "reason": "Finding not found"}

    now = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE findings
        SET verification_result = CAST(:vr AS JSON),
            status = CASE WHEN :verified THEN 'verified' ELSE 'failed' END,
            resolved_at = :now,
            updated_at = :now
        WHERE id = :id
    """), {
        "id": str(finding_id),
        "verified": bool(verified),
        "vr": _json({"verified": bool(verified), "actual_impact_sar": actual_impact_sar, "note": note}),
        "now": now,
    })
    if commit:
        await db.commit()
    return {"ok": True, "finding_id": str(finding_id), "verified": bool(verified)}


async def get_finding(db: AsyncSession, finding_id: UUID | str, business_id: UUID | str | None = None) -> dict[str, Any] | None:
    """Full finding detail (brief §20): problem, evidence, impact, reasoning, action,
    approval, execution, verification, and actual impact."""
    res = await db.execute(text("""
        SELECT f.*, a.status AS action_status, a.outcome_json, a.applied_at,
               l.actual_sar AS observed_impact_sar
        FROM findings f
        LEFT JOIN agent_actions a ON a.id = f.agent_action_id
        LEFT JOIN impact_ledger l ON l.finding_id = f.id
        WHERE f.id = :id
    """), {"id": str(finding_id)})
    row = res.fetchone()
    if not row:
        return None
    if business_id is not None and str(row.business_id) != str(business_id):
        return None

    return {
        "id": str(row.id),
        "domain": row.domain,
        "category": row.category,
        "severity": row.severity,
        "status": row.status,
        "title": row.title,
        "problem": row.title,
        "explanation": row.explanation,
        "evidence": row.evidence if isinstance(row.evidence, dict) else json.loads(row.evidence or "{}"),
        "affected_entities": row.affected_entities if isinstance(row.affected_entities, list) else json.loads(row.affected_entities or "[]"),
        "estimated_financial_impact_sar": float(row.estimated_financial_impact_sar) if row.estimated_financial_impact_sar is not None else None,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "recommended_action": row.recommended_action if isinstance(row.recommended_action, dict) else json.loads(row.recommended_action or "{}"),
        "action_risk": row.action_risk,
        "source": row.source,
        "action_status": row.action_status,
        "action_outcome": row.outcome_json if isinstance(row.outcome_json, dict) else json.loads(row.outcome_json or "{}") if row.outcome_json else None,
        "executed_at": row.applied_at.isoformat() if row.applied_at else None,
        "verification_result": row.verification_result if isinstance(row.verification_result, dict) else json.loads(row.verification_result or "{}") if row.verification_result else None,
        "observed_impact_sar": float(row.observed_impact_sar) if row.observed_impact_sar is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


async def list_findings(
    db: AsyncSession,
    business_id: UUID | str,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["business_id = :b"]
    params: dict[str, Any] = {"b": str(business_id), "lim": limit}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if domain:
        clauses.append("domain = :domain")
        params["domain"] = domain
    where = " AND ".join(clauses)
    res = await db.execute(text(f"""
        SELECT id, domain, category, severity, title, explanation, evidence,
               affected_entities, estimated_financial_impact_sar, confidence,
               recommended_action, action_risk, status, verification_result, source, created_at
        FROM findings
        WHERE {where}
        ORDER BY
          CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
          COALESCE(estimated_financial_impact_sar, 0) DESC,
          created_at DESC
        LIMIT :lim
    """), params)  # nosec B608
    out = []
    for r in res.fetchall():
        out.append({
            "id": str(r.id),
            "domain": r.domain,
            "category": r.category,
            "severity": r.severity,
            "title": r.title,
            "explanation": r.explanation,
            "evidence": r.evidence if isinstance(r.evidence, dict) else json.loads(r.evidence or "{}"),
            "affected_entities": r.affected_entities if isinstance(r.affected_entities, list) else json.loads(r.affected_entities or "[]"),
            "estimated_financial_impact_sar": float(r.estimated_financial_impact_sar) if r.estimated_financial_impact_sar is not None else None,
            "confidence": float(r.confidence) if r.confidence is not None else None,
            "recommended_action": r.recommended_action if isinstance(r.recommended_action, dict) else json.loads(r.recommended_action or "{}"),
            "action_risk": r.action_risk,
            "status": r.status,
            "verification_result": r.verification_result if isinstance(r.verification_result, dict) else json.loads(r.verification_result or "{}"),
            "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out
