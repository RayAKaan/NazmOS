"""Shared Agent Runtime (Phase 1, brief §5).

One runtime drives every specialized agent through the same loop:

    context → propose → policy gate → execute (auto | draft) → verify → record

The runtime does NOT grant the LLM arbitrary access. Each step:
  - propose:  the agent emits candidate proposals (existing contract).
  - gate:     every candidate action is classified via policy_engine
              (low→auto, medium→draft, high→mandatory approval).
  - execute:  only low-risk auto-approved actions run deterministically via
              agent_action_executor; everything else is queued as pending_approval.
  - verify:   the agent's verify_outcome hook records actual impact.

This is the architectural spine for the eventual Orchestrator/CEO Agent — it is
added WITHOUT reworking the existing agents, which keep their `propose()` contract.
"""
from __future__ import annotations
from app.utils.clock import utcnow

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.intelligence.agents.base import BaseAgent
from app.services.policy_engine import classify_and_disposition
from app.services.agent_observability import record_agent_run, estimate_prompt_tokens

logger = logging.getLogger("agent_runtime")


@dataclass
class RuntimeResult:
    agent_type: str
    proposals: int = 0
    auto_executed: int = 0
    queued_for_approval: int = 0
    actions: list[dict[str, Any]] = field(default_factory=list)


async def run_agent(
    db: AsyncSession,
    agent: BaseAgent,
    context: dict[str, Any] | None = None,
    *,
    trigger: str = "manual",
    trigger_event_type: str | None = None,
    record: bool = True,
) -> RuntimeResult:
    """Execute one agent through the full runtime loop (with observability, §24)."""
    result = RuntimeResult(agent_type=agent.agent_type)
    decisions: list[dict[str, Any]] = []
    verification: dict[str, Any] = {}
    start = time.perf_counter()
    status = "completed"
    error = None

    try:
        proposal = await agent.propose(context)
        result.proposals = len(proposal.get("payload", {}).get("proposals", []) or [])

        for candidate in (proposal.get("payload", {}).get("proposals", []) or []):
            action_type = candidate.get("action_type", "review")
            estimated = candidate.get("estimated_value_sar") or candidate.get("estimated_recovery_sar")
            confidence = float(candidate.get("confidence", 0.0) or 0.0)

            disposition = await classify_and_disposition(
                db,
                agent.business_id,
                action_type,
                candidate,
                confidence=confidence,
                estimated_impact_sar=estimated,
            )
            decisions.append({
                "action_type": action_type,
                "risk": disposition.risk,
                "decision": disposition.decision,
            })

            action = await _materialize_action(db, agent, candidate, disposition)
            if disposition.decision == "auto":
                result.auto_executed += 1
            else:
                result.queued_for_approval += 1
            result.actions.append(action)

            # §3: after a successful execution, re-audit the affected domain(s) so the
            # finding is verified against real business state, not just the API result.
            if action.get("outcome", {}).get("executed"):
                try:
                    from app.services.reaudit import reaudit_after_execution
                    await reaudit_after_execution(db, agent.business_id, action_type, commit=False)
                except Exception as exc:
                    logger.warning("re-audit after action skipped: %s", exc)

        # Verification hook runs even with zero proposals so agents can self-check.
        try:
            verification = await agent.verify_outcome(context)
            if verification.get("verified"):
                logger.info("agent %s verified outcome: %s", agent.agent_type, verification)
        except Exception as exc:  # verification must never break the run
            logger.warning("agent %s verification skipped: %s", agent.agent_type, exc)
            verification = {"verified": False, "note": str(exc)}
    except Exception as exc:
        status = "failed"
        error = str(exc)[:1000]
        logger.exception("agent %s run failed", agent.agent_type)
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)

    if record:
        try:
            await record_agent_run(
                db,
                business_id=agent.business_id,
                agent_type=agent.agent_type,
                trigger=trigger,
                trigger_event_type=trigger_event_type,
                model_provider="deterministic",  # current agents are rule/SQL-based, no LLM
                proposals=result.proposals,
                auto_executed=result.auto_executed,
                queued_for_approval=result.queued_for_approval,
                decisions=decisions,
                tools_requested=list(agent.tools or []),
                verification=verification,
                prompt_tokens=estimate_prompt_tokens(agent.agent_type, context),
                latency_ms=latency_ms,
                status=status,
                error=error,
                commit=False,
            )
        except Exception as exc:
            logger.warning("agent run observability write failed: %s", exc)

    await db.commit()
    return result


