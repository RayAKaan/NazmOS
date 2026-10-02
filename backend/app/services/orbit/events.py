"""Canonical business events (spec §37).

Events are **observations**, not conclusions. An event records that a source
asserted something at a location and time, with the evidence that backs it.

What an event deliberately does not contain: recommendations, diagnoses,
projections or health scores. Those belong to later phases, derived from state.
Mixing them in here is how an observation becomes indistinguishable from a
conclusion that nobody can trace.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    BusinessEventType,
    DomainCapability,
    FieldStatus,
    SourceType,
)

#: Which domain each event type contributes to.
DOMAIN_FOR_EVENT: dict[BusinessEventType, DomainCapability] = {
    BusinessEventType.SALE: DomainCapability.SALES,
    BusinessEventType.REFUND: DomainCapability.SALES,
    BusinessEventType.RETURN: DomainCapability.SALES,
    BusinessEventType.INVOICE: DomainCapability.SALES,
    BusinessEventType.PURCHASE: DomainCapability.PROCUREMENT,
    BusinessEventType.PURCHASE_ORDER: DomainCapability.PROCUREMENT,
    BusinessEventType.STOCK_RECEIPT: DomainCapability.PROCUREMENT,
    BusinessEventType.EXPENSE: DomainCapability.FINANCE,
    BusinessEventType.PAYMENT: DomainCapability.FINANCE,
    BusinessEventType.STOCK_OBSERVATION: DomainCapability.INVENTORY,
    BusinessEventType.STOCK_ADJUSTMENT: DomainCapability.INVENTORY,
    BusinessEventType.STOCK_TRANSFER: DomainCapability.INVENTORY,
    BusinessEventType.STOCKOUT: DomainCapability.INVENTORY,
    BusinessEventType.PRICE_CHANGE: DomainCapability.INVENTORY,
    BusinessEventType.SHIFT: DomainCapability.WORKFORCE,
    BusinessEventType.ATTENDANCE: DomainCapability.WORKFORCE,
    BusinessEventType.CAMPAIGN: DomainCapability.MARKETING,
    BusinessEventType.DISCOUNT: DomainCapability.SALES,
}


def domain_of_event(event: BusinessEvent) -> Optional[DomainCapability]:
    return DOMAIN_FOR_EVENT.get(event.event_type)


def build_events(raw: Sequence[BusinessEvent]) -> tuple[BusinessEvent, ...]:
    """Deduplicate and order events deterministically.

    Ordering matters: downstream inventory arithmetic depends on a stable
    sequence, and reprocessing the same input must produce the same order.
    """
    unique: dict[str, BusinessEvent] = {}
    for event in raw:
        # row_hash is content-derived, so identical observations collapse.
        unique.setdefault(event.row_hash, event)
    return tuple(
        sorted(
            unique.values(),
            key=lambda e: (
                e.business_local_date or date(1970, 1, 1),
                e.event_type.value,
                e.event_id,
            ),
        )
    )


def events_by_domain(events: Iterable[BusinessEvent]) -> dict[str, list[BusinessEvent]]:
    grouped: dict[str, list[BusinessEvent]] = defaultdict(list)
    for event in events:
        domain = domain_of_event(event)
        grouped[domain.value if domain else "unknown"].append(event)
    return dict(grouped)


def events_by_entity(events: Iterable[BusinessEvent]) -> dict[str, list[BusinessEvent]]:
    grouped: dict[str, list[BusinessEvent]] = defaultdict(list)
    for event in events:
        for kind, entity_id in event.entity_refs.items():
            grouped[f"{kind}:{entity_id}"].append(event)
    return dict(grouped)


def coverage_window(events: Sequence[BusinessEvent]) -> tuple[Optional[date], Optional[date]]:
    """The observed date range, used for freshness and period reporting."""
    dates = [e.business_local_date for e in events if e.business_local_date is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)


def events_missing_dates(events: Sequence[BusinessEvent]) -> tuple[BusinessEvent, ...]:
    """Events with no usable date.

    Surfaced rather than dropped: an undated event cannot enter any period
    calculation, and hiding it would make the period look complete.
    """
    return tuple(e for e in events if e.business_local_date is None)


def known_quantities(events: Iterable[BusinessEvent]) -> int:
    return sum(1 for e in events if e.quantity.value is not None)


def known_amounts(events: Iterable[BusinessEvent]) -> int:
    return sum(1 for e in events if e.amount.value is not None)


def sum_known_amounts(events: Iterable[BusinessEvent]) -> Optional[Decimal]:
    """Sum event amounts that are genuinely known.

    Returns ``None`` when no amount is known. A total of zero across unknown
    amounts is a different statement from "zero revenue", and only the first is
    supported by the evidence.
    """
    values = [e.amount.value for e in events if e.amount.value is not None]
    if not values:
        return None
    return sum(values, Decimal(0))


def event_summary(events: Sequence[BusinessEvent]) -> dict[str, Any]:
    """Counts and coverage, with no derived opinions."""
    start, end = coverage_window(events)
    return {
        "total": len(events),
        "by_type": {
            kind.value: sum(1 for e in events if e.event_type is kind)
            for kind in sorted({e.event_type for e in events}, key=lambda k: k.value)
        },
        "by_domain": {k: len(v) for k, v in sorted(events_by_domain(events).items())},
        "with_dates": sum(1 for e in events if e.business_local_date is not None),
        "without_dates": len(events_missing_dates(events)),
        "with_amounts": known_amounts(events),
        "with_quantities": known_quantities(events),
        "period_start": start.isoformat() if start else None,
        "period_end": end.isoformat() if end else None,
        "evidence_count": len({eid for e in events for eid in e.evidence_ids}),
    }