"""Temporal workflow definitions for NazmOS execution.

These classes are the exact orchestration skeletons executed by the Temporal
server under ``USE_TEMPORAL=True``. They mirror the step order of the local
deterministic functions in ``app.orchestration.workflows`` so both substrates
produce identical outcomes:

- ``ManualActionWorkflow``: capability → constraints → idempotency → apply → record
- ``AgentApprovalWorkflow``: approve → executing → apply → terminal → learning
- ``SimulatedWorkflow``: apply-simulated (no business-data mutation)

No business logic lives here: every side effect is delegated to a real
activity (``app.orchestration.temporal.activities``) whose name and explicit
retry policy are resolved from ``app.orchestration.temporal.policies``.
Determinism requirements are respected: no clocks, no random, no I/O outside
``workflow.execute_activity`` (the one best-effort learning call is itself an
activity, executed last with a catch).
"""
from __future__ import annotations

import datetime
from typing import Any

from temporalio import workflow

from app.orchestration.temporal.policies import activity_retry_policy

# Direct workflow-start path (all steps; matches the local composition).
START_TO_CLOSE = datetime.timedelta(seconds=30)

# Manual action-type → apply activity name (mirrors workflows.py dispatch).
APPLY_ACTIVITY_BY_ACTION: dict[str, str] = {
    "RESTOCK": "apply_restock",
    "PRICE_CHANGE": "apply_price_change",
    "DISCOUNT": "apply_discount",
    "ALERT_DISMISS": "apply_alert_dismiss",
}

with workflow.unsafe.imports_passed_through():
    # Imported only for the sandbox import pass; no clock/UUID usage in workflows.
    from app.orchestration.workflows import WF_AGENT_APPROVAL, WF_MANUAL_ACTION, WF_SIMULATED  # noqa: F401  (type names)


async def _act(name: str, payload: dict[str, Any]) -> Any:
    return await workflow.execute_activity(
        name,
        payload,
        start_to_close_timeout=START_TO_CLOSE,
        retry_policy=activity_retry_policy(name),
    )


def _meta(workflow_type: str) -> dict[str, str]:
    return {
        "workflow": workflow_type,
        "run_id": workflow.info().run_id,
        "workflow_id": workflow.info().workflow_id,
    }


@workflow.defn(name=WF_MANUAL_ACTION)
class ManualActionWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        business_id = req["business_id"]
        action_type = req["action_type"]
        entity_id = req["entity_id"]

        # 1. Capability revalidation (only when an actor is attached).
        if req.get("user_id"):
            cap = await _act(
                "revalidate_capability",
                {"business_id": business_id, "user_id": req["user_id"]},
            )
            if not cap["ok"]:
                return {
                    **_meta(WF_MANUAL_ACTION),
                    "blocked": True,
                    "reason_code": "INSUFFICIENT_CAPABILITY",
                    "reason": "User lacks can_approve_actions capability for this business.",
                }

        # 2. Owner-constraint / state guard (verdict only).
        verdict = await _act(
            "validate_action_constraints",
            {
                "business_id": business_id,
                "entity_id": entity_id,
                "action_type": action_type,
                "payload": {**req.get("payload", {}), "item_id": str(entity_id)},
                "previous_state": req.get("previous_state") or {},
                "new_state": req.get("new_state") or {},
            },
        )
        if verdict.get("blocked"):
            await _act(
                "record_constraint_block",
                {
                    "business_id": business_id,
                    "action_type": action_type,
                    "reason_code": verdict.get("reason_code"),
                    "reason": verdict.get("reason"),
                    "attempted_by": req.get("user_id"),
                    "new_state": req.get("new_state") or {},
                },
            )
            return {
                **_meta(WF_MANUAL_ACTION),
                "blocked": True,
                "reason_code": verdict.get("reason_code"),
                "reason": verdict.get("reason"),
            }

        # 3. Durable idempotency check.
        idem = await _act(
            "check_execution_idempotency",
            {
                "business_id": business_id,
                "execution_key": req["execution_key"],
                "table": "executed_actions",
            },
        )
        if idem.get("existing"):
            return {
                **_meta(WF_MANUAL_ACTION),
                "replayed": True,
                "action_id": idem.get("id"),
                "reason": f"Action already executed (replayed key={req['execution_key'][:8]})",
            }

        # 4. Apply business mutation (exactly-once: deterministic policy, never retried).
        apply_name = APPLY_ACTIVITY_BY_ACTION.get(action_type)
        outcome: dict[str, Any]
        if apply_name == "apply_alert_dismiss":
            outcome = await _act(apply_name, {"decision_id": entity_id})
        elif apply_name is not None:
            outcome = await _act(
                apply_name,
                {
                    "business_id": business_id,
                    "item_id": entity_id,
                    "new_state": req.get("new_state") or {},
                },
            )
        else:
            outcome = {"executed": False, "reason": f"Unknown action type: {action_type}"}

        # 5. Record outcome (idempotent, transient-retry).
        rec = await _act(
            "record_manual_action",
            {
                "business_id": business_id,
                "action_type": action_type,
                "entity_type": req.get("entity_type", ""),
                "entity_id": entity_id,
                "previous_state": req.get("previous_state") or {},
                "new_state": req.get("new_state") or {},
                "source": req.get("source", "manual"),
                "execution_key": req["execution_key"],
                "decision_id": req.get("decision_id"),
                "user_id": req.get("user_id"),
                "outcome": outcome,
            },
        )

        if outcome.get("executed"):
            return {
                **_meta(WF_MANUAL_ACTION),
                "success": True,
                "action_id": rec.get("action_id"),
                "outcome": outcome,
                "message": outcome.get("message", "Executed"),
            }
        return {
            **_meta(WF_MANUAL_ACTION),
            "success": False,
            "action_id": rec.get("action_id"),
            "outcome": outcome,
            "message": outcome.get("reason", "Execution failed"),
            "error": outcome.get("reason"),
        }


