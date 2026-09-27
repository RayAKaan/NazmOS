"""Phase 4G — read-only read model for the Business Loop Command Center.

Pure, DB-free builders that transform a durable ``CycleRun`` (as rehydrated
by ``app.services.cycle_run_repository``) into DLP-clean, evidence-first
observability. The console NEVER mutates, NEVER re-invents artifacts, and
NEVER calls back into the AI/Jev/approval surfaces to populate itself — it
composes ONLY what the cycle already persisted in ``state_output``.

Lifecycle ladder (MASTER_PLAN §16.2 observability):
    NOT_RUN -> RUNNING -> BLOCKED -> EXECUTED -> MEASURED -> VERIFIED
              -> LEARNING_ELIGIBLE
``compute_lifecycle`` returns the highest achieved ladder step PLUS boolean
flags for every step. ``BLOCKED`` is an orthogonal interruption: a cycle that
was executed and verified before a later revalidation block still reports
``blocked=True`` AND ``executed/verified`` truthfully — unknown execution is
never collapsed into a generic failure or success badge.

DLP contract: no SKUs, no raw merchant payloads, no exact SAR values in list
summaries (impacts are banded); the owner-facing DETAIL model may carry exact
impact numbers for THIS business only (same owner data the V1 OutcomeLedger
already returns to them via ``verified_outcomes``).
"""
from __future__ import annotations

from typing import Any

from app.services.business_loop.cycle import CycleRun, CycleStageState
from app.services.business_loop.contracts import CycleStage
from app.services.business_loop.outcome_linkage import attribution_quality

READ_MODEL_VERSION = "1.0"

