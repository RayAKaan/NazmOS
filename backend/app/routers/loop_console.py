"""Owner Loop Console (Phase 3K) — read-only surfaces over loop artifacts.

The Continuous Business Improvement Loop spine lives in
``app.services.business_loop``. The ONLY durable artifact it produces is the
V1 ``OutcomeLedger`` (verified outcomes); evidence / state snapshots /
opportunities / recommendations / cycle runs are in-memory during a cycle and
recomputed deterministically — they are never re-invented here.

This router REUSES existing read paths and adds no durable store:
    * verified outcomes: ``OutcomeLedger.verified_outcomes()`` /
      ``latest_verified_impact`` (same JSONL-free sqlite ledger the loop writes).
    * deterministic loop policy: the enumerated contracts and cycle policy
      knobs from ``business_loop.contracts`` / ``business_loop.cycle``.

Everything here is read-only (owner-gated via ``assert_business_access`` like
the dashboard), DLP-clean (opaque ids / banded signals only — no SKUs, no
plaintext business ids, no exact SAR values beyond the owner's own ledger).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import User, get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.services.business_loop.contracts import (
    AdvisorySource,
    CycleStage,
    GovernanceOutcome,
    ImpactKind,
    LoopSchemaVersion,
    OpportunityType,
    RecommendationStatus,
    RECOMMENDATION_TRANSITIONS,
    VerificationStatus,
)
from app.services.business_loop.cycle import CyclePolicy
from app.services.business_loop.opportunity import DEFAULT_RULE_OVERRIDES, RULE_VERSIONS
from app.services.cycle_run_repository import PostgresCycleRepository
from app.services.loop_console_readmodel import build_cycle_read_model, build_cycle_summary
from app.services.outcome_ledger import OutcomeLedger

router = APIRouter(prefix="/loop-console", tags=["LoopConsole"])


async def _verify_business_access(db: AsyncSession, business_id: UUID, user: User) -> None:
    """Owner/team gate (same as dashboard) — denials recorded to AuditLog."""
    await assert_business_access(db, business_id, user)


def _ledger_path() -> str:
    return str(getattr(get_settings(), "AI_OUTCOME_LEDGER_PATH", "") or "")


async def _scoped_verified_rows(
    db: AsyncSession, business_id: UUID, path: str
) -> tuple[list[dict[str, Any]], float]:
    """V1-ledger rows exposed ONLY for this business's own cycle runs.

    The V1 OutcomeLedger has no tenant column; its ``decision_key`` derives
    from ``(tenant, execution_key, recommendation)`` and the cycle persists the
    exact ``outcome_key`` it wrote in ``state_output``. Scoping by the set of
    outcome_keys referenced by THIS business's cycle_runs therefore exposes
    exactly this business's verified outcomes — unrelated legacy rows stay
    invisible. Fails closed: a business with no linked runs exposes nothing.
    """
    repo = PostgresCycleRepository(db)
    allowed = await repo.outcome_keys(business_id)
    rows = OutcomeLedger(path).verified_outcomes()
    scoped = [r for r in rows if r.get("decision_key") in allowed]
    total = round(sum(float(r.get("actual_impact_sar") or 0) for r in scoped), 2)
    return scoped, total


@router.get("/policy")
async def get_loop_policy(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only deterministic loop policy — a DLP-clean static contract.

    Exposes which thresholds, rule versions, stage order, and lifecycle
    transitions the loop is bound to. Contains no merchant data.
    """
    await _verify_business_access(db, business_id, current_user)
    transitions = {
        src.value: sorted(dst.value for dst in dsts)
        for src, dsts in RECOMMENDATION_TRANSITIONS.items()
    }
    return {
        "schema_version": LoopSchemaVersion.V1.value,
        "stages": [s.value for s in CycleStage.ordered()],
        "stage_count": len(CycleStage.ordered()),
        "opportunity_types": [o.value for o in OpportunityType],
        "rule_versions": RULE_VERSIONS,
        "detection_thresholds": dict(DEFAULT_RULE_OVERRIDES),
        "impact_kinds": [i.value for i in ImpactKind],
        "governance_outcomes": [g.value for g in GovernanceOutcome],
        "recommendation_lifecycle": [r.value for r in RecommendationStatus],
        "recommendation_transitions": transitions,
        "verification_ladder": [v.value for v in VerificationStatus],
        "advisory_sources": [a.value for a in AdvisorySource],
        "cycle_bounds": {
            "cooldown_seconds": CyclePolicy.cooldown_seconds,
            "max_opportunities_per_cycle": CyclePolicy.max_opportunities_per_cycle,
            "max_recommendations_per_cycle": CyclePolicy.max_recommendations_per_cycle,
            "max_retries_per_stage": CyclePolicy.max_retries_per_stage,
            "stale_max_age_days": CyclePolicy.stale_max_age_days,
            "shariah_approved": CyclePolicy.shariah_approved,
        },
    }


