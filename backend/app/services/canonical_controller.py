"""Canonical decision controller (Batch 1: Choice surfaces).

Migrates the three Batch 1 surfaces onto the single policy-checked AI choke
point (``ai_gateway.systemone_reason``) WITHOUT ever letting Jev change a
decision. This is the "verify-then-finalize" pattern: the surface's existing
deterministic decision is authoritative; Jev contributes advisory confidence /
an alternative that is validated against the surface's canonical contract and
recorded only as shadow evidence.

Surfaces under control (MIGRATION_MATRIX Batch 1):
    recovery.rank            Choice over rank buckets
    recovery.action_type     Choice over CANONICAL_ACTION_TYPES
    audit.root_cause_bucket  Choice over root-cause taxonomy (hypothesis keys)

Surfaces under control (MIGRATION_MATRIX Batch 2):
    inventory.stockout_tier       Choice over INVENTORY_STATUS_TIERS
    inventory.anomaly_triage      Choice over ANOMALY_TRIAGE_BUCKETS

Surfaces under control (MIGRATION_MATRIX Batch 3):
    procurement.reorder_urgency   Choice over REORDER_URGENCY_BANDS
    pricing.margin_erosion_risk   Choice over MARGIN_EROSION_BANDS
    report.finding_priority       Choice over FINDING_PRIORITY_TOKENS

Every call, regardless of Jev availability:
    * PRECONDITION: deterministic_decision comes from the owner module (the
      surface's existing logic) -- this controller never manufactures one.
    * Jev is consulted in shadow mode only (default): its suggestion can never
      be surfaced as the final decision.
    * The final decision is ALWAYS the deterministic decision.
    * If Jev suggests an out-of-contract key, the suggestion is discarded and
      flagged (risk_flags=["JEV_OUT_OF_CONTRACT"]) -- the output gate equivalent
      for the canonical controller.
    * Every outcome is captured to the AI call ledger + shadow parity JSONL with
      model version, capsule hash, provider, latency, source label (MASTER_PLAN
      sec 6).

The three entry points (``canonical_rank``, ``canonical_action_type``,
``canonical_root_cause``) keep the exact production signatures their owner
modules already use so integration is a one-line substitution per surface.
"""
from __future__ import annotations

import time
from typing import Any

from app.orchestration.contracts import (
    ANOMALY_TRIAGE_BUCKETS,
    CANONICAL_ACTION_TYPES,
    FINDING_PRIORITY_TOKENS,
    INVENTORY_STATUS_TIERS,
    MARGIN_EROSION_BANDS,
    REORDER_URGENCY_BANDS,
)
from app.security.privacy_firewall import build_capsule_for_payload
from app.services.ai_gateway import systemone_reason
from app.services.shadow_capture import ShadowParityRecorder

RANK_BUCKETS = frozenset({"TOP", "HIGH", "MEDIUM", "LOW", "DO_NOTHING"})
ROOT_CAUSE_BUCKETS = frozenset({
    "REORDER_THRESHOLD_LOW",
    "SUPPLIER_LEAD_TIME",
    "LOW_DEMAND",
    "SUPPLIER_COST_INCREASE",
    "SELLING_PRICE_MISMATCH",
    "EXCESSIVE_DISCOUNTING",
    "MISSING_COST_DATA",
    "INSUFFICIENT_CASH_DATA",
    "SLOW_STOCK_CONVERSION",
    "INVENTORY_CASH_TRAPPED",
    "EXPIRY_REMINDER",
    "NO_COMPLIANCE_SIGNAL",
    "UNCERTAIN",
})

DEFAULT_CAPABILITY_RANK = "recovery.rank"
DEFAULT_CAPABILITY_ACTION = "recovery.action_type"
DEFAULT_CAPABILITY_ROOT = "audit.root_cause_bucket"
DEFAULT_CAPABILITY_STOCKOUT_TIER = "inventory.stockout_tier"
DEFAULT_CAPABILITY_ANOMALY_TRIAGE = "inventory.anomaly_triage"
DEFAULT_CAPABILITY_REORDER_URGENCY = "procurement.reorder_urgency"
DEFAULT_CAPABILITY_MARGIN_EROSION = "pricing.margin_erosion_risk"
DEFAULT_CAPABILITY_FINDING_PRIORITY = "report.finding_priority"


