"""Production gateway for the canonical Orbit ingestion path.

All authenticated file uploads and provider adapters enter here. Transport-specific
validation may happen before this boundary, but semantic interpretation, canonical
events/state, and compatibility-table projection happen only through the Orbit
pipeline.

Phase 1 deliberately contains no LLM path. JEV remains bounded and optional inside
the canonical pipeline.
"""
from __future__ import annotations

import json
from dataclasses import is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    OrbitBusinessProfile,
    OrbitConflict,
    OrbitDataQuality,
    OrbitEntity,
    OrbitEntityAlias,
    OrbitEvidence,
    OrbitIngestionRun,
    OrbitSemanticMapping,
    OrbitStateVersion,
    UniversalArtifact,
)
from app.services.orbit.contracts import (
    CanonicalBusinessState,
    EvidenceRegistry,
    SourceType,
    content_hash,
)
from app.services.orbit.ingestion.pipeline import CanonicalIngestionResult, ingest_artifact
from app.services.orbit.projection import ProjectionResult, project_state
from app.services.orbit.state import build_canonical_state


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in vars(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(v) for v in value]
    return value


def _stable_uuid(*parts: Any) -> UUID:
    return UUID(content_hash(*parts)[:32])


def _full_state_payload(state: CanonicalBusinessState) -> dict[str, Any]:
    payload = state.to_dict()
    payload.update(
        {
            "entities": [_jsonable(e) for e in state.entities],
            "events": [_jsonable(e) for e in state.events],
            "conflicts": [_jsonable(c) for c in state.conflicts],
            "relationships": _jsonable(state.relationships),
        }
    )
    return payload


