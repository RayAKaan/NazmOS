"""Internal client for the Unified Intelligence API (Phase 7).

This client lets existing NazmOS application routers consume the Intelligence
API directly (same process, no HTTP overhead) while using the same consolidated
surface as the public `/api/v1/intelligence/*` endpoints.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.events import EventIngest
from app.services import intelligence_api


class IntelligenceAPIClient:
    """Thin wrapper around the unified Intelligence API service."""

    def __init__(self, session: AsyncSession, business_id: UUID | str):
        self.session = session
        self.business_id = business_id

    async def analyze(
        self,
        query: str | None = None,
        decision_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await intelligence_api.analyze(
            self.session, self.business_id, query=query, decision_type=decision_type, extra_context=context
        )

    async def predict(
        self,
        target: str,
        horizon_days: int = 7,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        return await intelligence_api.predict(
            self.session, self.business_id, target, horizon_days=horizon_days, item_id=item_id
        )

    async def explain(self, decision_id: UUID | str) -> dict[str, Any]:
        return await intelligence_api.explain(self.session, self.business_id, decision_id)

    async def plan(self, goal: str, context: dict[str, Any] | None = None) -> Any:
        return await intelligence_api.plan(self.session, self.business_id, goal, context=context)

    async def simulate(
        self,
        name: str,
        scenario: dict[str, Any],
        assumptions: dict[str, Any] | None = None,
    ) -> Any:
        return await intelligence_api.simulate(
            self.session, self.business_id, name, scenario, assumptions=assumptions
        )

    async def execute(
        self,
        action_type: str,
        entity_type: str,
        entity_id: UUID | str,
        payload: dict[str, Any],
        decision_id: UUID | str | None = None,
        plan_id: UUID | str | None = None,
    ) -> Any:
        return await intelligence_api.execute(
            self.session,
            self.business_id,
            action_type,
            entity_type,
            entity_id,
            payload,
            decision_id=decision_id,
            plan_id=plan_id,
        )

    async def observe(self, event: EventIngest) -> Any:
        return await intelligence_api.observe(self.session, self.business_id, event)

    async def remember(
        self,
        memory_type: str,
        operation: str = "set",
        path: str | None = None,
        value: Any = None,
        goals: dict[str, Any] | None = None,
    ) -> Any:
        return await intelligence_api.remember(
            self.session,
            self.business_id,
            memory_type,
            operation=operation,
            path=path,
            value=value,
            goals=goals,
        )

    async def reason(self, question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return await intelligence_api.reason(self.session, self.business_id, question, context=context)
