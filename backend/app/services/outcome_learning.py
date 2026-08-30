"""Structured outcome learning (Phase 4, §5–8).

Bridges the existing learning engine (OutcomeFeedback, tied to IntelligenceDecision)
to the agentic action loop: every meaningful AgentAction — approved/rejected/executed/
verified — is distilled into a `LearnedOutcome` with a provenance kind (fact | inference |
preference | hypothesis) and confidence. Rejections are captured with their reason
(`AgentAction.decision_note` already exists as the store); repeated evidence raises
confidence, but a single rejection never becomes a permanent rule (§6).
"""
from __future__ import annotations
from app.utils.clock import utcnow

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json(v: Any) -> str:
    return json.dumps(v, default=str)


def _iso(v: Any) -> str | None:
    """Dialect-safe timestamp serialization: SQLite returns strings, Postgres returns
    datetimes — accept both."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return v.isoformat()


def confidence_tier(evidence_count: int) -> tuple[str, float]:
    """Deterministic, documented confidence tiering (§9). Never LLM-invented.

    <2 occurrences    → weak evidence (base confidence preserved)
    2–5 occurrences   → moderate evidence
    6–19 occurrences  → strong evidence
    ≥20 occurrences   → very strong evidence
    """
    if evidence_count >= 20:
        return "very_strong", 0.95
    if evidence_count >= 6:
        return "strong", 0.85
    if evidence_count >= 2:
        return "moderate", 0.70
    return "weak", 0.50


async def learn_from_action(
    db: AsyncSession,
    business_id: UUID | str,
    action_id: UUID | str,
    *,
    kind: str = "inference",
    finding_id: UUID | str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Distill an AgentAction into a LearnedOutcome. Idempotent per action: re-learning
    updates the existing record rather than duplicating (evidence_count grows)."""
    res = await db.execute(text("""
        SELECT id, action_type, status, payload, decision_note, outcome_json,
               estimated_value_sar, was_auto_executed, applied_at
        FROM agent_actions WHERE id = :id AND business_id = :b
    """), {"id": str(action_id), "b": str(business_id)})
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "action not found"}

    status = row.status
    approval = "auto_executed" if row.was_auto_executed else (
        "approved" if status in ("approved", "executed") else
        "rejected" if status == "rejected" else "pending"
    )

    outcome = row.outcome_json if isinstance(row.outcome_json, dict) else (json.loads(row.outcome_json) if row.outcome_json else {})
    executed = bool(outcome.get("executed")) if isinstance(outcome, dict) else False

    # Extract a concise recommendation summary from the payload (never raw context).
    payload = row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {})
    recommendation = str(payload.get("title") or payload.get("reason") or row.action_type)[:500]

    # Verification / impact come from the impact ledger if present.
    impact = await db.execute(text("""
        SELECT COALESCE(SUM(actual_sar), 0), COALESCE(SUM(expected_sar), 0), COALESCE(SUM(amount_sar), 0)
        FROM impact_ledger WHERE agent_action_id = :id AND business_id = :b
    """), {"id": str(action_id), "b": str(business_id)})
    irow = impact.fetchone()
    actual_impact = irow[0] if irow else None
    expected_impact = row.estimated_value_sar

    # Confidence: approved+executed+verified outcomes are stronger evidence than rejections.
    confidence = 0.5
    if approval in ("approved", "auto_executed") and executed:
        confidence = 0.85
    elif approval == "rejected":
        confidence = 0.6  # a rejection is evidence of a preference/pattern, lower confidence

    now = utcnow()

    # Idempotent upsert (§3): ON CONFLICT on the unique agent_action_id updates in place —
    # a replay/retry/duplicate request must NOT create a second record or inflate
    # evidence_count (each action is one piece of evidence; "repeated evidence" is expressed
    # by multiple actions, aggregated at query time).
    import uuid
    lid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO learned_outcomes
            (id, business_id, agent_action_id, finding_id, action_type, kind, recommendation,
             approval, rejection_reason, execution_result, expected_impact_sar, actual_impact_sar,
             confidence, evidence_count, expires_at, created_at)
        VALUES
            (:id, :b, :aid, :fid, :type, :kind, :rec, :approval, :reason,
             CAST(:outcome AS JSON), :expected, :actual, :conf, 1, :expires, :now)
        ON CONFLICT (agent_action_id) DO UPDATE SET
            approval = EXCLUDED.approval,
            rejection_reason = EXCLUDED.rejection_reason,
            execution_result = EXCLUDED.execution_result,
            expected_impact_sar = EXCLUDED.expected_impact_sar,
            actual_impact_sar = EXCLUDED.actual_impact_sar,
            confidence = EXCLUDED.confidence,
            recommendation = EXCLUDED.recommendation,
            kind = EXCLUDED.kind
        RETURNING id
    """), {
        "id": str(lid), "b": str(business_id), "aid": str(action_id),
        "fid": str(finding_id) if finding_id else None, "type": row.action_type, "kind": kind,
        "rec": recommendation, "approval": approval, "reason": row.decision_note,
        "outcome": _json({"executed": executed, "status": status}),
        "expected": expected_impact, "actual": actual_impact, "conf": confidence,
        "expires": now + timedelta(days=90), "now": now,
    })
    result = await db.execute(text("SELECT id FROM learned_outcomes WHERE agent_action_id = :aid"), {"aid": str(action_id)})
    rid = result.fetchone()
    if commit:
        await db.commit()
    return {"ok": True, "learned_outcome_id": str(rid.id) if rid else str(lid), "updated": bool(rid)}


async def rejections_for(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Recent rejection evidence for an action type (used to inform future agents, §6)."""
    clause = "business_id = :b AND approval = 'rejected'"
    params: dict[str, Any] = {"b": str(business_id), "lim": limit}
    if action_type:
        clause += " AND action_type = :t"
        params["t"] = action_type
    res = await db.execute(text(f"""
        SELECT action_type, rejection_reason, confidence, evidence_count, created_at
        FROM learned_outcomes
        WHERE {clause}
        ORDER BY created_at DESC LIMIT :lim
    """), params)
    return [dict(r._mapping) for r in res.fetchall()]


