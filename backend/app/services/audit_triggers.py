"""Continuous auditing foundation (Phase 1, brief §11).

Maps business events (already ingested by the existing event engine) to the audit
domains / agents that should re-evaluate. This is a declarative mapping — no new
event infrastructure, and no background machinery added yet (scheduling stays a
Phase-2 concern). The mapping is the seam the orchestrator/cron will later call.

    sale.completed        → money_audit, recovery (recovery agent trigger)
    inventory.changed     → inventory, recovery
    supplier.delivered    → inventory, recovery
    price.updated         → money_audit (margin leakage)
    payment.failed        → money_audit (cash)
    temperature.alert     → compliance (expiry/recall adjacent)
    pos.order.received    → money_audit
    day_ended (future)    → all domains
"""
from __future__ import annotations

from typing import Any

# event type → audit domains to re-run
EVENT_AUDIT_DOMAINS: dict[str, list[str]] = {
    "sale.completed": ["money_audit"],
    "inventory.changed": ["inventory"],
    "supplier.delivered": ["inventory", "recovery_match"],
    "price.updated": ["money_audit"],
    "payment.failed": ["money_audit"],
    "temperature.alert": ["compliance"],
    "pos.order.received": ["money_audit"],
    "day.ended": ["money_audit", "inventory", "recovery_match", "compliance"],
}

# event type → agent types to wake (for the Agent Runtime)
EVENT_AGENT_TYPES: dict[str, list[str]] = {
    "sale.completed": ["recovery", "inventory"],
    "inventory.changed": ["inventory", "recovery"],
    "supplier.delivered": ["supplier", "inventory"],
    "price.updated": ["pricing"],
    "payment.failed": ["finance"],
    "temperature.alert": ["compliance"],
}


def audit_domains_for_event(event_type: str) -> list[str]:
    """Audit domains that should re-run for a given event type."""
    return EVENT_AUDIT_DOMAINS.get(event_type, [])


def agents_for_event(event_type: str) -> list[str]:
    """Agent types to wake for a given event type."""
    return EVENT_AGENT_TYPES.get(event_type, [])


async def run_event_triggered_audits(
    db,
    business_id,
    event_type: str,
    commit: bool = True,
) -> dict[str, Any]:
    """Run all audit domains mapped to an event, returning a summary (brief §11)."""
    from app.services.audit_engine import run_audit

    domains = audit_domains_for_event(event_type)
    results = []
    for domain in domains:
        try:
            results.append(await run_audit(db, business_id, domain, trigger="event", trigger_event_type=event_type, commit=False))
        except Exception as exc:  # one domain failing must not block the rest
            results.append({"domain": domain, "status": "failed", "error": str(exc)[:500]})
    if commit:
        await db.commit()
    return {"event_type": event_type, "audits": results, "agents": agents_for_event(event_type)}
