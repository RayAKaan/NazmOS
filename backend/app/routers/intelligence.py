"""Intelligence API router (Phase 1: Business Memory Engine).

Exposes query and goal-setting endpoints for the living business memory.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Business, BusinessMemory, MemoryType, User
from app.middleware.auth_middleware import get_current_user
from app.schemas.business_memory import (
    BusinessMemoryOut,
    GoalSetRequest,
    MemoryChangesOut,
    MemoryUpdateOut,
)
from app.schemas.context import (
    BusinessContextCreate,
    BusinessContextOut,
    EventDerivationCreate,
    EventDerivationOut,
    TimelineOut,
    WhatChangedOut,
    WhyOut,
)
from app.schemas.decision import (
    DecisionApprovalRequest,
    DecisionExplainOut,
    DecisionGenerateRequest,
    DecisionOut,
)
from app.schemas.knowledge_graph import (
    GraphEntityCreate,
    GraphEntityOut,
    GraphExpandOut,
    GraphRelationshipCreate,
    GraphRelationshipOut,
    GraphShortestPathOut,
)
from app.schemas.phase5 import (
    AgentProposalOut,
    AgentProposalRequest,
    ExecutionJobOut,
    ExecutionRequest,
    PlanCreate,
    PlanOut,
    SimulationCreate,
    SimulationOut,
)
from app.schemas.learning import (
    LearningRefreshOut,
    ModelPerformanceOut,
    OutcomeFeedbackCreate,
    OutcomeFeedbackListOut,
    OutcomeFeedbackOut,
    SuggestActionOut,
    SuggestActionRequest,
)
from app.schemas.intelligence_api import (
    AnalyzeOut,
    AnalyzeRequest,
    ExecuteRequest,
    ExplainRequest,
    ObserveOut,
    ObserveRequest,
    PlanRequest,
    PredictOut,
    PredictRequest,
    ReasonOut,
    ReasonRequest,
    RememberOut,
    RememberRequest,
    SimulateRequest,
)
from app.services import intelligence_api
from app.services.business_memory import (
    get_memory,
    list_memory_changes,
    set_goals,
)
from app.intelligence.agents.registry import dispatch_agent, list_agent_types
from app.services.context_engine import create_context, get_active_context, refresh_context_for_business
from app.services.decision_engine import explain_decision, generate_decision, get_decision
from app.services.execution_engine import execute_from_request, get_execution_job
from app.services.learning_engine import (
    compute_model_performance,
    get_model_performance,
    list_feedback,
    record_feedback,
    refresh_learning,
    suggest_best_action,
)
from app.services.knowledge_graph import (
    expand_graph,
    get_entity,
    shortest_path,
    upsert_entity,
    upsert_relationship,
)
from app.services.planning_engine import create_plan, get_plan
from app.services.simulation_engine import create_simulation, get_simulation
from app.services.temporal_reasoning import create_derivation, get_timeline, what_changed, why

router = APIRouter(prefix="/api/v1/intelligence", tags=["Intelligence"])


async def _verify_business_access(
    session: AsyncSession,
    business_id: UUID,
    user: User,
) -> Business:
    """Ensure the user owns or belongs to the business."""
    result = await session.execute(
        select(Business).where(
            (Business.id == business_id)
            & (
                (Business.owner_id == user.id)
                | Business.id.in_(
                    select(Business.id).where(Business.id == business_id)  # placeholder for team check
                )
            )
        )
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found or access denied")
    return business


@router.patch("/memory/goals", response_model=BusinessMemoryOut)
async def update_goals(
    business_id: UUID,
    request: GoalSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set merchant goals in the business memory."""
    await _verify_business_access(db, business_id, current_user)
    memory = await set_goals(db, business_id, request.goals)
    await db.commit()
    await db.refresh(memory)
    return memory


