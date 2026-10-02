"""Data quality engine (spec §28, §35).

One authoritative assessment with ten dimensions. The repository previously had
four competing quality scores, and one of them was a literal ``return 91``.

Every dimension is computed from evidence and is either a score in ``[0,1]`` or
``None``. ``None`` means **the dimension could not be evaluated**, which is never
the same as zero: a report that cannot judge semantic confidence must not claim
that semantic confidence is perfect.

The overall score is a weighted mean of the dimensions that *could* be evaluated,
with the evaluated weight renormalised. It is reproducible from the inputs shown
in the report, and the report always states which dimensions were excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    BusinessEvent,
    Conflict,
    ConflictResolution,
    DataQualityReport,
    DecisionOrigin,
    DomainCapability,
    EntityResolution,
    EvidenceRegistry,
    QualityDimension,
    QualityDimensionScore,
    QualityIssue,
    QualityIssueKind,
    ResolutionOutcome,
    SourceLocator,
    SourceReliability,
    UniversalArtifact,
)

#: Dimension weights. They sum to 1.0 and are documented here so a score can be
#: reproduced by hand from a report.
DIMENSION_WEIGHTS: dict[QualityDimension, float] = {
    QualityDimension.COMPLETENESS: 0.18,
    QualityDimension.CONSISTENCY: 0.14,
    QualityDimension.VALIDITY: 0.14,
    QualityDimension.UNIQUENESS: 0.12,
    QualityDimension.TIMELINESS: 0.10,
    QualityDimension.COVERAGE: 0.10,
    QualityDimension.SEMANTIC_CONFIDENCE: 0.08,
    QualityDimension.ENTITY_RESOLUTION_QUALITY: 0.08,
    QualityDimension.SOURCE_RELIABILITY: 0.03,
    QualityDimension.CONFLICT_RATE: 0.03,
}

#: A source below this reliability discount caps the overall score. An official
#: POS export and a hand-typed spreadsheet are not equally trustworthy.
UNRELIABLE_SOURCE_CAP = 0.75

#: Artifact kind -> source reliability.
SOURCE_RELIABILITY_BY_KIND: dict[str, SourceReliability] = {
    "pos_export": SourceReliability.OFFICIAL_POS_EXPORT,
    "bank_statement": SourceReliability.BANK_EXPORT,
    "supplier_quote": SourceReliability.SUPPLIER_QUOTE,
    "purchase_order": SourceReliability.SUPPLIER_QUOTE,
    "invoice": SourceReliability.SYSTEM_EXPORT,
    "staff_schedule": SourceReliability.MANUAL_SPREADSHEET,
    "marketing_report": SourceReliability.MANUAL_SPREADSHEET,
    "inventory_export": SourceReliability.MANUAL_SPREADSHEET,
}


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _dimension(
    dimension: QualityDimension,
    score: Optional[float],
    reason: str,
    *,
    evidence_ids: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> QualityDimensionScore:
    return QualityDimensionScore(
        dimension=dimension,
        score=None if score is None else _round(score),
        weight=DIMENSION_WEIGHTS.get(dimension, 0.0),
        reason=reason,
        evidence_ids=tuple(evidence_ids),
        limitations=tuple(limitations),
    )


def assess_quality(
    *,
    business_id: Any = None,
    artifact: Optional[UniversalArtifact] = None,
    column_map: Optional[Any] = None,
    records_seen: int = 0,
    records_accepted: int = 0,
    records_rejected: int = 0,
    records_ambiguous: int = 0,
    events: Sequence[BusinessEvent] = (),
    conflicts: Sequence[Conflict] = (),
    resolutions: Sequence[EntityResolution] = (),
    registry: Optional[EvidenceRegistry] = None,
) -> DataQualityReport:
    """Produce the one authoritative quality report for an ingestion."""
    dimensions: list[QualityDimensionScore] = []
    issues: list[QualityIssue] = []
    limitations: list[str] = []
    unknowns: list[str] = []
    warnings: list[str] = []

    total_rows = records_seen

    # ── completeness ─────────────────────────────────────────────────────────
    if total_rows == 0:
        dimensions.append(
            _dimension(
                QualityDimension.COMPLETENESS, None,
                "no records were read, so completeness cannot be judged",
                limitations=("no rows present in the source",),
            )
        )
    else:
        filled = records_accepted
        completeness = filled / total_rows
        dimensions.append(
            _dimension(
                QualityDimension.COMPLETENESS, completeness,
                f"{filled} of {total_rows} records produced a usable observation",
            )
        )
        if completeness < 0.9:
            issues.append(
                QualityIssue(
                    kind=QualityIssueKind.MISSING,
                    severity=_severity(1 - completeness),
                    message=(
                        f"{total_rows - filled} of {total_rows} records did not yield "
                        "a usable observation"
                    ),
                    domain="ingestion",
                )
            )

    # ── consistency ──────────────────────────────────────────────────────────
    if events:
        # Consistency: a monetary line that also carries a quantity is internally
        # coherent; one that does not cannot be checked at all.
        monetary = [e for e in events if e.amount.value is not None]
        consistency = (
            sum(1 for e in monetary if e.quantity.value is not None) / len(monetary)
            if monetary else None
        )
        if consistency is None:
            dimensions.append(
                _dimension(
                    QualityDimension.CONSISTENCY, None,
                    "no monetary events were observed, so internal consistency is unevaluated",
                )
            )
        else:
            dimensions.append(
                _dimension(
                    QualityDimension.CONSISTENCY, consistency,
                    f"{len(monetary)} monetary events, of which "
                    f"{int(consistency * len(monetary))} also carry a quantity",
                )
            )
            if consistency < 0.5:
                issues.append(
                    QualityIssue(
                        kind=QualityIssueKind.SUSPECT,
                        severity=_severity(1 - consistency),
                        message=(
                            "many monetary events lack a quantity, so line-level "
                            "consistency cannot be checked"
                        ),
                        domain="sales",
                    )
                )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.CONSISTENCY, None,
                "no events were produced, so consistency is unevaluated",
            )
        )

    # ── validity ─────────────────────────────────────────────────────────────
    if events:
        dated = sum(1 for e in events if e.business_local_date is not None)
        validity = dated / len(events)
        dimensions.append(
            _dimension(
                QualityDimension.VALIDITY, validity,
                f"{dated} of {len(events)} events carry a parseable date",
            )
        )
        if validity < 1.0:
            issues.append(
                QualityIssue(
                    kind=QualityIssueKind.PARSING_ERROR,
                    severity=_severity(1 - validity),
                    message=(
                        f"{len(events) - dated} events have no usable date and cannot "
                        "enter any period calculation"
                    ),
                    domain="time",
                )
            )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.VALIDITY, None, "no events to validate"
            )
        )

    # ── uniqueness ───────────────────────────────────────────────────────────
    if events:
        unique = len({e.row_hash for e in events})
        uniqueness = unique / len(events)
        dimensions.append(
            _dimension(
                QualityDimension.UNIQUENESS, uniqueness,
                f"{unique} distinct observations across {len(events)} processed rows",
            )
        )
        if uniqueness < 1.0:
            issues.append(
                QualityIssue(
                    kind=QualityIssueKind.DUPLICATE,
                    severity=_severity(1 - uniqueness),
                    message=f"{len(events) - unique} duplicate observations were dropped",
                    domain="ingestion",
                )
            )
    else:
        dimensions.append(
            _dimension(QualityDimension.UNIQUENESS, None, "no events to compare")
        )

    # ── timeliness ───────────────────────────────────────────────────────────
    from app.services.orbit.contracts import FreshnessState, evaluate_freshness

    if events:
        dates = [e.business_local_date for e in events if e.business_local_date]
        if dates:
            newest = max(dates)
            freshness = evaluate_freshness(
                artifact.observed_at or artifact.received_at if artifact else None
            )
            timeliness = (
                1.0 if freshness is FreshnessState.FRESH
                else 0.8 if freshness is FreshnessState.RECENT
                else 0.4 if freshness is FreshnessState.STALE else 0.0
            )
            dimensions.append(
                _dimension(
                    QualityDimension.TIMELINESS, timeliness,
                    f"newest observed date {newest.isoformat()}; source freshness "
                    f"{freshness.value}",
                )
            )
            if freshness is FreshnessState.STALE:
                warnings.append("the newest observed date is stale relative to ingest time")
        else:
            dimensions.append(
                _dimension(
                    QualityDimension.TIMELINESS, None,
                    "no dated observations, so timeliness cannot be assessed",
                )
            )
    else:
        dimensions.append(
            _dimension(QualityDimension.TIMELINESS, None, "no events to time")
        )

    # ── coverage ─────────────────────────────────────────────────────────────
    if column_map is not None:
        mapped = len(column_map.role_to_header)
        total_columns = len(column_map.mappings)
        coverage = mapped / total_columns if total_columns else None
        dimensions.append(
            _dimension(
                QualityDimension.COVERAGE, coverage,
                f"{mapped} of {total_columns} columns mapped to canonical roles",
            )
        )
        for ambiguous in column_map.ambiguous_headers:
            issues.append(
                QualityIssue(
                    kind=QualityIssueKind.SEMANTIC_AMBIGUITY,
                    severity=_severity(0.5),
                    message=f"column {ambiguous!r} could not be mapped unambiguously",
                    locator=ambiguous,
                    domain="semantics",
                )
            )
        if column_map.unmapped_headers:
            unknowns.append(
                f"unmapped columns: {', '.join(column_map.unmapped_headers)}"
            )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.COVERAGE, None,
                "no tabular columns were mapped, so coverage is unevaluated",
            )
        )
        limitations.append("coverage could not be evaluated for a non-tabular artifact")

    # ── semantic confidence ──────────────────────────────────────────────────
    if column_map is not None:
        mean = column_map.mean_confidence
        dimensions.append(
            _dimension(
                QualityDimension.SEMANTIC_CONFIDENCE, mean,
                "mean confidence of the accepted column mappings"
                if mean is not None else "no column was mapped",
                limitations=(
                    ("semantic confidence reflects header matching only, not the "
                     "correctness of the resulting business meaning",)
                ) if mean is not None else (),
            )
        )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.SEMANTIC_CONFIDENCE, None,
                "no column mapping was produced",
            )
        )

    # ── entity resolution quality ────────────────────────────────────────────
    if resolutions:
        decided = sum(1 for r in resolutions if r.outcome is not ResolutionOutcome.AMBIGUOUS)
        ambiguous = len(resolutions) - decided
        resolution_quality = decided / len(resolutions)
        dimensions.append(
            _dimension(
                QualityDimension.ENTITY_RESOLUTION_QUALITY, resolution_quality,
                f"{decided} of {len(resolutions)} references resolved decisively",
            )
        )
        for resolution in resolutions:
            if resolution.outcome is ResolutionOutcome.AMBIGUOUS:
                issues.append(
                    QualityIssue(
                        kind=QualityIssueKind.SUSPECT,
                        severity=_severity(0.6),
                        message=(
                            f"{resolution.kind.value} reference {resolution.query!r} is "
                            f"ambiguous: {resolution.note}"
                        ),
                        entity_ref=resolution.query,
                        domain="entities",
                    )
                )
        if ambiguous:
            warnings.append(f"{ambiguous} entity references are ambiguous and were not merged")
    else:
        dimensions.append(
            _dimension(
                QualityDimension.ENTITY_RESOLUTION_QUALITY, None,
                "no entity references were resolved",
            )
        )

    # ── source reliability ───────────────────────────────────────────────────
    kind = None
    if artifact is not None:
        kind = artifact.artifact_type.value
        reliability = SOURCE_RELIABILITY_BY_KIND.get(kind, SourceReliability.UNKNOWN_SOURCE)
        reliability_score = {
            SourceReliability.OFFICIAL_POS_EXPORT: 1.0,
            SourceReliability.BANK_EXPORT: 1.0,
            SourceReliability.SYSTEM_EXPORT: 0.9,
            SourceReliability.SUPPLIER_QUOTE: 0.75,
            SourceReliability.MANUAL_SPREADSHEET: 0.6,
            SourceReliability.OCR_DOCUMENT: 0.4,
            SourceReliability.USER_ENTERED: 0.5,
            SourceReliability.UNKNOWN_SOURCE: None,
        }[reliability]
        dimensions.append(
            _dimension(
                QualityDimension.SOURCE_RELIABILITY, reliability_score,
                f"source classified as {reliability.value}",
                limitations=()
                if reliability_score is not None
                else ("source reliability is unknown, so the score is withheld",),
            )
        )
        if artifact.classification_needs_review:
            issues.append(
                QualityIssue(
                    kind=QualityIssueKind.SEMANTIC_AMBIGUITY,
                    severity=_severity(0.5),
                    message="the artifact classification itself needs review",
                    domain="ingestion",
                )
            )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.SOURCE_RELIABILITY, None, "no artifact to assess"
            )
        )

    # ── conflict rate ────────────────────────────────────────────────────────
    if events:
        conflicting = sum(1 for c in conflicts if c.severity.value in ("high", "critical"))
        conflict_rate = min(1.0, conflicting / len(events))
        dimensions.append(
            _dimension(
                QualityDimension.CONFLICT_RATE, 1.0 - conflict_rate,
                f"{conflicting} high or critical conflicts across {len(events)} events",
            )
        )
        for conflict in conflicts:
            if conflict.status in (ConflictResolution.UNRESOLVED, ConflictResolution.NEEDS_REVIEW):
                issues.append(
                    QualityIssue(
                        kind=QualityIssueKind.CONFLICT,
                        severity=conflict.severity,
                        message=(
                            f"{conflict.field} disagrees: {conflict.value_a} vs "
                            f"{conflict.value_b} ({conflict.classification})"
                        ),
                        entity_ref=conflict.entity_ref,
                        evidence_ids=tuple(
                            e for e in (conflict.evidence_a, conflict.evidence_b) if e
                        ),
                        domain="conflicts",
                    )
                )
    else:
        dimensions.append(
            _dimension(
                QualityDimension.CONFLICT_RATE, None,
                "no events, so no conflict rate can be computed",
            )
        )

    overall = _overall(dimensions, artifact)
    if kind:
        limitations.append(f"artifact kind: {kind}")

    affected_domains = sorted({i.domain for i in issues if i.domain})
    affected_entities = sorted({i.entity_ref for i in issues if i.entity_ref})

    return DataQualityReport(
        business_id=business_id,
        ingestion_run_id=artifact.ingestion_run_id if artifact else None,
        artifact_ids=(artifact.artifact_id,) if artifact else (),
        overall_score=overall,
        dimensions=tuple(dimensions),
        issues=tuple(issues),
        critical_issues=tuple(
            i for i in issues if i.severity.value in ("high", "critical")
        ),
        warnings=tuple(dict.fromkeys(warnings)),
        unknowns=tuple(dict.fromkeys(unknowns)),
        affected_domains=tuple(affected_domains),
        affected_entities=tuple(affected_entities),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _overall(
    dimensions: Sequence[QualityDimensionScore],
    artifact: Optional[UniversalArtifact],
) -> Optional[float]:
    """Weighted mean of evaluated dimensions, with the weight renormalised.

    Returns ``None`` when nothing could be evaluated, which is the honest answer
    for an artifact that produced no assessable data.
    """
    usable = [
        d for d in dimensions
        if d.score is not None and d.weight > 0 and d.dimension is not QualityDimension.SOURCE_RELIABILITY
    ]
    if not usable:
        return None
    total_weight = sum(d.weight for d in usable)
    if total_weight <= 0:
        return None
    score = sum((d.score or 0.0) * d.weight for d in usable) / total_weight

    # An untrustworthy source caps the overall score, so a well-formed but
    # hand-typed sheet cannot present as authoritative.
    reliability = next(
        (d for d in dimensions if d.dimension is QualityDimension.SOURCE_RELIABILITY), None
    )
    if reliability is not None and reliability.score is not None and reliability.score < 0.7:
        score = min(score, UNRELIABLE_SOURCE_CAP)

    return _round(score)


def _severity(gap: float) -> Any:
    from app.services.orbit.contracts import ConflictSeverity

    if gap >= 0.5:
        return ConflictSeverity.HIGH
    if gap >= 0.2:
        return ConflictSeverity.MEDIUM
    return ConflictSeverity.LOW


def quality_formula() -> str:
    """Human-readable description of how the overall score is produced."""
    return (
        "overall_score = sum(score_d * weight_d) / sum(weight_d) over the dimensions "
        "that could be evaluated (source reliability is excluded from the mean and "
        "used only as a cap), where "
        + ", ".join(f"{d.value}={w}" for d, w in DIMENSION_WEIGHTS.items())
        + ". A dimension that cannot be evaluated contributes nothing and is listed "
        "in unevaluated_dimensions."
    )