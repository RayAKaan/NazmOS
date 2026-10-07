"""Business profile (spec §36).

The distinction this module exists to protect:

    **the business operates a domain**   ≠   **we have data for the domain**

Conflating them produces confident nonsense. A file called ``staff.csv`` does not
make the business a restaurant; it makes staff *data* available. Both facts are
recorded separately in :class:`DomainCapabilityFlag`, where
``observed_capability`` and ``data_available`` are distinct fields.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    BusinessProfile,
    BusinessType,
    DecisionOrigin,
    DomainCapability,
    DomainCapabilityFlag,
    Entity,
    EntityKind,
    _utcnow,
)
from app.services.orbit.events import domain_of_event
from app.services.orbit.semantics.vocabulary import PRIMARY_DOMAIN_BY_ARTIFACT_KIND

#: Minimum evidence before a business type is claimed. One filename is not a
#: business model.
MIN_BUSINESS_TYPE_EVIDENCE = 2

#: Entity kinds that imply an operating domain by their mere presence.
_ENTITY_DOMAIN_SIGNALS: dict[EntityKind, DomainCapability] = {
    EntityKind.PRODUCT: DomainCapability.SALES,
    EntityKind.SUPPLIER: DomainCapability.PROCUREMENT,
    EntityKind.EMPLOYEE: DomainCapability.WORKFORCE,
    EntityKind.BRANCH: DomainCapability.SALES,
    EntityKind.CHANNEL: DomainCapability.MARKETING,
    EntityKind.CUSTOMER: DomainCapability.CUSTOMER,
}


def infer_business_type(
    entities: Sequence[Entity],
    events: Sequence[BusinessEvent],
    *,
    source_count: int = 0,
) -> tuple[BusinessType, float, DecisionOrigin, tuple[str, ...]]:
    """Infer the business type, or decline.

    Returns ``UNKNOWN`` with zero confidence unless several independent signals
    agree. A guess here propagates into every downstream recommendation.
    """
    signals: Counter[BusinessType] = Counter()

    # Entity is not hashable (it carries an ``identifiers`` dict), so counting
    # uses lengths rather than sets.
    def count(kind: EntityKind) -> int:
        return sum(1 for e in entities if e.kind is kind)

    n_branches = count(EntityKind.BRANCH)
    n_staff = count(EntityKind.EMPLOYEE)
    n_products = count(EntityKind.PRODUCT)
    n_suppliers = count(EntityKind.SUPPLIER)

    if n_branches:
        signals[BusinessType.RETAIL] += 1
    if n_products and n_suppliers:
        signals[BusinessType.DISTRIBUTION] += 1
    if n_staff and not n_products:
        signals[BusinessType.SERVICES] += 1
    if n_products and not n_branches:
        signals[BusinessType.WHOLESALE] += 1

    observed = [t.value for t, n in signals.items() if n >= MIN_BUSINESS_TYPE_EVIDENCE]
    if not observed:
        return BusinessType.UNKNOWN, 0.0, DecisionOrigin.NONE, ()

    winner = signals.most_common(1)[0][0]
    total = sum(signals.values())
    confidence = min(0.8, signals[winner] / total) if total else 0.0
    return (
        winner,
        round(confidence, 4),
        DecisionOrigin.DETERMINISTIC,
        tuple(sorted(observed)),
    )


#: Currency is a property of the *source*, not of an event. It is passed in by the
#: pipeline (which saw the currency marks) rather than derived from events, because
#: a canonical event deliberately carries only a numeric amount and its evidence.


def build_business_profile(
    entities: Iterable[Entity],
    events: Iterable[BusinessEvent],
    classification: Optional[Any] = None,
    *,
    currencies: Sequence[str] = (),
) -> BusinessProfile:
    """Build the profile from observed evidence only."""
    entities = list(entities)
    events = list(events)

    by_kind: dict[EntityKind, list[Entity]] = {}
    for entity in entities:
        by_kind.setdefault(entity.kind, []).append(entity)

    # Domains the business *operates*, from entities present in the data.
    observed_domains: Counter[DomainCapability] = Counter()
    for kind, group in by_kind.items():
        domain = _ENTITY_DOMAIN_SIGNALS.get(kind)
        if domain and group:
            observed_domains[domain] += len(group)

    # Domains we actually have events for.
    event_domains: Counter[DomainCapability] = Counter()
    for event in events:
        domain = domain_of_event(event)
        if domain:
            event_domains[domain] += 1

    # The artifact kind is evidence of data availability, not of operations.
    artifact_domain = None
    if classification is not None:
        artifact_domain = getattr(classification, "domain", None)

    capabilities: list[DomainCapabilityFlag] = []
    limitations: list[str] = []
    for domain in DomainCapability:
        observed = observed_domains.get(domain, 0) > 0 or event_domains.get(domain, 0) > 0
        evidence_count = event_domains.get(domain, 0)
        artifact_count = 1 if artifact_domain is domain else 0
        data_available = evidence_count > 0

        if domain not in observed_domains and evidence_count == 0:
            reason_gap = True
        else:
            reason_gap = False

        capabilities.append(
            DomainCapabilityFlag(
                domain=domain,
                # "Operates" requires repeated evidence, not one filename.
                observed_capability=observed and not reason_gap,
                data_available=data_available,
                artifact_count=artifact_count,
                evidence_count=evidence_count,
                confidence=(
                    round(min(1.0, evidence_count / 10.0), 4) if evidence_count else 0.0
                ),
                first_observed_at=None,
                last_observed_at=_utcnow() if evidence_count else None,
            )
        )

    business_type, type_confidence, type_origin, observed_types = infer_business_type(
        entities, events
    )
    if business_type is BusinessType.UNKNOWN:
        limitations.append(
            "business type could not be established from the evidence available; "
            "it is reported as unknown rather than guessed"
        )

    observed_currencies = tuple(sorted({c for c in currencies if c}))
    if not observed_currencies:
        limitations.append(
            "no currency could be established from the ingested evidence, so no "
            "monetary total can be compared with another business's"
        )

    return BusinessProfile(
        business_type=business_type,
        business_type_confidence=type_confidence,
        business_type_origin=type_origin,
        observed_business_types=observed_types,
        operating_channels=tuple(
            sorted(e.canonical_name for e in by_kind.get(EntityKind.CHANNEL, []) if e.canonical_name)
        ),
        locations=tuple(
            sorted(e.canonical_name for e in by_kind.get(EntityKind.LOCATION, []) if e.canonical_name)
        ),
        branches=tuple(
            sorted(e.canonical_name for e in by_kind.get(EntityKind.BRANCH, []) if e.canonical_name)
        ),
        product_count=len(by_kind.get(EntityKind.PRODUCT, [])) or None,
        service_count=None,
        supplier_count=len(by_kind.get(EntityKind.SUPPLIER, [])) or None,
        employee_count=len(by_kind.get(EntityKind.EMPLOYEE, [])) or None,
        currencies=observed_currencies,
        countries=(),
        source_systems=(),
        capabilities=tuple(capabilities),
        observed_patterns=tuple(
            f"{len(by_kind.get(EntityKind.BRANCH, []))} branches observed",
        ) if by_kind.get(EntityKind.BRANCH) else (),
        evidence_ids=tuple(sorted({eid for e in events for eid in e.evidence_ids})),
        confidence=round(
            min(1.0, (len(events) / 50.0) + (len(entities) / 100.0)), 4
        ) if (events or entities) else 0.0,
        limitations=tuple(limitations),
        created_at=_utcnow(),
    )