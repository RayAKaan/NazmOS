from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
from enum import Enum
import uuid
import json


class ActionType(str, Enum):
    RESTOCK = "RESTOCK"
    REDUCE_ORDER = "REDUCE_ORDER"
    DISCOUNT = "DISCOUNT"
    PROMOTE = "PROMOTE"
    REMOVE = "REMOVE"
    INVESTIGATE = "INVESTIGATE"
    STAFF_UP = "STAFF_UP"
    PRICE_INCREASE = "PRICE_INCREASE"


@dataclass
class Decision:
    action: ActionType
    item_name: str
    reason: str
    confidence: float
    priority: int
    item_id: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = "units"
    by_when: Optional[date] = None
    estimated_value: Optional[float] = None
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "action": self.action.value,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "by_when": self.by_when.isoformat() if self.by_when else "ASAP",
            "reason": self.reason,
            "estimated_value": self.estimated_value,
            "confidence": self.confidence,
            "priority": self.priority,
            "metadata": self.metadata or {},
        }


class DecisionEngine:

    def normalize_decisions(self, raw_decisions: list[dict]) -> list[dict]:
        """Normalize raw action dicts for legacy callers/tests."""
        normalized = []
        for raw in raw_decisions or []:
            action_type = str(raw.get("type") or raw.get("action") or "investigate").lower()
            normalized.append({
                "type": action_type,
                "title": raw.get("title") or action_type.replace("_", " " ).title(),
                "items": raw.get("items", []),
                "priority": raw.get("priority") or self.assign_priority(action_type, raw),
                "confidence": raw.get("confidence", 0.5),
            })
        return normalized

    def assign_priority(self, action_type: str, context: dict) -> str:
        stock = float(context.get("current_stock", 999) or 0)
        days_left = float(context.get("days_left", 999) or 999)
        if action_type in {"restock", "reorder"} and (stock <= 0 or days_left < 2):
            return "high"
        if action_type in {"discount", "margin_fix", "recovery_match"}:
            return "medium"
        return "low"

    def calculate_confidence(self, decision: dict, context: dict) -> float:
        confidence = 0.5
        if decision.get("items"):
            confidence += 0.2
        if context.get("historical_accuracy") is not None:
            confidence = (confidence + float(context.get("historical_accuracy"))) / 2
        return max(0.0, min(1.0, confidence))

    def generate_from_inventory(self, inventory_items: list) -> List[Decision]:
        decisions = []
        today = date.today()

        for item in inventory_items:
            stock = item.get("current_stock", 0)
            daily_avg = item.get("daily_avg_sale", 0)
            days_left = stock / daily_avg if daily_avg > 0.1 else 999
            reorder_level = item.get("reorder_level", 10)
            cost_price = item.get("cost_price", 0)
            sell_price = item.get("sell_price", 0)
            stock_value = stock * cost_price
            trend = item.get("trend_7d", "stable")

            if days_left < 2:
                reorder_qty = max(daily_avg * 7, reorder_level * 2)
                decisions.append(Decision(
                    action=ActionType.RESTOCK,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=round(reorder_qty),
                    unit=item.get("unit", "units"),
                    by_when=today,
                    reason=f"Only {days_left:.1f} days of stock remaining. Will stock out today or tomorrow.",
                    estimated_value=round(reorder_qty * cost_price),
                    confidence=0.95,
                    priority=1,
                ))

            elif days_left < 5:
                reorder_qty = max(daily_avg * 10, reorder_level)
                decisions.append(Decision(
                    action=ActionType.RESTOCK,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=round(reorder_qty),
                    unit=item.get("unit", "units"),
                    by_when=today + timedelta(days=2),
                    reason=f"{days_left:.1f} days of stock remaining.",
                    estimated_value=round(reorder_qty * cost_price),
                    confidence=0.90,
                    priority=2,
                ))

            elif days_left > 25 and daily_avg < 0.1:
                decisions.append(Decision(
                    action=ActionType.DISCOUNT,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    quantity=stock,
                    reason=f"No meaningful sales. ﷼ {stock_value:,.0f} tied up. Discount to recover capital.",
                    estimated_value=stock_value,
                    confidence=0.85,
                    priority=3,
                ))

            elif days_left > 20 and trend == "down":
                decisions.append(Decision(
                    action=ActionType.REDUCE_ORDER,
                    item_id=item.get("item_id"),
                    item_name=item.get("name", "Unknown Item"),
                    reason=f"{days_left:.0f} days of stock with declining sales trend. Reduce next order.",
                    confidence=0.75,
                    priority=4,
                ))

        decisions.sort(key=lambda d: (d.priority, -d.confidence))
        return decisions

    def parse_llm_decisions(self, raw_json: list) -> List[Decision]:
        decisions = []
        for raw in raw_json:
            try:
                action = ActionType(raw["action"])
                decisions.append(Decision(
                    action=action,
                    item_id=raw.get("item_id"),
                    item_name=raw["item_name"],
                    quantity=raw.get("quantity"),
                    unit=raw.get("unit", "units"),
                    by_when=date.fromisoformat(raw["by_when"]) if raw.get("by_when") and raw["by_when"] != "ASAP" else None,
                    reason=raw.get("reason", ""),
                    estimated_value=raw.get("estimated_value"),
                    confidence=float(raw.get("confidence", 0.5)),
                    priority=int(raw.get("priority", 3)),
                ))
            except (KeyError, ValueError):
                continue
        return decisions


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Intelligence Decision & Explainability Engine
# ═══════════════════════════════════════════════════════════════════════════

