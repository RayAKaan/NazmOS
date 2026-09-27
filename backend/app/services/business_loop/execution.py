"""Execution + reconciliation (Phase 3H) — registered-action dry-run execution.

Only REGISTERED action contracts may execute (asserted against
``app.services.action_registry.ACTION_REGISTRY``). Every execution intent is
idempotent via ``app.orchestration.keys.derive_execution_key``. A dry-run
execution returns a SYNTHETIC receipt that is never represented as a real
merchant action (MASTER_PLAN §19, vertical slice rule).

Reconciliation (requested vs actual): before any retry of a potentially
successful external action, the actual receipt must reconcile. A blind retry
after timeout is forbidden here — callers receive ``reconcile_required``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.orchestration.keys import derive_execution_key
from app.services.action_registry import ACTION_REGISTRY, get_action_spec
from app.services.business_loop.contracts import GovernanceOutcome, RecommendationStatus


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ExecutionIntent:
    """One idempotent, pre-authorized execution intent."""

    business_id: str
    action_type: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "business_loop"
    recommendation_id: str = ""
    execution_key: str = ""

    def __post_init__(self) -> None:
        if not self.execution_key:
            self.execution_key = derive_execution_key(
                self.business_id, self.action_type, self.entity_type, self.entity_id, self.payload, self.source
            )


@dataclass
class SyntheticReceipt:
    """Receipt from a dry-run execution. EXPLICITLY synthetic — not a real action."""

    execution_key: str
    action_type: str
    business_id: str
    receipt_id: str
    ok: bool
    synthetic: bool = True  # never represent a dry-run as a real merchant action
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = ""

    def __post_init__(self) -> None:
        self.recorded_at = self.recorded_at or _now_iso()


def preflight(
    intent: ExecutionIntent,
    *,
    action_registry: dict[str, Any] = ACTION_REGISTRY,
) -> tuple[bool, list[str]]:
    """Pre-execution revalidation: registered action + preconditions + payload."""
    reasons: list[str] = []
    if intent.action_type not in action_registry:
        return False, ["unregistered_action"]
    spec = get_action_spec(intent.action_type)
    if not spec.can_execute:
        reasons.append(f"registry_can_execute_false:{intent.action_type}")
    return (not reasons, reasons)


def dry_run_execute(
    intent: ExecutionIntent,
    *,
    decision: GovernanceOutcome,
    recommendation_status: RecommendationStatus,
    action_registry: dict[str, Any] = ACTION_REGISTRY,
) -> SyntheticReceipt:
    """Execute (dry-run) ONLY when governance permitted + recommendation ready."""
    if decision != GovernanceOutcome.PERMITTED:
        return SyntheticReceipt(
            execution_key=intent.execution_key,
            action_type=intent.action_type,
            business_id=intent.business_id,
            receipt_id=f"rcpt-rejected-{intent.execution_key[:12]}",
            ok=False,
            details={"reason": "governance_not_permitted", "outcome": decision.value if hasattr(decision, "value") else str(decision)},
        )
    if recommendation_status not in (RecommendationStatus.APPROVED, RecommendationStatus.EXECUTING):
        return SyntheticReceipt(
            execution_key=intent.execution_key,
            action_type=intent.action_type,
            business_id=intent.business_id,
            receipt_id=f"rcpt-notready-{intent.execution_key[:12]}",
            ok=False,
            details={"reason": f"recommendation_not_ready:{recommendation_status}"},
        )
    ok, reasons = preflight(intent, action_registry=action_registry)
    if not ok:
        return SyntheticReceipt(
            execution_key=intent.execution_key,
            action_type=intent.action_type,
            business_id=intent.business_id,
            receipt_id=f"rcpt-preflight-{intent.execution_key[:12]}",
            ok=False,
            details={"reason": reasons},
        )
    # Deterministic synthetic outcome for the loop: idempotent by execution key.
    import hashlib

    outcome_seed = hashlib.sha256(intent.execution_key.encode()).hexdigest()
    return SyntheticReceipt(
        execution_key=intent.execution_key,
        action_type=intent.action_type,
        business_id=intent.business_id,
        receipt_id=f"rcpt-synthetic-{outcome_seed[:12]}",
        ok=True,
        details={
            "mode": "dry_run",
            "simulated_external_reference": f"sim-{outcome_seed[:16]}",
            "note": "SYNTHETIC - not a real merchant action",
        },
    )


@dataclass
class Reconciliation:
    """Requested-vs-actual reconciliation result for one execution."""

    execution_key: str
    requested_receipt_id: str
    actual_state: str  # reported | observed | unconfirmed
    matching: bool
    allow_retry: bool
    reason: str
    recorded_at: str = ""

    def __post_init__(self) -> None:
        self.recorded_at = self.recorded_at or _now_iso()


def reconcile(
    intent: ExecutionIntent,
    receipt: SyntheticReceipt,
    *,
    actual_state: str,
) -> Reconciliation:
    """Reconcile the requested payload against the actual recorded state.

    A potentially successful external action whose actual state is UNCONFIRMED
    must NOT be blindly retried: ``allow_retry`` is False. Retry is only
    permitted when the actual state confirms the request did not succeed.
    """
    if not receipt.ok:
        return Reconciliation(
            execution_key=intent.execution_key,
            requested_receipt_id=receipt.receipt_id,
            actual_state=actual_state,
            matching=False,
            allow_retry=False,
            reason="receipt_failed",
        )
    if actual_state == "reported":
        return Reconciliation(
            execution_key=intent.execution_key,
            requested_receipt_id=receipt.receipt_id,
            actual_state=actual_state,
            matching=True,
            allow_retry=False,  # potentially succeeded; must NOT blind-retry
            reason="reported_recorded_await_verification",
        )
    if actual_state == "observed_no_effect":
        return Reconciliation(
            execution_key=intent.execution_key,
            requested_receipt_id=receipt.receipt_id,
            actual_state=actual_state,
            matching=False,
            allow_retry=True,
            reason="observed_no_effect_eligible_for_retry",
        )
    return Reconciliation(
        execution_key=intent.execution_key,
        requested_receipt_id=receipt.receipt_id,
        actual_state=actual_state,
        matching=False,
        allow_retry=False,
        reason=f"unconfirmed_actual_state:{actual_state}",
    )