# Ladder order (highest achieved wins when multiple flags are true).
_LADDER_ORDER = (
    "learning_eligible",
    "verified",
    "measured",
    "executed",
    "blocked",
    "running",
    "not_run",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(state: dict[str, Any], key: str) -> dict[str, Any]:
    items = state.get(key)
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def _impact_band(value: Any) -> str | None:
    """Banded SAR signal for list summaries (DLP-clean, no exact amounts)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 250:
        return "under_250"
    if v < 1000:
        return "250_999"
    if v < 5000:
        return "1000_4999"
    return "5000_plus"


def compute_lifecycle(run: CycleRun) -> dict[str, Any]:
    """Highest-achieved lifecycle step + truth-opaque boolean flags."""
    state = _as_dict(getattr(run, "state_output", None))
    execution = _as_dict(state.get("execution"))
    outcome = _as_dict(state.get("outcome"))

    skipped = bool(execution.get("skipped"))
    receipt = _as_dict(execution.get("receipt"))
    receipt_ok = bool(receipt.get("ok"))
    has_execution = bool(execution.get("execution_key")) and not skipped

    flags: dict[str, bool] = {
        "not_run": run.stage_index == 0 and not run.completed and not run.last_error,
        "running": False,
        "blocked": False,
        "executed": has_execution and receipt_ok,
        "measured": False,
        "verified": False,
        "learning_eligible": bool(state.get("learning_eligible")),
    }
    flags["measured"] = (
        state.get("post_state_version") is not None
        and outcome.get("observed_impact_sar") is not None
    )
    flags["verified"] = str(outcome.get("verification_status", "")) == "verified"

    blocked = False
    if not run.completed:
        current_failed = (
            run.stage_index < len(run.stages)
            and run.stages[run.stage_index].status == "failed"
        )
        blocked = bool(run.last_error) or current_failed or run.stage_index >= len(run.stages)
    flags["blocked"] = blocked
    flags["running"] = not run.completed and not blocked and not flags["not_run"]

    status = "not_run"
    for key in _LADDER_ORDER:
        if flags[key]:
            status = key
            break
    return {"lifecycle_status": status, "flags": flags}


def _execution_section(state: dict[str, Any]) -> dict[str, Any]:
    execution = _as_dict(state.get("execution"))
    skipped = bool(execution.get("skipped"))
    execution_key = str(execution.get("execution_key", "") or "")
    receipt = _as_dict(execution.get("receipt"))
    return {
        "execution_authority": "none",  # read-only console holds no authority
        "executed": bool(execution_key) and not skipped and bool(receipt.get("ok")),
        "execution_failed": bool(execution_key) and not skipped and not bool(receipt.get("ok")),
        "skipped": skipped,
        "skip_reason": str(execution.get("reason", "") or ""),
        "action_type": str(execution.get("action_type", "") or ""),
        "attempt": int(execution.get("attempt", 1) or 1),
        "synthetic": bool(receipt.get("synthetic")),
        "receipt_present": bool(receipt),
    }


def _outcome_section(state: dict[str, Any]) -> dict[str, Any]:
    outcome = _as_dict(state.get("outcome"))
    return {
        "outcome_id": str(outcome.get("outcome_id", "") or ""),
        "verification_status": str(outcome.get("verification_status", "unverified") or "unverified"),
        "verification_method": str(outcome.get("verification_method", "") or ""),
        "measurement_window": str(outcome.get("measurement_window", "") or ""),
        "expected_impact_sar": outcome.get("expected_impact_sar"),
        "observed_impact_sar": outcome.get("observed_impact_sar"),
        "baseline_state_version": str(outcome.get("baseline_state_version", "") or ""),
        "post_action_state_version": str(outcome.get("post_action_state_version", "") or ""),
        "reason": str(outcome.get("reason", "") or ""),
    }


def build_cycle_summary(run: CycleRun) -> dict[str, Any]:
    """Compact, banded list item — safe to render for many cycles at once."""
    state = _as_dict(getattr(run, "state_output", None))
    lifecycle = compute_lifecycle(run)
    execution = _execution_section(state)
    outcome = _outcome_section(state)
    opportunity = _first(state, "opportunities")
    recommendation = _first(state, "recommendations")
    reconciliation = _as_dict(state.get("reconciliation"))

    flags = lifecycle["flags"]
    return {
        "cycle_id": run.cycle_id,
        "trigger": run.trigger,
        "created_at": run.created_at,
        "updated_at": getattr(run, "_updated_at", run.created_at),
        "completed": run.completed,
        "blocked": flags["blocked"],
        "last_error_type": _last_error_type(run),
        "revalidation_blocked": _last_error_type(run) == "revalidation_blocked",
        "lifecycle_status": lifecycle["lifecycle_status"],
        "flags": flags,
        "opportunity_type": str(opportunity.get("opportunity_type", "") or ""),
        "impact_band": _impact_band(opportunity.get("expected_impact_sar")),
        "recommendation_status": str(recommendation.get("status", "") or ""),
        "execution": {
            "executed": execution["executed"],
            "execution_failed": execution["execution_failed"],
            "skipped": execution["skipped"],
        },
        "reconciliation": {
            "allow_retry": bool(reconciliation.get("allow_retry")),
            "reason": str(reconciliation.get("reason", "") or ""),
        },
        "outcome": {
            "verification_status": outcome["verification_status"],
            "measured": bool(outcome.get("observed_impact_sar")),
        },
        "learning_eligible": flags["learning_eligible"],
        "stage_index": run.stage_index,
        "stage_count": len(run.stages),
    }


def _last_error_type(run: CycleRun) -> str:
    error = run.last_error or ""
    if error.startswith("revalidation_blocked:"):
        return "revalidation_blocked"
    if error:
        return "stage_error"
    return ""


def build_cycle_read_model(run: CycleRun) -> dict[str, Any]:
    """Full owner-facing detail model over ONE cycle (exact, tenant-scoped)."""
    state = _as_dict(getattr(run, "state_output", None))
    lifecycle = compute_lifecycle(run)
    snapshot = _as_dict(state.get("state"))
    opportunity = _first(state, "opportunities")
    recommendation = _first(state, "recommendations")
    advisory = _as_dict(state.get("advisory"))
    governance = _as_dict(state.get("governance"))
    approval = _as_dict(state.get("approval"))
    reconciliation = _as_dict(state.get("reconciliation"))
    linkage = _as_dict(state.get("outcome_linkage"))
    attachment = _as_dict(state.get("outcome_attachment"))
    revalidation = _as_dict(state.get("revalidation"))

    attribution = attribution_quality(
        verification_status=_outcome_section(state)["verification_status"],
        verification_method=_outcome_section(state)["verification_method"],
        observed_impact_sar=_outcome_section(state)["observed_impact_sar"],
        advisory_source=str(advisory.get("source", "") or ""),
        advisory_provider=str(advisory.get("provider", "") or ""),
        advisory_validated=bool(advisory.get("validation_passed", True)),
    )

    outcome = _outcome_section(state)
    domains = _as_dict(snapshot.get("domains"))
    quality_flags = snapshot.get("quality_flags") or []
    domain_states = [
        {
            "domain": name,
            "missing_fields": d.get("missing_fields", []) if isinstance(d, dict) else [],
            "stale": bool(d.get("stale", False)) if isinstance(d, dict) else False,
        }
        for name, d in domains.items()
    ]

    return {
        "read_model_version": READ_MODEL_VERSION,
        "cycle": {
            "cycle_id": run.cycle_id,
            "tenant_id": run.tenant_id,
            "business_id": run.business_id,
            "trigger": run.trigger,
            "created_at": run.created_at,
            "updated_at": getattr(run, "_updated_at", run.created_at),
            "completed": run.completed,
            "stage_index": run.stage_index,
            "stage_count": len(run.stages),
            "schema_version": run.state_output.get("schema_version", "loop-v1"),
            "starting_state_version": run.starting_state_version,
            "evidence_watermark": run.evidence_watermark,
        },
        "lifecycle": lifecycle,
        "state": {
            "state_version": str(snapshot.get("state_version", "") or ""),
            "snapshot_created_at": str(snapshot.get("created_at", "") or ""),
            "domains": domain_states,
            "quality_flags": [str(f) for f in quality_flags],
            "evidence_count": int(state.get("evidence_count", 0) or 0),
            "stale": str("stale") in {str(f) for f in quality_flags},
            "missing": str("missing") in {str(f) for f in quality_flags},
            "partial": str("partial") in {str(f) for f in quality_flags},
        },
        "evidence": {
            "watermark": run.evidence_watermark,
            "accepted_count": int(state.get("evidence_count", 0) or 0),
        },
        "opportunity": {
            "opportunity_id": str(opportunity.get("opportunity_id", "") or ""),
            "opportunity_type": str(opportunity.get("opportunity_type", "") or ""),
            "rule_version": str(opportunity.get("rule_version", "") or ""),
            "lifecycle_status": str(opportunity.get("lifecycle_status", "open") or "open"),
            "state_version": str(opportunity.get("state_version", "") or ""),
            "potential_impact_sar": opportunity.get("potential_impact_sar"),
            "expected_impact_sar": opportunity.get("expected_impact_sar"),
            "impact_band": _impact_band(opportunity.get("expected_impact_sar")),
        },
        "recommendation": {
            "recommendation_id": str(recommendation.get("recommendation_id", "") or ""),
            "version": int(recommendation.get("version", 1) or 1),
            "status": str(recommendation.get("status", "") or ""),
            "action_type": str(recommendation.get("action_type", "") or ""),
            "policy_version": str(recommendation.get("policy_version", "") or ""),
            "advisory_validated": bool(recommendation.get("advisory_validated")),
            "expires_at": str(recommendation.get("expires_at", "") or ""),
            "evidence_id_count": len(recommendation.get("evidence_ids") or []),
        },
        "advisory": {
            "source": str(advisory.get("source", "") or ""),
            "provider": str(advisory.get("provider", "") or ""),
            "model": str(advisory.get("model", "") or ""),
            "validation_passed": bool(advisory.get("validation_passed", False)),
            "confidence": advisory.get("confidence"),
            "risk_flag_count": len(advisory.get("risk_flags") or []),
            "attribution_quality": attribution,
        },
        "governance": {
            "outcome": str(governance.get("outcome", "") or ""),
            "policy_version": str(governance.get("policy_version", "") or ""),
            "reasons": [str(r) for r in (governance.get("reasons") or [])],
            "recommendation_id": str(governance.get("recommendation_id", "") or ""),
            "certified_by": str(governance.get("certified_by", "") or ""),
            "shariah_reviewed": bool(governance.get("shariah_reviewed")),
        },
        "approval": {
            "mode": str(approval.get("mode", "") or ""),
            "note": str(approval.get("note", "") or ""),
            "simulated": str(approval.get("mode", "")) == "simulated_owner_approval",
        },
        "execution": _execution_section(state),
        "reconciliation": {
            "allow_retry": bool(reconciliation.get("allow_retry")),
            "reason": str(reconciliation.get("reason", "") or ""),
        },
        "outcome": outcome,
        "measurement": {
            "observed_impact_sar": outcome["observed_impact_sar"],
            "expected_impact_sar": outcome["expected_impact_sar"],
            "impact_delta_sar": linkage.get("impact_delta_sar"),
            "measurement_window": outcome["measurement_window"],
            "measurement_evidence_count": int(linkage.get("measurement_evidence_count", 0) or 0),
            "measured": outcome["observed_impact_sar"] is not None,
        },
        "verification": {
            "verification_status": outcome["verification_status"],
            "verified": outcome["verification_status"] == "verified",
            "distinct_snapshots": bool(
                outcome["baseline_state_version"]
                and outcome["post_action_state_version"]
                and outcome["baseline_state_version"] != outcome["post_action_state_version"]
            ),
            "reason": outcome["reason"],
        },
        "learning": {
            "eligible": bool(state.get("learning_eligible")),
            "reasons": [str(r) for r in (state.get("learning_reasons") or [])],
            "artifact": str(_as_dict(state.get("learning")).get("artifact", "") or ""),
        },
        "recovery": {
            "blocked": lifecycle["flags"]["blocked"],
            "last_error_type": _last_error_type(run),
            "last_error": run.last_error,
            "allow_retry": bool(reconciliation.get("allow_retry")),
            "revalidation": {
                "ok": bool(revalidation.get("ok", False)),
                "status": str(revalidation.get("status", "") or ""),
                "recomputed_state_version": str(revalidation.get("recomputed_state_version", "") or ""),
                "persisted_state_version": str(revalidation.get("persisted_state_version", "") or ""),
                "recomputed_watermark": str(revalidation.get("recomputed_watermark", "") or ""),
                "persisted_watermark": str(revalidation.get("persisted_watermark", "") or ""),
                "cross_scope": int(revalidation.get("cross_scope", 0) or 0),
            },
            "execution_authority": "none",
        },
        "links": {
            "outcome_key": str(attachment.get("outcome_key", "") or linkage.get("outcome_key", "") or ""),
            "attached": bool(attachment.get("recorded")),
            "row_present": bool(attachment.get("row_present")),
            "row_verified": bool(attachment.get("row_verified")),
            "attach_reason": str(attachment.get("reason", "") or ""),
            "execution_key": str(_as_dict(state.get("execution")).get("execution_key", "") or ""),
        },
        "stage_timeline": [
            {
                "stage": s.stage.value if hasattr(s.stage, "value") else str(s.stage),
                "status": s.status,
                "attempts": s.attempts,
                "error": s.error,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
            }
            for s in run.stages
        ],
        "audit": {
            "schema_version": READ_MODEL_VERSION,
            "terminal": run.completed,
            "immutable": run.completed,
        },
    }


__all__ = [
    "READ_MODEL_VERSION",
    "build_cycle_read_model",
    "build_cycle_summary",
    "compute_lifecycle",
]