class CanonicalControllerError(Exception):
    """Raised when the surface violates the canonical controller contract."""


def _normalize(decision: str | None) -> str:
    d = (decision or "").strip().upper()
    return "DO_NOTHING" if d == "" else d


def _record_shadow(
    *,
    capability: str,
    deterministic_decision: str,
    jev_suggested: str | None,
    jev_source: str,
    agree: bool,
    decision: str,
    risk_flags: list[str],
    latency_ms: float,
    capsule_hash: str,
    recorder: ShadowParityRecorder | None = None,
) -> None:
    try:
        (recorder or ShadowParityRecorder()).record(
            {
                "capability": capability,
                "deterministic": deterministic_decision,
                "jev_suggested": jev_suggested,
                "jev_source": jev_source,
                "agree": agree,
                "decision": decision,
                "risk_flags": risk_flags,
                "latency_ms": latency_ms,
                "capsule_hash": capsule_hash,
                "model": "jev-1.13.0",
                "provider": jev_source,
                "source_label": "deterministic_authoritative",
            }
        )
    except Exception:
        pass  # ledger is best-effort; never blocks a decision


def _capture_outcome_ledger(
    *,
    payload: dict[str, Any],
    capability: str,
    deterministic_decision: str,
    source: str,
    jev_suggested: str | None,
    agree: bool,
    risk_flags: list[str],
    capsule_hash: str,
    model: str,
    provider: str,
    latency_ms: float,
) -> None:
    """Best-effort capture of one decision->evidence row (MASTER_PLAN sec 17).

    Only when ``settings.AI_OUTCOME_LEDGER_PATH`` is configured. Never blocks
    or changes a decision; every failure is swallowed (capture is optional).
    """
    try:
        from app.config import get_settings

        path = getattr(get_settings(), "AI_OUTCOME_LEDGER_PATH", "")
        if not path:
            return
        from app.services.outcome_ledger import OutcomeLedger, derive_decision_key

        business_id = str(payload.get("business_id") or "")
        decision_key = derive_decision_key(
            business_id=business_id or capsule_hash,
            capability=capability,
            deterministic_decision=deterministic_decision,
        )
        OutcomeLedger(path).record(
            decision_key=decision_key,
            capability=capability,
            deterministic_decision=deterministic_decision,
            source=source,
            jev_suggested=jev_suggested,
            agree=agree,
            risk_flags=risk_flags,
            capsule_hash=capsule_hash,
            model=model,
            provider=provider,
            latency_ms=latency_ms,
        )
    except Exception:
        pass  # outcome capture is best-effort; never blocks a decision