@router.get("/outcomes/verified")
async def get_verified_outcomes(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only verified outcomes through the EXISTING V1 OutcomeLedger.

    Fails closed: when the ledger is not configured (empty path) or empty, an
    all-zero report is returned, never a fabricated number. Exposes only the
    rows this business's own cycle runs linked.
    """
    await _verify_business_access(db, business_id, current_user)
    path = _ledger_path()
    if not path:
        return {"configured": False, "verified_rows": 0, "total_verified_impact_sar": 0.0, "rows": []}
    rows, total = await _scoped_verified_rows(db, business_id, path)
    return {"configured": True, "verified_rows": len(rows), "total_verified_impact_sar": total, "rows": rows}


@router.get("/summary")
async def get_loop_summary(
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only loop summary: ledger configured + verified learning signal.

    Uses only the aggregate values already exposed by the existing V1 ledger,
    scoped to this business's own cycle-linked outcome rows. No new store, no
    writes.
    """
    await _verify_business_access(db, business_id, current_user)
    path = _ledger_path()
    rows: list[dict[str, Any]]
    if path:
        rows, total = await _scoped_verified_rows(db, business_id, path)
    else:
        rows, total = [], 0.0
    return {
        "configured": bool(path),
        "verified_rows": len(rows),
        "total_verified_impact_sar": total,
        "learning_eligible_rows": len(rows),
    }


@router.get("/cycles")
async def list_cycles(
    business_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only, paginated list of this business's cycle runs (newest first).

    Deterministic ordering (created_at DESC, cycle_id ASC) so pages never
    flip between requests. Items are DLP-clean summaries with banded impacts —
    no merchant data, no exact SAR beyond the owner's own view.
    """
    await _verify_business_access(db, business_id, current_user)
    repo = PostgresCycleRepository(db)
    runs, total = await repo.page(business_id, limit=limit, offset=offset)
    return {
        "items": [build_cycle_summary(r) for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(runs) < total,
    }


@router.get("/cycles/{cycle_id}")
async def get_cycle(
    cycle_id: str,
    business_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only detail read model for ONE cycle (tenant-scoped, composed).

    Composes only what the cycle persisted in ``state_output`` — identity,
    lifecycle ladder, state/evidence/opportunity/recommendation/advisory/
    governance/approval/execution/reconciliation/outcome/measurement/
    verification/learning/recovery/revalidation. Advisory/data surfaces are
    observability only: ``execution_authority`` is always ``"none"`` and no
    AI/Jev/approval surface is ever called to populate this model.
    """
    await _verify_business_access(db, business_id, current_user)
    repo = PostgresCycleRepository(db)
    run = await repo.load(business_id, cycle_id)
    if run is None:
        # Identical to the cross-tenant case: a guessed/foreign cycle id must
        # be indistinguishable from a missing one.
        raise HTTPException(404, "Cycle not found")
    return build_cycle_read_model(run)