@workflow.defn(name=WF_AGENT_APPROVAL)
class AgentApprovalWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        action_id = req["action_id"]

        # 1. Approve (pending_approval → approved; single-transition guard).
        approval = await _act(
            "record_agent_approval",
            {
                "business_id": req.get("business_id"),
                "action_id": action_id,
                "note": req.get("note") or "Approved",
                "decided_by": req.get("decided_by"),
            },
        )
        if not approval.get("ok"):
            return {**_meta(WF_AGENT_APPROVAL), **approval}

        # 2. approve → executing (raced/stale approvals never proceed).
        mark = await _act(
            "agent_mark_executing",
            {
                "business_id": req.get("business_id"),
                "action_id": action_id,
            },
        )
        if not mark.get("ok"):
            return {**_meta(WF_AGENT_APPROVAL), "ok": False, "reason": mark.get("reason")}

        # 3. Apply business mutation (exactly-once).
        outcome = await _act(
            "apply_agent_action",
            {
                "business_id": approval["business_id"],
                "action_id": action_id,
                "action_type": approval["action_type"],
                "payload": approval.get("payload"),
            },
        )

        # 4. Record terminal status.
        await _act(
            "record_agent_terminal",
            {
                "business_id": approval.get("business_id"),
                "action_id": action_id,
                "outcome": outcome,
            },
        )

        # 5. Best-effort learning/KG distillation (never fails the workflow).
        try:
            await _act(
                "record_terminal_outcome",
                {"business_id": approval.get("business_id"), "action_id": action_id},
            )
        except Exception:  # noqa: BLE001 - best-effort by design
            pass

        return {
            **_meta(WF_AGENT_APPROVAL),
            "ok": True,
            "action_id": str(action_id),
            "outcome": outcome,
        }


@workflow.defn(name=WF_SIMULATED)
class SimulatedWorkflow:
    @workflow.run
    async def run(self, req: dict) -> dict:
        # apply_simulated_execution records an ExecutionJob and never mutates
        # business data (ADR §7). Deterministic policy: never retried.
        outcome = await _act(
            "apply_simulated_execution",
            {
                "business_id": req["business_id"],
                "action_type": req["action_type"],
                "entity_type": req.get("entity_type", ""),
                "entity_id": req["entity_id"],
                "payload": req.get("payload", {}),
            },
        )
        return {**_meta(WF_SIMULATED), **outcome}


# Registration table for the worker + tests.
WORKFLOWS: dict[str, Any] = {
    WF_MANUAL_ACTION: ManualActionWorkflow,
    WF_AGENT_APPROVAL: AgentApprovalWorkflow,
    WF_SIMULATED: SimulatedWorkflow,
}