async def _persist_result(
    db: AsyncSession,
    *,
    result: CanonicalIngestionResult,
    state: CanonicalBusinessState,
    source_location: Optional[str],
) -> None:
    """Persist canonical observations without creating a second interpreter."""
    business_id = result.business_id
    if business_id is None:
        return

    existing_run = await db.get(OrbitIngestionRun, result.run_id)
    if existing_run is None:
        db.add(
            OrbitIngestionRun(
                id=result.run_id,
                business_id=business_id,
                status=result.status.value,
                records_seen=result.records_seen,
                records_accepted=result.records_accepted,
                records_rejected=result.records_rejected,
                records_ambiguous=result.records_ambiguous,
                conflicts_detected=len(result.conflicts),
                warnings=list(result.warnings),
                errors=list(result.errors),
                state_version_before=result.state_version_before,
                state_version_after=result.state_version_after,
                completed_at=datetime.now().astimezone(),
            )
        )

    artifact_query = await db.execute(
        select(UniversalArtifact).where(
            UniversalArtifact.business_id == business_id,
            UniversalArtifact.content_hash == result.artifact.content_hash,
        )
    )
    if artifact_query.scalar_one_or_none() is None:
        a = result.artifact
        db.add(
            UniversalArtifact(
                id=a.artifact_id,
                business_id=business_id,
                tenant_id=a.tenant_id,
                ingestion_run_id=result.run_id,
                source_type=a.source_type.value,
                source_name=a.source_name,
                source_location=source_location,
                mime_type=a.mime_type,
                artifact_type=a.artifact_type.value,
                classification_confidence=a.classification_confidence,
                classification_origin=a.classification_origin.value,
                classification_alternatives=list(a.classification_alternatives),
                classification_needs_review=a.classification_needs_review,
                content_hash=a.content_hash,
                size_bytes=a.size_bytes,
                version=a.version,
                received_at=a.received_at,
                observed_at=a.observed_at,
                period_start=a.period_start,
                period_end=a.period_end,
                timezone=a.timezone,
                currency=a.currency,
                language=a.language,
                status=a.status.value,
                confidence=a.confidence,
                quality=dict(a.quality),
            )
        )

    for ev in result.evidence:
        existing = await db.execute(
            select(OrbitEvidence).where(
                OrbitEvidence.artifact_id == ev.artifact_id,
                OrbitEvidence.hash == ev.hash,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(
            OrbitEvidence(
                id=_stable_uuid("evidence", ev.artifact_id, ev.hash),
                audit_id=None,
                finding_id=None,
                metric_name=None,
                evidence_type="source",
                source_ref=ev.source_locator.to_dict(),
                calculation={},
                artifact_id=ev.artifact_id,
                business_id=business_id,
                tenant_id=ev.tenant_id,
                ingestion_run_id=result.run_id,
                source_type=ev.source_type.value,
                source_locator=ev.source_locator.to_dict(),
                raw_value=ev.raw_value,
                normalized_value=ev.normalized_value,
                semantic_role=ev.semantic_role,
                entity_ref=ev.entity_ref,
                observed_at=ev.observed_at,
                period_start=ev.period_start,
                period_end=ev.period_end,
                confidence=ev.confidence,
                quality=dict(ev.quality),
                extraction_method=ev.extraction_method.value,
                is_ocr=ev.is_ocr,
                hash=ev.hash,
            )
        )

    entity_db_ids: dict[str, UUID] = {}
    for entity in result.entities:
        entity_id = _stable_uuid("entity", business_id, entity.entity_id)
        entity_db_ids[entity.entity_id] = entity_id
        existing = await db.execute(
            select(OrbitEntity).where(
                OrbitEntity.business_id == business_id,
                OrbitEntity.kind == entity.kind.value,
                OrbitEntity.entity_ref == entity.entity_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                OrbitEntity(
                    id=entity_id,
                    business_id=business_id,
                    kind=entity.kind.value,
                    entity_ref=entity.entity_id,
                    canonical_name=entity.canonical_name,
                    normalized_name=entity.normalized_name,
                    identifiers=dict(entity.identifiers),
                    language=entity.language,
                    confidence=entity.confidence,
                    resolution_origin="deterministic",
                    resolution_method="canonical_pipeline",
                    is_ambiguous=False,
                    first_seen_at=entity.first_seen_at,
                    last_seen_at=entity.last_seen_at,
                )
            )

        for alias in entity.aliases:
            alias_norm = alias.strip().lower()
            if not alias_norm:
                continue
            exists_alias = await db.execute(
                select(OrbitEntityAlias).where(
                    OrbitEntityAlias.entity_id == entity_id,
                    OrbitEntityAlias.normalized_alias == alias_norm,
                )
            )
            if exists_alias.scalar_one_or_none() is None:
                db.add(
                    OrbitEntityAlias(
                        id=_stable_uuid("alias", entity_id, alias_norm),
                        business_id=business_id,
                        entity_id=entity_id,
                        kind=entity.kind.value,
                        raw_alias=alias,
                        normalized_alias=alias_norm,
                        match_method="canonical_pipeline",
                        outcome="same_entity",
                        confidence=entity.confidence,
                        origin="deterministic",
                        evidence_ids=list(entity.evidence_ids),
                    )
                )

    for conflict in result.conflicts:
        exists_conflict = await db.execute(
            select(OrbitConflict).where(
                OrbitConflict.business_id == business_id,
                OrbitConflict.conflict_ref == conflict.conflict_id,
            )
        )
        if exists_conflict.scalar_one_or_none() is None:
            period_a = conflict.period_a or (None, None)
            period_b = conflict.period_b or (None, None)
            db.add(
                OrbitConflict(
                    id=_stable_uuid("conflict", business_id, conflict.conflict_id),
                    business_id=business_id,
                    conflict_ref=conflict.conflict_id,
                    entity_ref=conflict.entity_ref,
                    field=conflict.field,
                    evidence_a=conflict.evidence_a,
                    evidence_b=conflict.evidence_b,
                    value_a=conflict.value_a,
                    value_b=conflict.value_b,
                    relationship=conflict.relationship.value,
                    severity=conflict.severity.value,
                    classification=conflict.classification,
                    classification_origin=conflict.classification_origin.value,
                    period_a_start=period_a[0],
                    period_a_end=period_a[1],
                    period_b_start=period_b[0],
                    period_b_end=period_b[1],
                    status=conflict.status.value,
                    resolution_method=conflict.resolution_method,
                )
            )

    if result.column_map is not None:
        for idx, mapping in enumerate(result.column_map.mappings):
            exists_mapping = await db.execute(
                select(OrbitSemanticMapping).where(
                    OrbitSemanticMapping.artifact_id == result.artifact_id,
                    OrbitSemanticMapping.header_index == idx,
                )
            )
            if exists_mapping.scalar_one_or_none() is None:
                db.add(
                    OrbitSemanticMapping(
                        id=_stable_uuid("semantic", result.artifact_id, idx),
                        artifact_id=result.artifact_id,
                        business_id=business_id,
                        sheet=None,
                        header_index=idx,
                        raw_header=mapping.raw_header,
                        normalized_header=mapping.normalized_header,
                        candidate_roles=[c.to_dict() for c in mapping.candidates],
                        selected_role=mapping.selected_role,
                        confidence=mapping.confidence,
                        origin=mapping.origin.value,
                        evidence_ids=[],
                        ambiguity="; ".join(mapping.notes) if mapping.notes else None,
                    )
                )

    if result.profile is not None:
        profile = result.profile
        existing_profile = await db.execute(
            select(OrbitBusinessProfile).where(OrbitBusinessProfile.business_id == business_id)
        )
        row = existing_profile.scalar_one_or_none()
        payload = {
            "state_version": state.state_version,
            "business_type": profile.business_type.value,
            "business_type_confidence": profile.business_type_confidence,
            "business_type_origin": profile.business_type_origin.value,
            "observed_business_types": list(profile.observed_business_types),
            "operating_channels": list(profile.operating_channels),
            "locations": list(profile.locations),
            "branches": list(profile.branches),
            "currencies": list(profile.currencies),
            "countries": list(profile.countries),
            "source_systems": list(profile.source_systems),
            "capabilities": {c.domain.value: _jsonable(c) for c in profile.capabilities},
            "observed_patterns": list(profile.observed_patterns),
            "product_count": profile.product_count,
            "service_count": profile.service_count,
            "supplier_count": profile.supplier_count,
            "employee_count": profile.employee_count,
            "confidence": profile.confidence,
            "limitations": list(profile.limitations),
            "evidence_ids": list(profile.evidence_ids),
        }
        if row is None:
            db.add(
                OrbitBusinessProfile(
                    id=_stable_uuid("profile", business_id),
                    business_id=business_id,
                    **payload,
                )
            )
        else:
            for key, value in payload.items():
                setattr(row, key, value)

    if result.quality is not None:
        q = result.quality
        quality_id = _stable_uuid("quality", result.run_id)
        existing_quality = await db.get(OrbitDataQuality, quality_id)
        if existing_quality is None:
            db.add(
                OrbitDataQuality(
                    id=quality_id,
                    run_id=result.run_id,
                    overall_score=None if q.overall_score is None else int(round(q.overall_score)),
                    domain_scores={d.dimension.value: d.score for d in q.dimensions},
                    missing_required_fields=list(q.unknowns),
                    ambiguous_fields=[
                        i.message for i in q.issues if i.kind.value == "semantic_ambiguity"
                    ],
                )
            )

    existing_state = await db.execute(
        select(OrbitStateVersion).where(
            OrbitStateVersion.business_id == business_id,
            OrbitStateVersion.state_version == state.state_version,
        )
    )
    if existing_state.scalar_one_or_none() is None:
        db.add(
            OrbitStateVersion(
                id=_stable_uuid("state", business_id, state.state_version),
                business_id=business_id,
                state_version=state.state_version,
                previous_state_version=state.previous_state_version,
                state=_full_state_payload(state),
                artifact_hashes=[result.artifact.content_hash],
                entity_refs=[e.entity_id for e in state.entities],
                evidence_ids=list(state.evidence_ids),
                freshness=[_jsonable(f) for f in state.freshness],
                evidence_coverage=dict(state.evidence_coverage),
                limitations=list(state.limitations),
                period_start=state.period_start,
                period_end=state.period_end,
                timezone=state.timezone,
            )
        )

    await db.flush()


async def ingest_and_project(
    db: AsyncSession,
    content: bytes,
    *,
    business_id: UUID,
    source_name: str,
    source_type: SourceType = SourceType.FILE,
    mime_type: Optional[str] = None,
    source_location: Optional[str] = None,
    timezone_name: str = "Asia/Riyadh",
    jev: Any | None = None,
    column_mapping_override: Optional[Mapping[str, str]] = None,
) -> tuple[CanonicalIngestionResult, ProjectionResult]:
    """Canonical authenticated ingestion + persistence + compatibility projection."""
    from app.services.orbit.ingestion.pipeline import CanonicalOrbitIngestionPipeline

    pipeline = CanonicalOrbitIngestionPipeline(
        business_id=business_id,
        timezone_name=timezone_name,
        jev=jev,
    )
    result = pipeline.ingest(
        content,
        source_name=source_name,
        source_type=source_type,
        mime_type=mime_type,
        column_mapping_override=column_mapping_override,
    )

    registry = EvidenceRegistry()
    for evidence in result.evidence:
        registry.register(evidence)

    state = build_canonical_state(
        business_id=business_id,
        entities=result.entities,
        events=result.events,
        conflicts=result.conflicts,
        profile=result.profile,
        quality=result.quality,
        artifact=result.artifact,
        registry=registry,
        previous_state_version=result.state_version_before,
    )

    await _persist_result(
        db,
        result=result,
        state=state,
        source_location=source_location,
    )

    projection = await project_state(
        state,
        business_id=str(business_id),
        session=db,
    )
    await db.commit()
    return result, projection


async def ingest_pos_records(
    db: AsyncSession,
    records: list[dict[str, Any]],
    *,
    business_id: UUID,
    source_name: str,
    provider: str,
    external_reference: Optional[str],
) -> tuple[CanonicalIngestionResult, ProjectionResult]:
    """Convert a provider payload to canonical JSON rows, then enter the same pipeline."""
    payload = {
        "provider": provider,
        "external_reference": external_reference,
        "rows": records,
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return await ingest_and_project(
        db,
        content,
        business_id=business_id,
        source_name=source_name,
        source_type=SourceType.API,
        mime_type="application/json",
        source_location=f"api://{provider}/{external_reference or 'unknown'}",
    )


def provider_order_rows(provider: str, payload: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Flatten provider transport into canonical source rows.

    This adapter only translates transport shape; it never writes product tables.
    """
    if provider == "foodics":
        order = payload.get("order", payload) or {}
        reference = str(order.get("reference") or order.get("id") or "")
        occurred = order.get("created_at") or order.get("updated_at") or order.get("date")
        rows = [
            {
                "transaction_id": reference,
                "transaction_date": occurred,
                "product_name": item.get("name"),
                "sku": item.get("sku") or item.get("code"),
                "barcode": item.get("barcode") or item.get("ean"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price") or item.get("price"),
            }
            for item in (order.get("products", []) or [])
        ]
        return reference, rows

    if provider == "salla":
        order = payload.get("data", payload) or {}
        reference = str(order.get("id") or order.get("reference_id") or "")
        occurred = order.get("created_at") or order.get("updated_at") or order.get("date")
        rows: list[dict[str, Any]] = []
        for item in order.get("items", []) or []:
            amounts = item.get("amounts", {}) or {}
            price = (amounts.get("price_without_tax", {}) or {}).get("amount")
            if price is None:
                price = item.get("price")
            rows.append(
                {
                    "transaction_id": reference,
                    "transaction_date": occurred,
                    "product_name": item.get("name"),
                    "sku": item.get("sku") or item.get("product_sku"),
                    "barcode": item.get("barcode") or item.get("ean"),
                    "quantity": item.get("quantity"),
                    "unit_price": price,
                }
            )
        return reference, rows

    raise ValueError(f"Unsupported POS provider: {provider}")
