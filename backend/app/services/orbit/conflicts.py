"""Conflict detection (spec §25, §26, §27).

Silent first-write-wins is how two sources end up disagreeing invisibly. Every
disagreement is recorded with both values, both periods and an explicit
relationship, and is **never** resolved by picking a side or averaging.

The distinction that matters most: ordinary time-series movement is not a
conflict. A stock level of 40 on Monday and 30 on Tuesday is the business
working, not two sources contradicting each other. Only observations that claim
to describe the *same* thing at the *same* time can conflict.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    Conflict,
    ConflictRelationship,
    ConflictResolution,
    ConflictSeverity,
    DecisionOrigin,
    EvidenceRegistry,
    SourceType,
    content_hash,
)

#: Fields compared for agreement. Two observations disagree only on these.
COMPARED_FIELDS = ("amount", "quantity", "unit_price")

#: How close two values must be to count as agreeing.
DECIMAL_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class _Observation:
    event: BusinessEvent
    field_name: str
    value: Decimal

    @property
    def period(self) -> Optional[date]:
        return self.event.business_local_date


#: Entity kinds ordered by how specifically they identify the subject of a line.
#: The first one present is used to group observations, so two products sold at
#: one branch are not compared against each other.
_SUBJECT_PRIORITY = ("product", "customer", "employee", "supplier", "channel")


def _subject_key(event: BusinessEvent) -> Optional[str]:
    """The entity that identifies what an observation is *about*."""
    for kind in _SUBJECT_PRIORITY:
        entity_id = event.entity_refs.get(kind)
        if entity_id:
            return entity_id
    # No specific subject: fall back to a stable key over every reference.
    if event.entity_refs:
        return "|".join(sorted(f"{k}:{v}" for k, v in event.entity_refs.items()))
    return None


def _observations(
    events: Sequence[BusinessEvent], entity_key: str, field_name: str
) -> list[_Observation]:
    out: list[_Observation] = []
    for event in events:
        if entity_key not in event.entity_refs.values():
            continue
        measured = getattr(event, field_name, None)
        if measured is None or measured.value is None:
            continue
        out.append(_Observation(event=event, field_name=field_name, value=measured.value))
    return out


def _agree(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= DECIMAL_TOLERANCE


def _relationship(
    a: _Observation, b: _Observation, *, same_artifact: bool
) -> ConflictRelationship:
    """Classify why two observations differ.

    Deterministic classification first; bounded judgment is only consulted by
    :func:`classify_ambiguous_conflict` and its answer is recorded as metadata,
    never used to alter the data.
    """
    if same_artifact:
        # The same source asserting two different values for one entity/field at
        # one time is a duplication or transcription problem, not new information.
        return ConflictRelationship.DUPLICATES

    if a.period and b.period and a.period != b.period:
        # Different times are not a contradiction; this is the business changing.
        return ConflictRelationship.TEMPORAL_VALID

    if a.event.source_type is b.event.source_type:
        return ConflictRelationship.CONTRADICTS

    return ConflictRelationship.CONTRADICTS


def _severity(field_name: str, relationship: ConflictRelationship) -> ConflictSeverity:
    if relationship in (ConflictRelationship.DUPLICATES,):
        return ConflictSeverity.LOW
    if field_name in ("amount", "unit_price"):
        return ConflictSeverity.HIGH
    return ConflictSeverity.MEDIUM


def detect_conflicts(
    events: Sequence[BusinessEvent],
    registry: Optional[EvidenceRegistry] = None,
    *,
    entity_kind: Optional[str] = None,
) -> tuple[Conflict, ...]:
    """Find every genuine disagreement between observations of the same fact.

    Conflicts are deduplicated by content, so re-ingesting the same data cannot
    multiply the conflict list.
    """
    conflicts: dict[str, Conflict] = {}
    evidence_index = {
        e.evidence_id: e for e in (registry.all() if registry else ())
    }

    # Group by (subject, field) so only like is compared with like.
    #
    # The subject is the *primary* entity of the event, not every entity it
    # mentions. Two different products sold at the same branch both reference that
    # branch, so grouping by "any referenced entity" would compare Pepsi against
    # Nestle and invent a conflict between unrelated products.
    grouped: dict[tuple[str, str], list[BusinessEvent]] = defaultdict(list)
    for event in events:
        subject = _subject_key(event)
        if subject is None:
            continue
        for field_name in COMPARED_FIELDS:
            measured = getattr(event, field_name, None)
            if measured is not None and measured.value is not None:
                grouped[(subject, field_name)].append(event)

    for (subject, field_name), group in sorted(grouped.items()):
        if len(group) < 2:
            continue

        # Same-period comparisons are the only ones that can contradict.
        by_period: dict[Optional[date], list[BusinessEvent]] = defaultdict(list)
        for event in group:
            by_period[event.business_local_date].append(event)

        for period, same_period in sorted(
            by_period.items(), key=lambda kv: (kv[0] is None, kv[0] or date.min)
        ):
            if len(same_period) < 2:
                continue
            for i in range(len(same_period)):
                for j in range(i + 1, len(same_period)):
                    conflict = _compare(
                        subject, field_name, same_period[i], same_period[j],
                        evidence_index, period,
                    )
                    if conflict is not None:
                        conflicts.setdefault(conflict.conflict_id, conflict)

    return tuple(sorted(conflicts.values(), key=lambda c: c.conflict_id))


def _compare(
    entity_id: str,
    field_name: str,
    left: BusinessEvent,
    right: BusinessEvent,
    evidence_index: Mapping[str, Any],
    period: Optional[date],
) -> Optional[Conflict]:
    a_value = getattr(left, field_name)
    b_value = getattr(right, field_name)
    if a_value is None or b_value is None:
        return None
    if a_value.value is None or b_value.value is None:
        return None
    if _agree(a_value.value, b_value.value):
        return None

    same_artifact = left.source_locator.locator == right.source_locator.locator and (
        left.evidence_ids and left.evidence_ids == right.evidence_ids
    )
    a_obs = _Observation(event=left, field_name=field_name, value=a_value.value)
    b_obs = _Observation(event=right, field_name=field_name, value=b_value.value)
    relationship = _relationship(a_obs, b_obs, same_artifact=same_artifact)

    ev_a = left.evidence_ids[0] if left.evidence_ids else ""
    ev_b = right.evidence_ids[0] if right.evidence_ids else ""
    a_ev = evidence_index.get(ev_a)
    b_ev = evidence_index.get(ev_b)

    period_tuple = (period, period) if period else None
    return Conflict(
        business_id=left.business_id,
        entity_ref=entity_id,
        field=field_name,
        evidence_a=ev_a,
        evidence_b=ev_b,
        value_a=str(a_value.value),
        value_b=str(b_value.value),
        relationship=relationship,
        severity=_severity(field_name, relationship),
        period_a=period_tuple,
        period_b=period_tuple,
        classification=_classification_for(relationship),
        classification_origin=DecisionOrigin.DETERMINISTIC,
        status=ConflictResolution.NEEDS_REVIEW
        if relationship is ConflictRelationship.CONTRADICTS
        else ConflictResolution.RESOLVED_DETERMINISTIC,
        resolution_method=(
            "not applicable: temporal variation is a real change, not a conflict"
            if relationship is ConflictRelationship.TEMPORAL_VALID
            else None
        ),
    )


def _classification_for(relationship: ConflictRelationship) -> str:
    """The JEV classification vocabulary applied deterministically."""
    return {
        ConflictRelationship.DUPLICATES: "DUPLICATE",
        ConflictRelationship.TEMPORAL_VALID: "TEMPORAL_DIFFERENCE",
        ConflictRelationship.SUPERSEDES: "SOURCE_LAG",
        ConflictRelationship.PARTIALLY_OVERLAPS: "SOURCE_LAG",
        ConflictRelationship.CONTRADICTS: "TRUE_CONFLICT",
        ConflictRelationship.UNKNOWN: "AMBIGUOUS",
    }[relationship]


def classify_ambiguous_conflict(conflict: Conflict, jev: Optional[Any]) -> Conflict:
    """Consult bounded judgment about a conflict's nature.

    JEV cannot resolve the underlying data. Its choice becomes metadata on the
    conflict, recorded with ``classification_origin=JEV`` so a reviewer can tell
    a judgment from a fact. A failure leaves the deterministic classification.
    """
    if jev is None:
        return conflict
    try:
        decision = jev.classify_conflict(
            relationship=conflict.relationship.value,
            field=conflict.field,
            value_a=conflict.value_a,
            value_b=conflict.value_b,
        )
    except Exception:
        return conflict

    choice = getattr(decision, "choice", None)
    allowed = {
        "DUPLICATE", "SOURCE_LAG", "DATA_ENTRY_ERROR", "TEMPORAL_DIFFERENCE",
        "LEGITIMATE_VARIATION", "TRUE_CONFLICT", "AMBIGUOUS",
    }
    if choice not in allowed:
        return conflict

    from dataclasses import replace

    return replace(
        conflict,
        classification=choice,
        classification_origin=DecisionOrigin.JEV,
    )


def conflict_summary(conflicts: Sequence[Conflict]) -> dict[str, Any]:
    """Counts by relationship and severity, with nothing unresolved hidden."""
    by_relationship: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    unresolved: list[str] = []
    for conflict in conflicts:
        by_relationship[conflict.relationship.value] += 1
        by_severity[conflict.severity.value] += 1
        if conflict.status is ConflictResolution.UNRESOLVED:
            unresolved.append(conflict.conflict_id)
    return {
        "total": len(conflicts),
        "by_relationship": dict(sorted(by_relationship.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "unresolved_count": len(unresolved),
        "unresolved_ids": sorted(unresolved),
        "requires_review_count": sum(
            1 for c in conflicts if c.status is ConflictResolution.NEEDS_REVIEW
        ),
    }


def unresolved(conflicts: Sequence[Conflict]) -> tuple[Conflict, ...]:
    """Conflicts still awaiting a decision. Never filtered out of reports."""
    return tuple(
        c for c in conflicts
        if c.status in (ConflictResolution.UNRESOLVED, ConflictResolution.NEEDS_REVIEW)
    )