def _validate_action_type(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for recovery.action_type: only contract keys are usable."""
    if suggestion is None:
        return None, []
    if suggestion in CANONICAL_ACTION_TYPES:
        return suggestion, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_root_cause(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    s = (suggestion or "").strip().upper()
    if s in ROOT_CAUSE_BUCKETS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_rank(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for recovery.rank: only rank-bucket keys are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in RANK_BUCKETS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_stockout_tier(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for inventory.stockout_tier: only contract tier keys are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in INVENTORY_STATUS_TIERS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_anomaly_triage(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for inventory.anomaly_triage: only triage buckets are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in ANOMALY_TRIAGE_BUCKETS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_reorder_urgency(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for procurement.reorder_urgency: only urgency bands are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in REORDER_URGENCY_BANDS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_margin_erosion(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for pricing.margin_erosion_risk: only margin bands are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in MARGIN_EROSION_BANDS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


def _validate_finding_priority(suggestion: str | None, deterministic_decision: str) -> tuple[str | None, list[str]]:
    """Output-gate for report.finding_priority: only severity tokens are usable."""
    if suggestion is None:
        return None, []
    s = suggestion.strip().upper()
    if s in FINDING_PRIORITY_TOKENS:
        return s, []
    return None, ["JEV_OUT_OF_CONTRACT"]


async def canonical_decision(
    *,
    payload: dict[str, Any],
    deterministic_decision: str,
    capability: str,
    purpose: str,
    question: str,
    contract: frozenset[str] | None = None,
    client: Any | None = None,
    validate_suggestion: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """Shared verify-then-finalize flow for every Batch 1 surface."""
    start = time.monotonic()
    base_decision = _normalize(deterministic_decision)

    if contract is not None and base_decision not in contract:
        raise CanonicalControllerError(
            f"deterministic decision {base_decision!r} not in surface contract"
        )

    capsule = build_capsule_for_payload(payload, capability=capability, purpose=purpose)

    # Jev consults in shadow mode; the deterministic decision is authoritative.
    result = await systemone_reason(
        payload,
        capability=capability,
        purpose=purpose,
        deterministic_decision=base_decision,
        question=question,
        client=client,
        shadow=True,
        allowed_suggestions=contract,
        allowed_decisions=contract,
    )
    latency = (time.monotonic() - start) * 1000

    suggestion = result.get("alternative_decision")
    surface_flags: list[str] = []
    if validate_suggestion is not None:
        suggestion, surface_flags = validate_suggestion(suggestion, base_decision)

    risk_flags = list(result.get("risk_flags") or []) + surface_flags
    agree = suggestion is None or suggestion == base_decision

    _record_shadow(
        capability=capability,
        deterministic_decision=base_decision,
        jev_suggested=result.get("alternative_decision"),
        jev_source=result.get("source", "fallback"),
        agree=agree,
        decision=base_decision,
        risk_flags=risk_flags,
        latency_ms=latency,
        capsule_hash=capsule.capsule_hash,
        recorder=recorder,
    )

    _capture_outcome_ledger(
        payload=payload,
        capability=capability,
        deterministic_decision=base_decision,
        jev_suggested=result.get("alternative_decision"),
        source=result.get("source", "fallback"),
        agree=agree,
        risk_flags=risk_flags,
        capsule_hash=capsule.capsule_hash,
        model="jev-1.13.0",
        provider=result.get("source", "fallback"),
        latency_ms=latency,
    )

    return {
        "decision": base_decision,          # deterministic ALWAYS wins
        "source": result.get("source", "fallback"),
        "confidence": result.get("confidence", 0.0),
        "reasoning": result.get("reasoning", ""),
        "evidence_ids": result.get("evidence_ids", []),
        "risk_flags": risk_flags,
        "alternative_decision": suggestion,  # validated Jev suggestion (advisory only)
        "challenge": result.get("challenge", False),
        "latency_ms": latency,
        "jev_consulted": result.get("jev_consulted", False),
    }


async def canonical_rank(
    *,
    payload: dict[str, Any],
    deterministic_bucket: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """recovery.rank -- Choice over rank buckets."""
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_bucket,
        capability=DEFAULT_CAPABILITY_RANK,
        purpose="resolve ambiguity in recovery candidate ranking",
        question="Which recovery rank bucket is the safest, most defensible choice?",
        contract=RANK_BUCKETS,
        client=client,
        validate_suggestion=_validate_rank,
        recorder=recorder,
    )


async def canonical_action_type(
    *,
    payload: dict[str, Any],
    deterministic_action: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """recovery.action_type -- Choice over CANONICAL_ACTION_TYPES."""
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_action,
        capability=DEFAULT_CAPABILITY_ACTION,
        purpose="resolve ambiguity in the recovery action type",
        question="Which canonical recovery action is the safest choice?",
        contract=CANONICAL_ACTION_TYPES,
        client=client,
        validate_suggestion=_validate_action_type,
        recorder=recorder,
    )


async def canonical_root_cause(
    *,
    payload: dict[str, Any],
    deterministic_bucket: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """audit.root_cause_bucket -- Choice over root-cause taxonomy."""
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_bucket,
        capability=DEFAULT_CAPABILITY_ROOT,
        purpose="resolve ambiguity in the root-cause bucket",
        question="Which root-cause bucket is the safest, most supported choice?",
        contract=ROOT_CAUSE_BUCKETS,
        client=client,
        validate_suggestion=_validate_root_cause,
        recorder=recorder,
    )


async def canonical_stockout_tier(
    *,
    payload: dict[str, Any],
    deterministic_tier: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """inventory.stockout_tier -- Choice over INVENTORY_STATUS_TIERS.

    The deterministic tier comes from the owner module
    (``app.analytics.metrics.classify_tier``, itself a wrapper over the canonical
    ``classify_status``). Jev contributes advisory confidence over the same
    ladder; the deterministic tier always wins.
    """
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_tier,
        capability=DEFAULT_CAPABILITY_STOCKOUT_TIER,
        purpose="resolve ambiguity in the stockout urgency tier",
        question="Which stockout urgency tier is the safest, most defensible choice?",
        contract=INVENTORY_STATUS_TIERS,
        client=client,
        validate_suggestion=_validate_stockout_tier,
        recorder=recorder,
    )


async def canonical_anomaly_triage(
    *,
    payload: dict[str, Any],
    deterministic_bucket: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """inventory.anomaly_triage -- Choice over ANOMALY_TRIAGE_BUCKETS.

    Ground-truth pre-req (MIGRATION_MATRIX Batch 2) is satisfied by
    ``app.services.anomaly_triage`` persisting detector output as findings;
    the deterministic triage bucket is the detector's own signal. Jev advisory
    only.
    """
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_bucket,
        capability=DEFAULT_CAPABILITY_ANOMALY_TRIAGE,
        purpose="resolve ambiguity in the anomaly triage bucket",
        question="Which anomaly triage bucket is the safest, most supported choice?",
        contract=ANOMALY_TRIAGE_BUCKETS,
        client=client,
        validate_suggestion=_validate_anomaly_triage,
        recorder=recorder,
    )


async def canonical_reorder_urgency(
    *,
    payload: dict[str, Any],
    deterministic_band: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """procurement.reorder_urgency -- Choice over REORDER_URGENCY_BANDS.

    The deterministic band comes from the owner module
    (``app.services.reorder_urgency.reorder_urgency_band``) over canonical
    days-of-supply. The prompt states the window explicitly (days of supply,
    never days-since-last-sale; DEAD items are excluded from REORDER). Jev
    advisory only.
    """
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_band,
        capability=DEFAULT_CAPABILITY_REORDER_URGENCY,
        purpose="score the reorder urgency ladder over days of supply",
        question="Which reorder urgency band is the safest, most defensible choice?",
        contract=REORDER_URGENCY_BANDS,
        client=client,
        validate_suggestion=_validate_reorder_urgency,
        recorder=recorder,
    )


async def canonical_margin_erosion(
    *,
    payload: dict[str, Any],
    deterministic_band: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """pricing.margin_erosion_risk -- Choice over MARGIN_EROSION_BANDS.

    The deterministic band comes from the owner module
    (``app.services.margin_erosion.margin_erosion_band``) over the canonical
    gross-margin ratio. Jev advisory only.
    """
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_band,
        capability=DEFAULT_CAPABILITY_MARGIN_EROSION,
        purpose="score the margin erosion band against the gross margin threshold set",
        question="Which margin erosion band is the safest, most defensible choice?",
        contract=MARGIN_EROSION_BANDS,
        client=client,
        validate_suggestion=_validate_margin_erosion,
        recorder=recorder,
    )


async def canonical_finding_priority(
    *,
    payload: dict[str, Any],
    deterministic_priority: str,
    client: Any | None = None,
    recorder: ShadowParityRecorder | None = None,
) -> dict[str, Any]:
    """report.finding_priority -- Choice over FINDING_PRIORITY_TOKENS.

    The deterministic priority is the finding's stored severity uppercased
    (``app.services.finding_service.finding_priority_token``); the severity
    string stays authoritative. Advisory only until verified outcomes exist
    (MIGRATION_MATRIX Batch 3).
    """
    return await canonical_decision(
        payload=payload,
        deterministic_decision=deterministic_priority,
        capability=DEFAULT_CAPABILITY_FINDING_PRIORITY,
        purpose="choose the finding priority over the severity contract",
        question="Which finding priority is the safest, most defensible choice?",
        contract=FINDING_PRIORITY_TOKENS,
        client=client,
        validate_suggestion=_validate_finding_priority,
        recorder=recorder,
    )