async def intervention_effectiveness(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Aggregate historical intervention effectiveness (Phase 5, §5/§7).

    Returns {attempts, succeeded, success_rate, avg_actual_impact, rejected} for the given
    action type (and optional finding category). This is the deterministic evidence agents
    consume to change future recommendations — never raw historical text.
    """
    clause = "business_id = :b"
    params: dict[str, Any] = {"b": str(business_id)}
    if action_type:
        clause += " AND action_type = :t"
        params["t"] = action_type
    if category:
        clause += " AND recommendation ILIKE :cat"
        params["cat"] = f"%{category}%"

    res = await db.execute(text(f"""
        SELECT
            COUNT(*) AS attempts,
            COALESCE(SUM(CASE WHEN approval IN ('approved','auto_executed') AND execution_result->>'executed' = 'true' THEN 1 ELSE 0 END), 0) AS succeeded,
            COALESCE(SUM(CASE WHEN approval = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected,
            COALESCE(AVG(actual_impact_sar), 0) AS avg_actual_impact,
            COALESCE(SUM(actual_impact_sar), 0) AS total_actual_impact
        FROM learned_outcomes
        WHERE {clause}
    """), params)
    r = res.fetchone()
    attempts = int(r.attempts or 0)
    succeeded = int(r.succeeded or 0)
    # Effectiveness = actual / expected impact (§10). Never estimated-as-actual.
    expected_total = await db.execute(text(f"""
        SELECT COALESCE(SUM(expected_impact_sar), 0) FROM learned_outcomes WHERE {clause}
    """), params)
    exp_total = float(expected_total.scalar() or 0)
    act_total = float(r.total_actual_impact or 0)
    effectiveness = round(act_total / exp_total, 3) if exp_total > 0 else None

    return {
        "attempts": attempts,
        "succeeded": succeeded,
        "rejected": int(r.rejected or 0),
        "success_rate": round(succeeded / attempts, 3) if attempts else None,
        "avg_actual_impact_sar": float(r.avg_actual_impact or 0),
        "total_actual_impact_sar": act_total,
        "total_expected_impact_sar": exp_total,
        "effectiveness": effectiveness,  # actual / expected; None if no expected baseline
    }


async def record_unified_outcome(
    db: AsyncSession,
    business_id: UUID | str,
    action_id: UUID | str,
    *,
    kind: str = "inference",
    finding_id: UUID | str | None = None,
    data_quality_note: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """§5–6: one action → one canonical outcome → two consumers.

    1. LearnedOutcome — business intervention memory (drives future agent behaviour).
    2. OutcomeFeedback — model/action performance signal (feeds the existing learning
       engine / Thompson sampling). No third system is created; the two remain
       semantically distinct but now share a single write path.
    """
    learned = await learn_from_action(db, business_id, action_id, kind=kind,
                                      finding_id=finding_id, commit=False)
    if not learned.get("ok"):
        if commit:
            await db.commit()
        return learned

    # Persist the data-quality note (avoids a second write in learn_from_action).
    if data_quality_note:
        await db.execute(text("""
            UPDATE learned_outcomes SET data_quality_note = :note
            WHERE agent_action_id = :aid
        """), {"note": data_quality_note, "aid": str(action_id)})

    # Bridge to OutcomeFeedback (action-performance signal) — decision_type = action_type.
    # predicted = expected impact, actual = observed impact + executed flag.
    try:
        res = await db.execute(text("""
            SELECT action_type, expected_impact_sar, actual_impact_sar, execution_result
            FROM learned_outcomes WHERE agent_action_id = :aid LIMIT 1
        """), {"aid": str(action_id)})
        row = res.fetchone()
        if row:
            executed = False
            if row.execution_result and isinstance(row.execution_result, dict):
                executed = bool(row.execution_result.get("executed"))
            elif row.execution_result:
                try:
                    executed = bool(json.loads(row.execution_result).get("executed"))
                except Exception:
                    pass
            predicted = {"expected_impact_sar": float(row.expected_impact_sar or 0)}
            actual = {
                "actual_impact_sar": float(row.actual_impact_sar or 0),
                "executed": executed,
            }
            delta = {
                "impact_delta_sar": round(
                    float(row.actual_impact_sar or 0) - float(row.expected_impact_sar or 0), 2
                )
            }
            await db.execute(text("""
                INSERT INTO outcome_feedback
                    (id, business_id, agent_action_id, decision_type, predicted_outcome, actual_outcome, delta,
                     feedback_source, recorded_at, created_at)
                VALUES
                    (:id, :b, :aid, :type, CAST(:pred AS JSON), CAST(:actual AS JSON),
                     CAST(:delta AS JSON), 'system', :now, :now)
                ON CONFLICT (agent_action_id) DO NOTHING
            """), {
                "id": str(uuid.uuid4()), "b": str(business_id), "aid": str(action_id),
                "type": row.action_type,
                "pred": _json(predicted), "actual": _json(actual), "delta": _json(delta),
                "now": utcnow(),
            })
    except Exception as exc:
        # The performance bridge is best-effort; business learning must never fail on it.
        import logging
        logging.getLogger("outcome_learning").warning("outcome-feedback bridge skipped: %s", exc)

    if commit:
        await db.commit()
    return learned


async def repeated_failures(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    threshold: int = 2,
) -> bool:
    """True if the given action type has failed (executed=False or rejected) repeatedly,
    signalling future agents should try an alternative (§6–7)."""
    res = await db.execute(text("""
        SELECT COUNT(*) FROM learned_outcomes
        WHERE business_id = :b AND action_type = :t
          AND (approval = 'rejected'
               OR (approval IN ('approved','auto_executed') AND execution_result->>'executed' != 'true'))
    """), {"b": str(business_id), "t": action_type})
    return int(res.scalar() or 0) >= threshold


# §5/§7: deterministic alternative-recommendation mapping. When an intervention has
# historically failed for a business, agents propose the alternative instead.
ALTERNATIVE_ACTIONS: dict[str, str] = {
    "discount": "transfer_inventory",   # discounting failed → try a branch transfer first
    "restock": "transfer_inventory",    # restocking failed → try internal transfer
    "transfer_inventory": "discount",
    "margin_fix": "pricing_decrease",
    "pricing_decrease": "margin_fix",
}


async def learning_adjusted_action(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str,
) -> dict[str, Any]:
    """Return the action type NazmOS should recommend given historical evidence (§5).

    Deterministic: if the candidate action type has failed repeatedly (rejected or
    execution failure), suggest the mapped alternative with an evidence-based reason.
    Never injects raw historical text into any model.
    """
    if await repeated_failures(db, business_id, action_type):
        alternative = ALTERNATIVE_ACTIONS.get(action_type)
        if alternative and alternative != action_type:
            return {
                "action_type": alternative,
                "adjusted": True,
                "reason": (
                    f"Previous {action_type} interventions repeatedly failed for this business; "
                    f"recommending {alternative} instead."
                ),
            }
    return {"action_type": action_type, "adjusted": False, "reason": None}


async def list_learned_outcomes(
    db: AsyncSession,
    business_id: UUID | str,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clause = "business_id = :b"
    params: dict[str, Any] = {"b": str(business_id), "lim": limit}
    if kind:
        clause += " AND kind = :k"
        params["k"] = kind
    res = await db.execute(text(f"""
        SELECT id, action_type, kind, recommendation, approval, rejection_reason,
               expected_impact_sar, actual_impact_sar, confidence, evidence_count, created_at
        FROM learned_outcomes
        WHERE {clause}
        ORDER BY created_at DESC LIMIT :lim
    """), params)
    out = []
    for r in res.fetchall():
        out.append({
            "id": str(r.id), "action_type": r.action_type, "kind": r.kind,
            "recommendation": r.recommendation, "approval": r.approval,
            "rejection_reason": r.rejection_reason,
            "expected_impact_sar": float(r.expected_impact_sar) if r.expected_impact_sar is not None else None,
            "actual_impact_sar": float(r.actual_impact_sar) if r.actual_impact_sar is not None else None,
            "confidence": float(r.confidence), "evidence_count": r.evidence_count,
            "created_at": _iso(r.created_at),
        })
    return out