async def _materialize_action(
    db: AsyncSession,
    agent: BaseAgent,
    candidate: dict[str, Any],
    disposition,
) -> dict[str, Any]:
    """Persist the candidate as an AgentAction in the right status, and auto-execute
    only when the policy engine returned `auto`. Reuses the existing executor."""
    import json
    from sqlalchemy import text

    action_type = candidate.get("action_type", "review")
    status = "auto_executed" if disposition.decision == "auto" else "pending_approval"

    # §2–3: deterministic, auditable finding → action linkage. The candidate carries the
    # finding_id it was derived from (agents set this); we do NOT infer it from titles.
    finding_id = candidate.get("finding_id")

    res = await db.execute(text("""
        INSERT INTO agent_actions
            (id, business_id, finding_id, action_type, status, confidence, priority, title, summary,
             payload, estimated_value_sar, autonomy_dial_at_creation, was_auto_executed, created_at, updated_at)
        VALUES
            (:id, :b, :fid, :type, :status, :conf, 3, :title, :summary,
             CAST(:payload AS JSON), :value, :dial, :auto, :now, :now)
        RETURNING id
    """), {
        "id": str(uuid.uuid4()),
        "b": str(agent.business_id),
        "fid": str(finding_id) if finding_id else None,
        "type": action_type,
        "status": status,
        "conf": candidate.get("confidence", 0.8),
        "title": candidate.get("title", candidate.get("reason", action_type)),
        "summary": candidate.get("reason", candidate.get("summary", "")),
        "payload": json.dumps(candidate, default=str),
        "value": candidate.get("estimated_value_sar"),
        "dial": int(disposition.policy.get("dial", 50)),
        "auto": disposition.decision == "auto",
        "now": utcnow(),
    })
    row = res.fetchone()
    action_id = str(row.id)

    # Back-link Finding.agent_action_id (convenience pointer to the most recent action).
    if finding_id:
        await db.execute(text("""
            UPDATE findings SET agent_action_id = :aid, updated_at = :now
            WHERE id = :fid AND (agent_action_id IS NULL OR agent_action_id <> :aid)
        """), {"aid": action_id, "fid": str(finding_id), "now": utcnow()})

    if disposition.decision == "auto":
        from app.services.agent_action_executor import execute_agent_action
        outcome = await execute_agent_action(db, agent.business_id, action_id, action_type, candidate)
        await db.execute(text("""
            UPDATE agent_actions
            SET applied_at = CASE WHEN :executed THEN NOW() ELSE applied_at END,
                outcome_json = CAST(:outcome AS JSON), updated_at = NOW()
            WHERE id = :id
        """), {
            "id": action_id,
            "executed": bool(outcome.get("executed")),
            "outcome": json.dumps(outcome, default=str),
        })
    else:
        outcome = {"executed": False, "reason": "queued for approval"}

    await db.commit()

    # §2: auto-executed actions reach a terminal state here — record the unified outcome
    # (LearnedOutcome + OutcomeFeedback bridge), best-effort so it never breaks the run.
    if disposition.decision == "auto":
        try:
            from app.services.outcome_learning import record_unified_outcome
            await record_unified_outcome(
                db, agent.business_id, action_id, finding_id=finding_id, commit=True,
            )
        except Exception as exc:
            logger.warning("learned-outcome write skipped: %s", exc)

    # Thread decision-quality inputs (Phase 9 §8) through to the orchestrator's score.
    data_quality_score = candidate.get("data_quality_score")
    if data_quality_score is None and finding_id:
        f = await db.execute(text("SELECT data_quality_score FROM findings WHERE id = :fid"),
                             {"fid": str(finding_id)})
        row = f.fetchone()
        if row and row.data_quality_score is not None:
            data_quality_score = float(row.data_quality_score)

    return {
        "action_id": action_id,
        "action_type": action_type,
        "status": status,
        "risk": disposition.risk,
        "decision": disposition.decision,
        "reason": disposition.reason,
        "outcome": outcome,
        "finding_id": str(finding_id) if finding_id else None,
        "estimated_value_sar": candidate.get("estimated_value_sar"),
        "confidence": candidate.get("confidence"),
        "urgency": candidate.get("urgency"),
        "data_quality_score": data_quality_score,
    }