"""Additional Phase 4 functions for ranked, auditable decisions stored in the
IntelligenceDecision table. These coexist with the legacy DecisionEngine class
above.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    BusinessMemory,
    Event,
    GraphEntity,
    GraphRelationship,
    IntelligenceDecision,
    MemoryType,
)
from app.services.context_engine import get_active_context
from app.utils.logger import setup_logger

logger = setup_logger("decision_engine_phase4")


def _to_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _load_memory(session: AsyncSession, business_id: UUID) -> dict[str, Any]:
    result = await session.execute(
        select(BusinessMemory).where(BusinessMemory.business_id == business_id)
    )
    return {m.memory_type: m.data for m in result.scalars().all()}


async def _load_recent_events(
    session: AsyncSession,
    business_id: UUID,
    hours: int = 24,
) -> list[Event]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        select(Event)
        .where(Event.business_id == business_id, Event.occurred_at >= since)
        .order_by(Event.occurred_at.desc())
        .limit(1000)
    )
    return list(result.scalars().all())


async def _load_graph_signals(
    session: AsyncSession,
    business_id: UUID,
) -> dict[str, Any]:
    result = await session.execute(
        select(GraphRelationship)
        .where(GraphRelationship.business_id == business_id)
        .order_by(GraphRelationship.strength.desc())
        .limit(50)
    )
    rels = result.scalars().all()

    entity_ids = {str(r.source_id) for r in rels} | {str(r.target_id) for r in rels}
    entity_map: dict[str, str] = {}
    if entity_ids:
        entities = await session.execute(
            select(GraphEntity).where(GraphEntity.id.in_(entity_ids))
        )
        entity_map = {str(e.id): f"{e.entity_type}:{e.name}" for e in entities.scalars().all()}

    return {
        "top_relationships": [
            {
                "source": entity_map.get(str(r.source_id), str(r.source_id)),
                "target": entity_map.get(str(r.target_id), str(r.target_id)),
                "relation_type": r.relation_type,
                "strength": float(r.strength) if r.strength else 0.0,
            }
            for r in rels
        ]
    }


async def _load_context_signals(
    session: AsyncSession,
    business_id: UUID,
) -> dict[str, Any]:
    contexts = await get_active_context(session, business_id)
    return {ctx.context_type: ctx.payload for ctx in contexts}


def _generate_restock_candidates(memory: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    inventory = memory.get(MemoryType.CURRENT_STATE.value, {}).get("inventory", {})
    for item_key, item_state in inventory.items():
        stock = _safe_float(item_state.get("stock"))
        reorder_flag = item_state.get("reorder_flag")
        if reorder_flag or stock < 10:
            candidates.append({
                "action_type": "restock",
                "title": f"Restock {item_key}",
                "payload": {"item_key": item_key, "current_stock": stock, "suggested_qty": max(50, int(20 - stock) * 5)},
                "expected_roi": max(0, (20 - stock) * 10),
                "risk_score": 0.2,
                "confidence": 0.85,
                "urgency": 0.9 if stock < 5 else 0.6,
                "reasons": [f"Stock level {stock} is below reorder threshold"],
            })
    return candidates


def _generate_pricing_candidates(memory: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    patterns = memory.get(MemoryType.PATTERNS.value, {})
    pricing = patterns.get("pricing", {})
    for item_key, history_data in pricing.items():
        history = history_data.get("history", [])
        if len(history) >= 2:
            latest = history[-1]
            previous = history[-2]
            latest_price = _safe_float(latest.get("price"))
            previous_price = _safe_float(previous.get("price"))
            if latest_price > previous_price * 1.05:
                candidates.append({
                    "action_type": "pricing_decrease",
                    "title": f"Consider decreasing price of {item_key}",
                    "payload": {"item_key": item_key, "current_price": latest_price, "previous_price": previous_price},
                    "expected_roi": -5.0,
                    "risk_score": 0.4,
                    "confidence": 0.6,
                    "urgency": 0.5,
                    "reasons": ["Recent price increase may reduce demand"],
                })
            elif latest_price < previous_price * 0.95:
                candidates.append({
                    "action_type": "pricing_increase",
                    "title": f"Consider increasing price of {item_key}",
                    "payload": {"item_key": item_key, "current_price": latest_price, "previous_price": previous_price},
                    "expected_roi": 10.0,
                    "risk_score": 0.3,
                    "confidence": 0.6,
                    "urgency": 0.4,
                    "reasons": ["Recent price decrease leaves margin on the table"],
                })

    top_products = patterns.get("top_products", {})
    for item_key, data in top_products.items():
        qty = _safe_float(data.get("quantity_30d"))
        if qty > 50:
            candidates.append({
                "action_type": "pricing_increase",
                "title": f"High-demand product {item_key}",
                "payload": {"item_key": item_key, "quantity_30d": qty},
                "expected_roi": qty * 2,
                "risk_score": 0.25,
                "confidence": 0.7,
                "urgency": 0.5,
                "reasons": ["High sales velocity in the last 30 days"],
            })
    return candidates


def _generate_discount_candidates(memory: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    patterns = memory.get(MemoryType.PATTERNS.value, {})
    pricing = patterns.get("pricing", {})
    for item_key, history_data in pricing.items():
        history = history_data.get("history", [])
        if len(history) >= 5:
            decreases = sum(
                1 for i in range(1, len(history))
                if _safe_float(history[i].get("price")) < _safe_float(history[i - 1].get("price"))
            )
            if decreases >= 3:
                candidates.append({
                    "action_type": "discount",
                    "title": f"Discount slow-moving {item_key}",
                    "payload": {"item_key": item_key, "recommended_discount_pct": 15},
                    "expected_roi": 20.0,
                    "risk_score": 0.3,
                    "confidence": 0.65,
                    "urgency": 0.5,
                    "reasons": ["Repeated price decreases suggest weak demand"],
                })
    return candidates


def _generate_supplier_switch_candidates(
    memory: dict[str, Any],
    graph: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    relationships = graph.get("top_relationships", [])
    for rel in relationships:
        if rel["relation_type"] == "SUPPLIES" and rel["strength"] < 0.4:
            candidates.append({
                "action_type": "supplier_switch",
                "title": f"Review supplier for {rel['target']}",
                "payload": {"supplier": rel["source"], "product": rel["target"], "strength": rel["strength"]},
                "expected_roi": 50.0,
                "risk_score": 0.35,
                "confidence": 0.6,
                "urgency": 0.45,
                "reasons": ["Supplier relationship strength is low"],
            })
    return candidates


def _score_candidate(
    candidate: dict[str, Any],
    memory: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    roi = _safe_float(candidate.get("expected_roi"), 0.0)
    risk = max(0.0, min(1.0, _safe_float(candidate.get("risk_score"), 0.5)))
    confidence = max(0.0, min(1.0, _safe_float(candidate.get("confidence"), 0.5)))
    urgency = max(0.0, min(1.0, _safe_float(candidate.get("urgency"), 0.5)))

    holidays = context.get("holiday", {}).get("holidays", [])
    if holidays:
        urgency = min(1.0, urgency + 0.05)
        confidence = min(1.0, confidence + 0.02)

    inflation_records = context.get("inflation", {}).get("records", [])
    if inflation_records:
        latest_inflation = _safe_float(inflation_records[0].get("value"), 1.9)
        if latest_inflation > 3.0:
            risk = min(1.0, risk + 0.1)

    normalized_roi = max(-100.0, min(100.0, roi)) / 100.0
    composite = (
        0.35 * normalized_roi +
        0.25 * confidence +
        0.25 * urgency -
        0.15 * risk
    )

    scored = deepcopy(candidate)
    scored["score"] = round(composite, 4)
    scored["risk_score"] = round(risk, 3)
    scored["confidence"] = round(confidence, 3)
    scored["urgency"] = round(urgency, 3)
    scored["expected_roi"] = round(roi, 2)
    return scored


def _build_explanation(
    decision_type: str,
    ranked: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    memory: dict[str, Any],
    graph: dict[str, Any],
    context: dict[str, Any],
    events: list[Event],
) -> dict[str, Any]:
    alternatives = [c for c in candidates if c != ranked][:3]
    return {
        "summary": f"Generated {decision_type} decision from {len(events)} recent events, "
                   f"{len(memory)} memory documents, {len(graph.get('top_relationships', []))} graph relationships, "
                   f"and {len(context)} context types.",
        "primary_drivers": ranked.get("reasons", []) if ranked else [],
        "evidence": {
            "memory_types_used": list(memory.keys()),
            "context_types_used": list(context.keys()),
            "graph_relationship_count": len(graph.get("top_relationships", [])),
            "recent_event_count": len(events),
            "top_event_types": list({e.event_type for e in events})[:5],
        },
        "alternative_actions": alternatives,
    }


async def generate_decision(
    session: AsyncSession,
    business_id: UUID | str,
    decision_type: str | None = None,
    input_event_ids: list[UUID] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> IntelligenceDecision:
    """Generate a ranked, explainable decision for a business."""
    business_id = _to_uuid(business_id)
    input_event_ids = input_event_ids or []

    memory = await _load_memory(session, business_id)
    events = await _load_recent_events(session, business_id, hours=24)
    graph = await _load_graph_signals(session, business_id)
    context = await _load_context_signals(session, business_id)
    if extra_context:
        context.update(extra_context)

    if not decision_type:
        if memory.get(MemoryType.CURRENT_STATE.value, {}).get("inventory"):
            decision_type = "inventory_optimization"
        else:
            decision_type = "general"

    candidates: list[dict[str, Any]] = []
    candidates.extend(_generate_restock_candidates(memory))
    candidates.extend(_generate_pricing_candidates(memory))
    candidates.extend(_generate_discount_candidates(memory))
    candidates.extend(_generate_supplier_switch_candidates(memory, graph))

    if not candidates:
        candidates.append({
            "action_type": "info_only",
            "title": "No urgent actions detected",
            "payload": {},
            "expected_roi": 0.0,
            "risk_score": 0.0,
            "confidence": 0.9,
            "urgency": 0.0,
            "reasons": ["Business signals are within normal ranges"],
        })

    scored = [_score_candidate(c, memory, context) for c in candidates]
    scored.sort(key=lambda x: x["score"], reverse=True)
    ranked = scored[0]

    explanation = _build_explanation(
        decision_type,
        ranked,
        scored,
        memory,
        graph,
        context,
        events,
    )

    decision = IntelligenceDecision(
        business_id=business_id,
        decision_type=decision_type,
        input_event_ids=[str(e) for e in input_event_ids],
        rules_applied=[
            "restock_threshold",
            "price_trend",
            "demand_velocity",
            "supplier_strength",
            "context_adjustment",
        ],
        memory_snapshot=memory,
        graph_evidence=graph,
        context_evidence=context,
        candidate_actions=scored,
        ranked_action=ranked,
        confidence=ranked["confidence"],
        expected_roi=ranked.get("expected_roi"),
        risk_score=ranked["risk_score"],
        urgency=ranked["urgency"],
        status="draft",
        explanation=explanation,
    )
    session.add(decision)
    await session.flush()
    return decision


async def get_decision(
    session: AsyncSession,
    decision_id: UUID | str,
    business_id: UUID | str | None = None,
) -> IntelligenceDecision | None:
    query = select(IntelligenceDecision).where(IntelligenceDecision.id == _to_uuid(decision_id))
    if business_id is not None:
        query = query.where(IntelligenceDecision.business_id == _to_uuid(business_id))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def explain_decision(
    session: AsyncSession,
    decision_id: UUID | str,
    business_id: UUID | str,
) -> dict[str, Any]:
    """Return a human-readable explanation for a decision."""
    decision = await get_decision(session, decision_id, business_id)
    if not decision:
        return {
            "decision_id": decision_id,
            "decision_type": "unknown",
            "why": "Decision not found",
            "primary_drivers": [],
            "evidence": {},
            "confidence": 0.0,
            "expected_roi": None,
            "risk_score": 0.0,
            "urgency": 0.0,
            "alternative_actions": [],
            "ranked_action": None,
        }

    ranked = decision.ranked_action or {}
    alternatives = [c for c in (decision.candidate_actions or []) if c != ranked][:3]
    return {
        "decision_id": decision.id,
        "decision_type": decision.decision_type,
        "why": decision.explanation.get("summary", ""),
        "primary_drivers": decision.explanation.get("primary_drivers", []),
        "evidence": decision.explanation.get("evidence", {}),
        "confidence": float(decision.confidence) if decision.confidence else 0.0,
        "expected_roi": float(decision.expected_roi) if decision.expected_roi else None,
        "risk_score": float(decision.risk_score) if decision.risk_score else 0.0,
        "urgency": float(decision.urgency) if decision.urgency else 0.0,
        "alternative_actions": alternatives,
        "ranked_action": ranked,
    }
