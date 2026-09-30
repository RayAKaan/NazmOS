"""Canonical Intelligence API.

    GET  /api/v1/intelligence/context
    GET  /api/v1/intelligence/signals
    GET  /api/v1/intelligence/root-causes
    GET  /api/v1/intelligence/impacts
    GET  /api/v1/intelligence/recommendations
    GET  /api/v1/intelligence/recommendations/{id}
    GET  /api/v1/intelligence/decisions
    GET  /api/v1/intelligence/decisions/{id}
    GET  /api/v1/intelligence/alerts
    GET  /api/v1/intelligence/alerts/{id}
    POST /api/v1/intelligence/monitor
    POST /api/v1/intelligence/analyze
    POST /api/v1/intelligence/copilot

Deliberately absent: any execution endpoint. Execution belongs to the Loop
(``/api/v1/actions``, ``/api/v1/agent``); Intelligence only produces candidates
for Governance to evaluate.

Security: every route requires authentication, authorizes business access through
the shared ``assert_business_access`` gate (which is also what establishes the RLS
tenant context), validates input via Pydantic, and uses bounded pagination. No
endpoint discloses the existence of another tenant's artifacts.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.middleware.business_access import assert_business_access
from app.database.models import User
from app.schemas.intelligence import (
    AlertListOut,
    AlertOut,
    BusinessContextOut,
    CopilotAnswerOut,
    CopilotRequest,
    DecisionCandidateListOut,
    DecisionCandidateOut,
    ImpactListOut,
    IntelligenceRunOut,
    RecommendationListOut,
    RecommendationOut,
    RootCauseListOut,
    RunRequest,
    SignalListOut,
    SignalOut,
)
from app.services.intelligence import (
    answer_from_run,
    build_business_context,
    run_intelligence,
)
from app.services.intelligence import api_mappers as mappers
from app.services.intelligence.context import OrbitStateUnavailable
from app.services.intelligence.contracts import (
    IntelligenceRun,
    IntelligenceRunStatus,
)

router = APIRouter(prefix="/api/v1/intelligence", tags=["Intelligence"])

MAX_PAGE = 200
DEFAULT_PAGE = 50


async def _authorize(session: AsyncSession, business_id: UUID, user: User) -> None:
    """Enforce business access.

    Delegates to the shared gate. This is the same check the existing
    Intelligence router uses, so there is exactly one tenant-isolation path.
    A denial surfaces as 404/403 without revealing whether the record exists.
    """
    await assert_business_access(session, business_id, user)


def _paginate(items, limit: int, offset: int):
    return items[offset : offset + limit], len(items)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


# ── Monitor / analyze ────────────────────────────────────────────────────────

async def _run(session, request: RunRequest) -> IntelligenceRun:
    return await run_intelligence(
        session,
        request.business_id,
        state_version=request.state_version,
        trigger=request.trigger,
        enable_advisory=request.enable_advisory,
        shariah_approved=request.shariah_approved,
        detectors=request.detectors,
    )


@router.post("/monitor", response_model=IntelligenceRunOut)
async def monitor_business(
    request: RunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the canonical Intelligence pipeline for a business.

    Produces context → signals → root causes → impact → recommendations →
    bounded advisory → decision candidates (Governance-evaluated) → alerts.
    Intelligence never executes anything.
    """
    await _authorize(db, request.business_id, current_user)
    run = await _run(db, request)
    if run.status is IntelligenceRunStatus.FAILED:
        # 422/409 semantics: the request was valid but cannot be satisfied
        # because the required canonical Orbit state does not exist.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "intelligence_run_failed",
                "warnings": run.warnings,
            },
        )
    return IntelligenceRunOut(
        run_id=run.run_id,
        business_id=run.business_id,
        state_version=run.state_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status.value,
        signals=[mappers.signal_out(s) for s in run.signals],
        root_causes=[mappers.root_cause_out(c) for c in run.root_causes],
        impacts=[mappers.impact_out(i) for i in run.impacts],
        recommendations=[mappers.recommendation_out(r) for r in run.recommendations],
        decision_candidates=[mappers.decision_candidate_out(c) for c in run.decision_candidates],
        alerts=[mappers.alert_out(a) for a in run.alerts],
        evidence_ids=list(run.evidence_ids),
        warnings=list(run.warnings),
        failed_detectors=list(run.failed_detectors),
        detector_errors=dict(run.detector_errors),
    )


@router.post("/analyze", response_model=IntelligenceRunOut)
async def analyze_business(
    request: RunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze a business through the same canonical pipeline as ``/monitor``.

    ``/analyze`` is an alias of the canonical pipeline, not a second
    intelligence engine.
    """
    await _authorize(db, request.business_id, current_user)
    return await monitor_business(request, db=db, current_user=current_user)


# ── Context ──────────────────────────────────────────────────────────────────

@router.get("/context", response_model=BusinessContextOut)
async def get_context(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Canonical BusinessContext projected from Orbit state."""
    await _authorize(db, business_id, current_user)
    try:
        context = await build_business_context(
            db, business_id, state_version=state_version
        )
    except OrbitStateUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "orbit_state_unavailable", "message": str(exc)},
        )
    return mappers.context_out(context)