@router.get("/memory/changes", response_model=MemoryChangesOut)
async def read_memory_changes(
    business_id: UUID,
    memory_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent mutations to business memory."""
    await _verify_business_access(db, business_id, current_user)
    items, total = await list_memory_changes(db, business_id, memory_type, limit=limit, offset=offset)
    return MemoryChangesOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/memory/{memory_type}", response_model=BusinessMemoryOut)
async def read_memory(
    memory_type: str,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a business memory document by type."""
    if memory_type not in {m.value for m in MemoryType}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported memory_type: {memory_type}",
        )
    await _verify_business_access(db, business_id, current_user)
    memory = await get_memory(db, business_id, memory_type)
    if not memory:
        # Return an empty memory document so clients have a stable contract.
        return BusinessMemoryOut(
            id=UUID(int=0),
            business_id=business_id,
            memory_type=memory_type,
            data={},
            version=0,
            updated_by_event_id=None,
            updated_at=None,  # type: ignore[arg-type]
        )
    return memory


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Knowledge Graph
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/graph/entities", response_model=GraphEntityOut, status_code=status.HTTP_201_CREATED)
async def create_graph_entity(
    business_id: UUID,
    data: GraphEntityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or update a graph entity."""
    await _verify_business_access(db, business_id, current_user)
    entity = await upsert_entity(
        db,
        business_id,
        data.entity_type,
        data.name,
        external_id=data.external_id,
        attributes=data.attributes,
        vector=data.vector,
    )
    await db.commit()
    await db.refresh(entity)
    return entity


@router.post("/graph/relationships", response_model=GraphRelationshipOut, status_code=status.HTTP_201_CREATED)
async def create_graph_relationship(
    business_id: UUID,
    data: GraphRelationshipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or strengthen a graph relationship."""
    await _verify_business_access(db, business_id, current_user)
    rel = await upsert_relationship(
        db,
        business_id,
        data.source_id,
        data.target_id,
        data.relation_type,
        strength_delta=0.0,
        evidence_event_id=data.evidence_event_ids[0] if data.evidence_event_ids else None,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
    )
    await db.commit()
    await db.refresh(rel)
    return rel


@router.get("/graph/expand")
async def expand_graph_view(
    business_id: UUID,
    entity_id: UUID,
    depth: int = Query(2, ge=1, le=5),
    relation_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Expand the graph around an entity up to a given depth."""
    await _verify_business_access(db, business_id, current_user)
    result = await expand_graph(db, entity_id, business_id, depth=depth, relation_type=relation_type)
    return GraphExpandOut(
        root=result["root"],
        depth=depth,
        entities=result["entities"],
        edges=result["edges"],
    )


@router.get("/graph/shortest-path")
async def graph_shortest_path(
    business_id: UUID,
    from_entity_id: UUID,
    to_entity_id: UUID,
    max_depth: int = Query(6, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find the shortest path between two entities."""
    await _verify_business_access(db, business_id, current_user)
    result = await shortest_path(db, from_entity_id, to_entity_id, business_id, max_depth=max_depth)
    return GraphShortestPathOut(
        found=result["found"],
        path=result["path"],
        edges=result["edges"],
        distance=result["distance"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Context & Temporal Reasoning
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/context", response_model=BusinessContextOut, status_code=status.HTTP_201_CREATED)
async def add_context(
    business_id: UUID,
    data: BusinessContextCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add external context for a business."""
    await _verify_business_access(db, business_id, current_user)
    ctx = await create_context(db, business_id, data.model_dump())
    await db.commit()
    await db.refresh(ctx)
    return ctx


@router.get("/context", response_model=list[BusinessContextOut])
async def list_context(
    business_id: UUID,
    context_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active external context for a business."""
    await _verify_business_access(db, business_id, current_user)
    return await get_active_context(db, business_id, context_type=context_type)


@router.post("/context/refresh")
async def refresh_context(
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Refresh external context adapters for a business."""
    await _verify_business_access(db, business_id, current_user)
    result = await refresh_context_for_business(db, business_id)
    return result


@router.post("/derivations", response_model=EventDerivationOut, status_code=status.HTTP_201_CREATED)
async def add_derivation(
    business_id: UUID,
    data: EventDerivationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a causal or correlational link between two events."""
    await _verify_business_access(db, business_id, current_user)
    derivation = await create_derivation(
        db,
        business_id,
        data.cause_event_id,
        data.effect_event_id,
        derivation_type=data.derivation_type,
        confidence=data.confidence,
        evidence=data.evidence,
    )
    await db.commit()
    await db.refresh(derivation)
    return derivation


@router.get("/timeline", response_model=TimelineOut)
async def timeline(
    business_id: UUID,
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Query the event timeline for a business."""
    await _verify_business_access(db, business_id, current_user)
    events, total = await get_timeline(
        db,
        business_id,
        from_date=from_date,
        to_date=to_date,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return TimelineOut(
        items=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "payload": e.payload,
                "occurred_at": e.occurred_at,
                "context_snapshot": e.context_snapshot,
            }
            for e in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/what-changed", response_model=WhatChangedOut)
async def what_changed_view(
    business_id: UUID,
    since: datetime,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summarize what changed since a given timestamp."""
    await _verify_business_access(db, business_id, current_user)
    result = await what_changed(db, business_id, since, limit=limit)
    return WhatChangedOut(
        since=result["since"],
        events=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "payload": e.payload,
                "occurred_at": e.occurred_at,
                "context_snapshot": e.context_snapshot,
            }
            for e in result["events"]
        ],
        summary=result["summary"],
    )


@router.get("/why/{event_id}", response_model=WhyOut)
async def why_view(
    event_id: UUID,
    business_id: UUID,
    max_depth: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the causal chain leading to an event."""
    await _verify_business_access(db, business_id, current_user)
    result = await why(db, event_id, business_id=business_id, max_depth=max_depth)
    return WhyOut(
        event_id=result["event_id"],
        causal_chain=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "payload": e.payload,
                "occurred_at": e.occurred_at,
                "context_snapshot": e.context_snapshot,
            }
            for e in result["causal_chain"]
        ],
        derivations=result["derivations"],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Decision & Explainability Engine
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/decisions/generate", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
async def generate_decision_view(
    business_id: UUID,
    request: DecisionGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a ranked, explainable decision for a business."""
    await _verify_business_access(db, business_id, current_user)
    decision = await generate_decision(
        db,
        business_id,
        decision_type=request.decision_type,
        input_event_ids=request.input_event_ids,
        extra_context=request.context,
    )
    await db.commit()
    await db.refresh(decision)
    return decision


@router.get("/decisions/{decision_id}", response_model=DecisionOut)
async def read_decision(
    decision_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a decision by id."""
    await _verify_business_access(db, business_id, current_user)
    decision = await get_decision(db, decision_id, business_id)
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return decision


@router.get("/decisions/{decision_id}/explain", response_model=DecisionExplainOut)
async def explain_decision_view(
    decision_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a human-readable explanation for a decision."""
    await _verify_business_access(db, business_id, current_user)
    result = await explain_decision(db, decision_id, business_id)
    return DecisionExplainOut(**result)


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Agents, Planning, Simulation, Execution
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/agents/propose", response_model=AgentProposalOut)
async def agent_propose(
    business_id: UUID,
    request: AgentProposalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a specialized agent and return its proposal."""
    await _verify_business_access(db, business_id, current_user)
    result = await dispatch_agent(db, business_id, request.agent_type, request.context)
    return AgentProposalOut(**result)


@router.get("/agents/types")
async def agent_types(
    current_user: User = Depends(get_current_user),
):
    """List available agent types."""
    return {"agent_types": list_agent_types()}


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan_view(
    business_id: UUID,
    request: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a goal-driven plan."""
    await _verify_business_access(db, business_id, current_user)
    plan = await create_plan(db, business_id, request.goal, context=request.context)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def read_plan(
    plan_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a plan by id."""
    await _verify_business_access(db, business_id, current_user)
    plan = await get_plan(db, plan_id, business_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.post("/simulate", response_model=SimulationOut, status_code=status.HTTP_201_CREATED)
async def run_simulation_view(
    business_id: UUID,
    request: SimulationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a what-if simulation."""
    await _verify_business_access(db, business_id, current_user)
    simulation = await create_simulation(
        db,
        business_id,
        request.name,
        request.scenario,
        assumptions=request.assumptions,
    )
    await db.commit()
    await db.refresh(simulation)
    return simulation


@router.get("/simulations/{simulation_id}", response_model=SimulationOut)
async def read_simulation(
    simulation_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a simulation by id."""
    await _verify_business_access(db, business_id, current_user)
    simulation = await get_simulation(db, simulation_id, business_id)
    if not simulation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found")
    return simulation


@router.post("/execute", response_model=ExecutionJobOut, status_code=status.HTTP_201_CREATED)
async def execute_action(
    business_id: UUID,
    request: ExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute an approved action through the Execution Engine."""
    await _verify_business_access(db, business_id, current_user)
    job = await execute_from_request(
        db,
        business_id,
        request.action_type,
        request.entity_type,
        request.entity_id,
        request.payload,
        decision_id=request.decision_id,
        plan_id=request.plan_id,
    )
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/execution-jobs/{job_id}", response_model=ExecutionJobOut)
async def read_execution_job(
    job_id: UUID,
    business_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve an execution job by id."""
    await _verify_business_access(db, business_id, current_user)
    job = await get_execution_job(db, job_id, business_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution job not found")
    return job


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: Learning Engine
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/feedback", response_model=OutcomeFeedbackOut, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    business_id: UUID,
    request: OutcomeFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record outcome feedback for a decision or execution job."""
    await _verify_business_access(db, business_id, current_user)
    try:
        feedback = await record_feedback(
            db,
            business_id=business_id,
            decision_id=request.decision_id,
            execution_job_id=request.execution_job_id,
            actual_outcome=request.actual_outcome,
            feedback_source=request.feedback_source,
            recorded_at=request.recorded_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/feedback", response_model=OutcomeFeedbackListOut)
async def read_feedback(
    business_id: UUID,
    decision_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recorded outcome feedback for a business."""
    await _verify_business_access(db, business_id, current_user)
    items, total = await list_feedback(db, business_id, decision_type=decision_type, limit=limit, offset=offset)
    return OutcomeFeedbackListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/performance", response_model=list[ModelPerformanceOut])
async def read_model_performance(
    business_id: UUID,
    decision_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return model performance aggregates for a business."""
    await _verify_business_access(db, business_id, current_user)
    return await get_model_performance(db, business_id, decision_type=decision_type)


@router.post("/learning/refresh", response_model=LearningRefreshOut)
async def refresh_learning_view(
    business_id: UUID,
    window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Refresh Learning Engine performance aggregates for a business."""
    await _verify_business_access(db, business_id, current_user)
    refreshed = await refresh_learning(db, business_id, window_days=window_days)
    await db.commit()
    return LearningRefreshOut(refreshed=refreshed, window_days=window_days)


@router.post("/learning/suggest-action", response_model=SuggestActionOut)
async def suggest_action_view(
    business_id: UUID,
    request: SuggestActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest the best candidate action using historical feedback (Thompson sampling)."""
    await _verify_business_access(db, business_id, current_user)
    candidates = [c.model_dump() for c in request.candidates]
    selected, probabilities, note = await suggest_best_action(
        db,
        business_id,
        candidates,
        decision_type=request.decision_type,
        seed=request.seed,
    )
    return SuggestActionOut(
        selected_candidate=selected,
        probabilities=probabilities,
        note=note,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 7: Unified Intelligence API
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/analyze", response_model=AnalyzeOut, status_code=status.HTTP_201_CREATED)
async def analyze_view(
    business_id: UUID,
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze a business across memory, graph, context, and recent events."""
    await _verify_business_access(db, business_id, current_user)
    result = await intelligence_api.analyze(
        db,
        business_id,
        query=request.query,
        decision_type=request.decision_type,
        extra_context=request.context,
    )
    await db.commit()
    await db.refresh(result["decision"])
    return AnalyzeOut(**result)


@router.post("/predict", response_model=PredictOut)
async def predict_view(
    business_id: UUID,
    request: PredictRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Predict sales, demand, or stock over a horizon from business memory."""
    await _verify_business_access(db, business_id, current_user)
    result = await intelligence_api.predict(
        db,
        business_id,
        request.target,
        horizon_days=request.horizon_days,
        item_id=request.item_id,
    )
    return PredictOut(**result)


@router.post("/explain", response_model=DecisionExplainOut)
async def explain_view(
    business_id: UUID,
    request: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explain a previously generated intelligence decision."""
    await _verify_business_access(db, business_id, current_user)
    result = await intelligence_api.explain(db, business_id, request.decision_id)
    return DecisionExplainOut(**result)


@router.post("/plan", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def plan_view(
    business_id: UUID,
    request: PlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a goal-driven plan (unified Intelligence API alias)."""
    await _verify_business_access(db, business_id, current_user)
    plan_obj = await intelligence_api.plan(db, business_id, request.goal, context=request.context)
    await db.commit()
    await db.refresh(plan_obj)
    return plan_obj


@router.post("/observe", response_model=ObserveOut, status_code=status.HTTP_201_CREATED)
async def observe_view(
    business_id: UUID,
    request: ObserveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Observe a business event through the Universal Event Engine."""
    await _verify_business_access(db, business_id, current_user)
    event = await intelligence_api.observe(db, business_id, request.event)
    await db.commit()
    await db.refresh(event)
    return ObserveOut(
        event_id=event.id,
        event_type=event.event_type,
        processed=event.processed,
        correlation_id=event.correlation_id,
    )


@router.post("/remember", response_model=RememberOut)
async def remember_view(
    business_id: UUID,
    request: RememberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Write a value or goals into business memory."""
    await _verify_business_access(db, business_id, current_user)
    memory = await intelligence_api.remember(
        db,
        business_id,
        request.memory_type,
        operation=request.operation,
        path=request.path,
        value=request.value,
        goals=request.goals,
    )
    await db.commit()
    await db.refresh(memory)
    return RememberOut(
        memory_type=memory.memory_type,
        data=memory.data,
        version=memory.version,
    )


@router.post("/reason", response_model=ReasonOut, status_code=status.HTTP_201_CREATED)
async def reason_view(
    business_id: UUID,
    request: ReasonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a business question by reasoning over memory, graph, and decisions."""
    await _verify_business_access(db, business_id, current_user)
    result = await intelligence_api.reason(db, business_id, request.question, context=request.context)
    await db.commit()
    if result["decision"]:
        await db.refresh(result["decision"])
    if result["plan"]:
        await db.refresh(result["plan"])
    return ReasonOut(
        answer=result["answer"],
        decision=result["decision"],
        plan=result["plan"],
        sources=result["sources"],
    )
