"""Real Temporal activities for NazmOS execution.

Each ``@activity.defn`` is a thin transport boundary: it opens its own
tenant-scoped database session, calls the SAME canonical NazmOS business
functions the local deterministic composition uses (apply.py / record.py /
precheck.py — the bodies never move into Temporal), commits, and returns a
JSON-safe outcome.

Business semantics stay in NazmOS. Temporal owns only durable scheduling,
retries, and replay — the activity bodies here merely adapt the transport
(JSON payloads in, JSON-safe outcomes out) to the existing services.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from temporalio import activity

from app.database.connection import async_session_scope, sync_rls_tenant_context


def _uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


@asynccontextmanager
async def _db_scope(business_id: str | None = None):
    """Tenant-scoped DB session context for an activity invocation.

    Wraps ``async_session_scope`` (auto-commit on success, auto-rollback on
    failure) with the Postgres RLS tenant context. ``None`` runs without a
    tenant scope (decision-level work that needs none).
    """
    if business_id:
        with sync_rls_tenant_context(str(business_id)):
            async with async_session_scope() as db:
                yield db
    else:
        async with async_session_scope() as db:
            yield db


# ── Manual path (manual_action) ───────────────────────────────────────


@activity.defn(name="revalidate_capability")
async def act_revalidate_capability(payload: dict) -> dict:
    """Re-check the actor still holds can_approve_actions."""
    business_id = _uuid(payload["business_id"])
    user_id = _uuid(payload["user_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import revalidate_capability

        ok = await revalidate_capability(db, user_id, business_id)
    return {"ok": bool(ok)}


@activity.defn(name="validate_action_constraints")
async def act_validate_action_constraints(payload: dict) -> dict:
    """Run the owner-constraint / state guard (verdict only, no side effects)."""
    business_id = _uuid(payload["business_id"])
    entity_id = _uuid(payload["entity_id"])
    action_type = payload["action_type"]
    guarded_payload = {**payload.get("payload", {}), "item_id": str(entity_id)}
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import validate_action_constraints

        verdict = await validate_action_constraints(
            db,
            business_id=business_id,
            action_type=action_type,
            payload=guarded_payload,
            previous_state=payload.get("previous_state") or {},
            new_state=payload.get("new_state") or {},
            actor_business_id=business_id,
        )
    return {
        "blocked": bool(getattr(verdict, "blocked", False)),
        "reason_code": getattr(verdict, "reason_code", None),
        "reason": getattr(verdict, "reason", None),
    }


@activity.defn(name="record_constraint_block")
async def act_record_constraint_block(payload: dict) -> dict:
    """Durably record a blocked execution attempt (best-effort, never raises)."""
    business_id = _uuid(payload["business_id"])
    attempted_by = (
        _uuid(payload["attempted_by"]) if payload.get("attempted_by") else None
    )
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.precheck import record_constraint_block

        await record_constraint_block(
            db,
            business_id=business_id,
            action_type=payload.get("action_type", ""),
            reason_code=payload.get("reason_code", ""),
            reason=payload.get("reason", ""),
            attempted_by=attempted_by,
            payload=payload.get("new_state") or payload.get("payload"),
        )
    return {"ok": True}


@activity.defn(name="check_execution_idempotency")
async def act_check_execution_idempotency(payload: dict) -> dict:
    """Durable idempotency probe: does this execution_key already terminate?"""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from app.orchestration.record import check_execution_idempotency

        existing = await check_execution_idempotency(
            db,
            payload.get("execution_key", ""),
            table=payload.get("table", "executed_actions"),
        )
    if existing:
        return {"existing": True, "replayed": True, "id": existing["id"], "status": existing["status"]}
    return {"existing": False}


@activity.defn(name="apply_restock")
async def act_apply_restock(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_restock

        return await apply_restock(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_price_change")
async def act_apply_price_change(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_price_change

        return await apply_price_change(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_discount")
async def act_apply_discount(payload: dict) -> dict:
    business_id = _uuid(payload["business_id"])
    item_id = _uuid(payload["item_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_discount

        return await apply_discount(db, business_id, item_id, payload.get("new_state") or {})


@activity.defn(name="apply_alert_dismiss")
async def act_apply_alert_dismiss(payload: dict) -> dict:
    decision_id = _uuid(payload["decision_id"])
    async with _db_scope(None) as db:
        from app.orchestration.apply import apply_alert_dismiss

        return await apply_alert_dismiss(db, decision_id)


@activity.defn(name="record_manual_action")
async def act_record_manual_action(payload: dict) -> dict:
    """Persist the manual-action outcome with its execution_key."""
    business_id = _uuid(payload["business_id"])
    entity_id = _uuid(payload["entity_id"])
    decision_id = _uuid(payload["decision_id"]) if payload.get("decision_id") else None
    user_id = _uuid(payload["user_id"]) if payload.get("user_id") else None
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.record import record_manual_action

        action_id = await record_manual_action(
            db,
            business_id=business_id,
            action_type=payload["action_type"],
            entity_type=payload.get("entity_type", ""),
            entity_id=entity_id,
            previous_state=payload.get("previous_state") or {},
            new_state=payload.get("new_state") or {},
            source=payload.get("source", "manual"),
            execution_key=payload.get("execution_key", ""),
            decision_id=decision_id,
            user_id=user_id,
            outcome=payload.get("outcome"),
        )
    return {"action_id": str(action_id)}


# ── Agent path (agent_approval) ───────────────────────────────────────


@activity.defn(name="record_agent_approval")
async def act_record_agent_approval(payload: dict) -> dict:
    """pending_approval -> approved (single-transition guard), returns row data."""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from app.orchestration.record import record_agent_approval

        return await record_agent_approval(
            db,
            action_id=payload["action_id"],
            note=payload.get("note") or "Approved",
            decided_by=payload.get("decided_by"),
            business_id=business_id,
        )


@activity.defn(name="agent_mark_executing")
async def act_agent_mark_executing(payload: dict) -> dict:
    """approved -> executing, guarded (stale/raced approvals never proceed)."""
    business_id = payload.get("business_id")
    async with _db_scope(str(business_id) if business_id else None) as db:
        from sqlalchemy import text

        from app.utils.clock import utcnow

        res = await db.execute(
            text(
                "UPDATE agent_actions SET status='executing', updated_at=:now "
                "WHERE id=:id AND status='approved'"
            ),
            {"id": str(_uuid(payload["action_id"])), "now": utcnow()},
        )
    if res.rowcount != 1:
        return {
            "ok": False,
            "reason": f"Action {payload['action_id']} is not in the approved state",
        }
    return {"ok": True}


@activity.defn(name="apply_agent_action")
async def act_apply_agent_action(payload: dict) -> dict:
    """Apply the agent mutation (owns its own guard + mutation transaction)."""
    business_id = _uuid(payload["business_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_agent_action

        return await apply_agent_action(
            db,
            business_id,
            payload["action_id"],
            payload["action_type"],
            payload.get("payload") or {},
        )


@activity.defn(name="record_agent_terminal")
async def act_record_agent_terminal(payload: dict) -> dict:
    """Record the terminal agent-action status after apply."""
    async with _db_scope(str(payload["business_id"]) if payload.get("business_id") else None) as db:
        from app.orchestration.record import record_agent_terminal

        await record_agent_terminal(
            db, action_id=_uuid(payload["action_id"]), outcome=payload.get("outcome") or {}
        )
    return {"ok": True}


@activity.defn(name="record_terminal_outcome")
async def act_record_terminal_outcome(payload: dict) -> dict:
    """Best-effort learning/KG distillation — must never fail the workflow."""
    try:
        async with _db_scope(str(payload["business_id"]) if payload.get("business_id") else None) as db:
            from app.orchestration.record import record_terminal_outcome

            await record_terminal_outcome(db, payload["business_id"], payload["action_id"])
    except Exception:  # noqa: BLE001 - intentionally best-effort
        return {"ok": False}
    return {"ok": True}


# ── Simulated path (simulated) ────────────────────────────────────────


@activity.defn(name="apply_simulated_execution")
async def act_apply_simulated_execution(payload: dict) -> dict:
    """Simulated execution — records an ExecutionJob, never mutates business data."""
    business_id = _uuid(payload["business_id"])
    async with _db_scope(str(business_id)) as db:
        from app.orchestration.apply import apply_simulated_execution

        return await apply_simulated_execution(
            db,
            business_id,
            payload["action_type"],
            payload.get("entity_type", ""),
            _uuid(payload["entity_id"]),
            payload.get("payload") or {},
        )


# ── Registration table (single source for the worker + tests) ─────────

ACTIVITIES: dict[str, Callable[[dict], Any]] = {
    "revalidate_capability": act_revalidate_capability,
    "validate_action_constraints": act_validate_action_constraints,
    "record_constraint_block": act_record_constraint_block,
    "check_execution_idempotency": act_check_execution_idempotency,
    "apply_restock": act_apply_restock,
    "apply_price_change": act_apply_price_change,
    "apply_discount": act_apply_discount,
    "apply_alert_dismiss": act_apply_alert_dismiss,
    "record_manual_action": act_record_manual_action,
    "record_agent_approval": act_record_agent_approval,
    "agent_mark_executing": act_agent_mark_executing,
    "apply_agent_action": act_apply_agent_action,
    "record_agent_terminal": act_record_agent_terminal,
    "record_terminal_outcome": act_record_terminal_outcome,
    "apply_simulated_execution": act_apply_simulated_execution,
}

ALL_ACTIVITY_FUNCTIONS = list(ACTIVITIES.values())
ALL_ACTIVITY_NAMES = frozenset(ACTIVITIES)