# ── Signals ──────────────────────────────────────────────────────────────────

@router.get("/signals", response_model=SignalListOut)
async def list_signals(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    domain: Optional[str] = Query(None, max_length=32),
    severity: Optional[str] = Query(None, max_length=16),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Signals from the latest Intelligence run (deterministic, no side effects)."""
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    signals = run.signals
    if domain:
        signals = [s for s in signals if s.domain == domain]
    if severity:
        signals = [s for s in signals if s.severity.value == severity]
    items, total = _paginate(signals, limit, offset)
    return SignalListOut(
        items=[mappers.signal_out(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Root causes ──────────────────────────────────────────────────────────────

@router.get("/root-causes", response_model=RootCauseListOut)
async def list_root_causes(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    cause_type: Optional[str] = Query(None, max_length=64),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Root-cause hypotheses with support level and counter-evidence."""
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    causes = run.root_causes
    if cause_type:
        causes = [c for c in causes if c.cause_type == cause_type]
    items, total = _paginate(causes, limit, offset)
    return RootCauseListOut(
        items=[mappers.root_cause_out(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Impacts ──────────────────────────────────────────────────────────────────

@router.get("/impacts", response_model=ImpactListOut)
async def list_impacts(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    impact_kind: Optional[str] = Query(
        None, alias="kind", description="POTENTIAL | EXPECTED"
    ),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Quantified impact, always labelled by kind (never collapsed)."""
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    impacts = run.impacts
    if impact_kind:
        impacts = [i for i in impacts if i.kind.value == impact_kind]
    items, total = _paginate(impacts, limit, offset)
    return ImpactListOut(
        items=[mappers.impact_out(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Recommendations ──────────────────────────────────────────────────────────

@router.get("/recommendations", response_model=RecommendationListOut)
async def list_recommendations(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    action_type: Optional[str] = Query(None, max_length=64),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deterministic candidate recommendations, ranked."""
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    recs = run.recommendations
    if action_type:
        recs = [r for r in recs if r.action_type == action_type]
    items, total = _paginate(recs, limit, offset)
    return RecommendationListOut(
        items=[mappers.recommendation_out(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationOut)
async def get_recommendation(
    recommendation_id: UUID,
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    await _authorize(db, business_id, current_user)
    for rec in run.recommendations:
        if rec.recommendation_id == recommendation_id:
            return mappers.recommendation_out(rec)
    raise _not_found("Recommendation")


# ── Decision candidates ──────────────────────────────────────────────────────

@router.get("/decisions", response_model=DecisionCandidateListOut)
async def list_decision_candidates(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Decision candidates after Governance evaluation.

    Reading this does NOT approve anything and does NOT execute anything.
    """
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    items, total = _paginate(run.decision_candidates, limit, offset)
    return DecisionCandidateListOut(
        items=[mappers.decision_candidate_out(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/decisions/{decision_id}", response_model=DecisionCandidateOut)
async def get_decision_candidate(
    decision_id: UUID,
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    for cand in run.decision_candidates:
        if cand.decision_id == decision_id:
            return mappers.decision_candidate_out(cand)
    raise _not_found("Decision candidate")


# ── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertListOut)
async def list_alerts(
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    alert_severity: Optional[str] = Query(None, alias="severity", max_length=32),
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    alerts = run.alerts
    if alert_severity:
        alerts = [a for a in alerts if a.severity.value == alert_severity]
    items, total = _paginate(alerts, limit, offset)
    return AlertListOut(
        items=[mappers.alert_out(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: UUID,
    business_id: UUID,
    state_version: Optional[str] = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _authorize(db, business_id, current_user)
    run = await _run(db, RunRequest(business_id=business_id, state_version=state_version))
    for alert in run.alerts:
        if alert.alert_id == alert_id:
            return mappers.alert_out(alert)
    raise _not_found("Alert")


# ── Owner Copilot ────────────────────────────────────────────────────────────

@router.post("/copilot", response_model=CopilotAnswerOut)
async def copilot(
    request: CopilotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask the Owner Copilot a question.

    The Copilot is a read/explanation layer: it answers strictly from existing
    Orbit evidence and Intelligence artifacts, cites what it used, and says
    "insufficient data" rather than inventing a number.
    """
    await _authorize(db, request.business_id, current_user)
    run = await _run(
        db,
        RunRequest(
            business_id=request.business_id,
            state_version=request.state_version,
            enable_advisory=request.enable_advisory,
        ),
    )
    context = None
    try:
        context = await build_business_context(
            db, request.business_id, state_version=request.state_version
        )
    except OrbitStateUnavailable:
        context = None
    return mappers.copilot_answer_out(answer_from_run(request.question, run, context))
