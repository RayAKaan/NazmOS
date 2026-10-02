"""Canonical business state (spec §38, §39, §40).

``CanonicalBusinessState`` is the single authoritative statement of observed
business reality. Everything a later phase believes about a business comes from
here, and everything here is traceable to evidence.

**State versioning is content-derived, not time-derived.** Re-ingesting identical
content produces the *same* ``state_version``, which is what makes reprocessing
idempotent. A version is only created when the canonical content actually changes.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    BusinessProfile,
    BusinessType,
    CanonicalBusinessState,
    Conflict,
    ConflictResolution,
    DataQualityReport,
    DomainCapability,
    DomainCapabilityFlag,
    DomainFreshness,
    Entity,
    EntityKind,
    Evidence,
    EvidenceRegistry,
    FieldStatus,
    FreshnessState,
    Measured,
    UniversalArtifact,
    compute_state_version,
    evaluate_freshness,
    _utcnow,
)
from app.services.orbit.events import coverage_window, events_by_domain
from app.services.orbit.events import domain_of_event


def _sum_measured(events: Sequence[BusinessEvent], attribute: str) -> Measured:
    """Sum a measured attribute, keeping absence distinct from zero.

    A total over events where *none* carry the attribute is unknown, not zero.
    """
    values = [
        getattr(e, attribute).value
        for e in events
        if getattr(e, attribute).value is not None
    ]
    if not values:
        return Measured.missing()
    total = sum(values, Decimal(0))
    evidence = tuple(sorted({
        eid for e in events if getattr(e, attribute).value is not None
        for eid in e.evidence_ids
    }))
    return Measured.present(total, evidence_ids=evidence) if evidence else Measured.present(total)


def build_domain_states(
    events: Sequence[BusinessEvent],
    entities: Sequence[Entity],
) -> dict[str, dict[str, Measured]]:
    """Per-domain aggregates. Absent evidence yields an absent measurement."""
    by_domain = events_by_domain(events)
    states: dict[str, dict[str, Measured]] = {}
    for domain, domain_events in by_domain.items():
        # A derived aggregate is still a fact, so it carries the provenance of the
        # observations it was computed from. The contract rejects a PRESENT value
        # with no evidence, which is the correct behaviour.
        domain_evidence = tuple(sorted({
            eid for e in domain_events for eid in e.evidence_ids
        }))
        states[domain] = {
            "event_count": Measured.present(
                Decimal(len(domain_events)), evidence_ids=domain_evidence
            ) if domain_evidence else Measured.missing(),
            "total_amount": _sum_measured(domain_events, "amount"),
            "total_quantity": _sum_measured(domain_events, "quantity"),
            "undated_events": Measured.present(
                Decimal(sum(1 for e in domain_events if e.business_local_date is None)),
                evidence_ids=domain_evidence,
            ) if domain_evidence else Measured.missing(),
        }
    return states


def build_freshness(
    events: Sequence[BusinessEvent],
    conflicts: Sequence[Conflict],
    *,
    now: Optional[datetime] = None,
) -> tuple[DomainFreshness, ...]:
    """Per-domain freshness, including domains that have no data at all.

    A domain with no events is reported as MISSING rather than omitted, so an
    absent domain is visible instead of invisible.
    """
    by_domain = events_by_domain(events)
    reference = now or _utcnow()

    out: list[DomainFreshness] = []
    for domain in sorted(
        set(by_domain) | {d.value for d in DomainCapability}
    ):
        domain_events = by_domain.get(domain, [])
        dated = [e.business_local_date for e in domain_events if e.business_local_date]
        if not dated:
            out.append(
                DomainFreshness(
                    domain=domain,
                    freshness=FreshnessState.MISSING,
                    last_observed_at=None,
                    last_updated_at=None,
                    source_age_hours=None,
                    reason="no events were observed for this domain",
                )
            )
            continue

        newest = max(dated)
        last_observed = datetime(
            newest.year, newest.month, newest.day, tzinfo=timezone.utc
        )
        freshness = evaluate_freshness(last_observed, now=reference)
        age_hours = round((reference - last_observed).total_seconds() / 3600.0, 2)
        out.append(
            DomainFreshness(
                domain=domain,
                freshness=freshness,
                last_observed_at=last_observed,
                last_updated_at=last_observed,
                source_age_hours=age_hours,
                reason=(
                    f"{len(domain_events)} events, newest dated observation "
                    f"{newest.isoformat()}"
                ),
            )
        )
    return tuple(out)


def build_canonical_state(
    *,
    business_id: Any = None,
    entities: Sequence[Entity] = (),
    events: Sequence[BusinessEvent] = (),
    conflicts: Sequence[Conflict] = (),
    profile: Optional[BusinessProfile] = None,
    quality: Optional[DataQualityReport] = None,
    artifact: Optional[UniversalArtifact] = None,
    registry: Optional[EvidenceRegistry] = None,
    previous_state_version: Optional[str] = None,
) -> CanonicalBusinessState:
    """Assemble the canonical state from already-canonical inputs."""
    entities = tuple(entities)
    events = tuple(events)
    conflicts = tuple(conflicts)
    period_start, period_end = coverage_window(events)

    domain_states = build_domain_states(events, entities)
    limitations: list[str] = []
    for domain, values in sorted(domain_states.items()):
        if values["total_amount"].value is None:
            limitations.append(
                f"no monetary observations for {domain}; its totals are unknown, not zero"
            )
    if not events:
        limitations.append("no events were observed, so no domain totals are available")

    state_version = compute_state_version(
        business_id,
        [artifact.content_hash] if artifact else [],
        [e.entity_id for e in entities],
        [e.row_hash for e in events],
    )

    relationships = _build_relationships(entities, events)

    return CanonicalBusinessState(
        business_id=business_id,
        state_version=state_version,
        previous_state_version=previous_state_version,
        business_type=(profile.business_type if profile else BusinessType.UNKNOWN),
        period_start=period_start,
        period_end=period_end,
        timezone=getattr(artifact, "timezone", None),
        entities=entities,
        events=events,
        conflicts=conflicts,
        relationships=tuple(relationships),
        financial_state=domain_states.get("finance", {}),
        inventory_state=domain_states.get("inventory", {}),
        procurement_state=domain_states.get("procurement", {}),
        workforce_state=domain_states.get("workforce", {}),
        marketing_state=domain_states.get("marketing", {}),
        customer_state=domain_states.get("customer", {}),
        evidence_coverage=_evidence_coverage(registry, events),
        freshness=build_freshness(events, conflicts),
        capabilities=(profile.capabilities if profile else ()),
        artifact_ids=(artifact.artifact_id,) if artifact else (),
        evidence_ids=tuple(sorted({eid for e in events for eid in e.evidence_ids})),
        source_systems=(),
        historical_coverage={
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
            "event_count": len(events),
            "entity_count": len(entities),
        },
        limitations=tuple(limitations),
        warnings=(quality.warnings if quality else ()),
    )


def _build_relationships(
    entities: Sequence[Entity], events: Sequence[BusinessEvent]
) -> list[dict[str, Any]]:
    """Entity relationships observed in the evidence.

    ``sells`` / ``supplies`` / ``works_at`` are asserted only where a source
    actually linked the two entities in a single observation.
    """
    relationships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for event in events:
        product = event.entity_refs.get(EntityKind.PRODUCT.value)
        supplier = event.entity_refs.get(EntityKind.SUPPLIER.value)
        branch = event.entity_refs.get(EntityKind.BRANCH.value)
        employee = event.entity_refs.get(EntityKind.EMPLOYEE.value)
        customer = event.entity_refs.get(EntityKind.CUSTOMER.value)

        for a, b, label in (
            (supplier, product, "supplies"),
            (product, branch, "sold_at"),
            (employee, branch, "works_at"),
            (customer, product, "purchased"),
        ):
            if a and b and (a, b, label) not in seen:
                seen.add((a, b, label))
                relationships.append(
                    {
                        "from": a,
                        "to": b,
                        "type": label,
                        "evidence_ids": list(event.evidence_ids),
                    }
                )
    return relationships


def _evidence_coverage(
    registry: Optional[EvidenceRegistry], events: Sequence[BusinessEvent]
) -> dict[str, str]:
    """Per-domain statement of what evidence exists, in plain language."""
    coverage: dict[str, str] = {}
    by_domain = events_by_domain(events)
    for domain, domain_events in by_domain.items():
        dated = sum(1 for e in domain_events if e.business_local_date is not None)
        total = len(domain_events)
        coverage[domain] = (
            f"{total} events, {dated} dated, "
            f"{len({eid for e in domain_events for eid in e.evidence_ids})} distinct evidence records"
        )
    coverage["total_registered"] = str(len(registry) if registry else 0)
    return coverage


# ─────────────────────────────────────────────────────────────────────────────
# State diffing (§40)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StateDiff:
    """What changed between two canonical states, with lineage preserved."""

    added_entities: tuple[str, ...] = ()
    removed_entities: tuple[str, ...] = ()
    changed_entities: tuple[str, ...] = ()
    added_events: tuple[str, ...] = ()
    removed_events: tuple[str, ...] = ()
    added_conflicts: tuple[str, ...] = ()
    resolved_conflicts: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.added_entities, self.removed_entities, self.changed_entities,
                self.added_events, self.removed_events,
                self.added_conflicts, self.resolved_conflicts,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_empty": self.is_empty,
            "added_entities": list(self.added_entities),
            "removed_entities": list(self.removed_entities),
            "changed_entities": list(self.changed_entities),
            "added_events": list(self.added_events),
            "removed_events": list(self.removed_events),
            "added_conflicts": list(self.added_conflicts),
            "resolved_conflicts": list(self.resolved_conflicts),
        }


def diff_states(before: CanonicalBusinessState, after: CanonicalBusinessState) -> StateDiff:
    """Compare two states.

    An entity counts as *changed* when its identity is stable but its observed
    attributes differ, so a re-ingestion that only restates the same facts is not
    reported as change.
    """
    before_entities = {e.entity_id: e for e in before.entities}
    after_entities = {e.entity_id: e for e in after.entities}
    before_events = {e.row_hash: e for e in before.events}
    after_events = {e.row_hash: e for e in after.events}
    before_conflicts = {c.conflict_id: c for c in before.conflicts}
    after_conflicts = {c.conflict_id: c for c in after.conflicts}

    changed = []
    for entity_id in set(before_entities) & set(after_entities):
        a, b = before_entities[entity_id], after_entities[entity_id]
        if (
            a.confidence != b.confidence
            or set(a.aliases) != set(b.aliases)
            or set(a.evidence_ids) != set(b.evidence_ids)
        ):
            changed.append(entity_id)

    resolved = tuple(
        sorted(
            cid
            for cid in set(before_conflicts) & set(after_conflicts)
            if before_conflicts[cid].status is ConflictResolution.UNRESOLVED
            and after_conflicts[cid].status is not ConflictResolution.UNRESOLVED
        )
    )

    return StateDiff(
        added_entities=tuple(sorted(set(after_entities) - set(before_entities))),
        removed_entities=tuple(sorted(set(before_entities) - set(after_entities))),
        changed_entities=tuple(sorted(changed)),
        added_events=tuple(sorted(set(after_events) - set(before_events))),
        removed_events=tuple(sorted(set(before_events) - set(after_events))),
        added_conflicts=tuple(sorted(set(after_conflicts) - set(before_conflicts))),
        resolved_conflicts=resolved,
    )