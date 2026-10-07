"""The single canonical ingestion pipeline (spec §3, §4).

    Files / APIs / Imports
            ↓
        Artifact
            ↓      Classification
        Extraction
            ↓      Evidence
        Semantic normalization
            ↓      Row roles
        Entity resolution
            ↓      Time / Unit / Currency normalization
        Conflict detection
            ↓
        Data quality
            ↓      Business profile
        Canonical events/state
            ↓      State version
        BusinessContext

Every ingestion entry point — authenticated upload, guest upload, POS webhook,
scheduled POS sync — calls :func:`ingest_artifact`. There is no second path that
produces truth. Transport differs; the truth model does not.

The pipeline is deliberately *in-memory*: it produces canonical contracts without
touching the database, which is what lets the convergence tests assert that two
different transports produce identical canonical state. Persistence and the ETL
projector are separate, later stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Optional, Sequence
from uuid import UUID, uuid4

from app.services.orbit.contracts import (
    ArtifactType,
    BusinessContext,
    BusinessEvent,
    BusinessEventType,
    BusinessType,
    Conflict,
    ConflictRelationship,
    ConflictResolution,
    ConflictSeverity,
    DataQualityReport,
    DecisionOrigin,
    DomainCapability,
    DomainCapabilityFlag,
    EntityKind,
    EntityResolution,
    ErrorCategory,
    Evidence,
    EvidenceRegistry,
    ExtractionMethod,
    FieldStatus,
    IngestionError,
    IngestionRun,
    IngestionStatus,
    Measured,
    ResolutionOutcome,
    RowRole,
    SourceLocator,
    SourceReliability,
    SourceType,
    UniversalArtifact,
    content_hash,
    compute_state_version,
    normalize_text,
)
from app.services.orbit.contracts import _utcnow
from app.services.orbit.entities import EntityResolver, EntityStore
from app.services.orbit.ingestion.classification import ArtifactClassification, classify_artifact
from app.services.orbit.ingestion.documents import ExtractedDocument, extract_document
from app.services.orbit.ingestion.idempotency import (
    ArtifactIdentity,
    IdempotencyDecision,
    artifact_identity,
    decide_ingestion,
)
from app.services.orbit.ingestion.loaders import LoadedArtifact, load_artifact
from app.services.orbit.normalize.currency import (
    NormalizedMoney,
    detect_currency,
    normalize_money,
)
from app.services.orbit.normalize.time import normalize_time
from app.services.orbit.normalize.units import dimension_of
from app.services.orbit.semantics import (
    ArtifactColumnMap,
    ColumnMappingStatus,
    classify_rows,
    map_columns,
)
from app.services.orbit.semantics.vocabulary import DATE_ROLES, is_currency_role, ALL_ROLES


# ─────────────────────────────────────────────────────────────────────────────
# Canonical ingestion result (§4)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CanonicalIngestionResult:
    """The only shape an ingestion entry point returns.

    No entry point returns an ad-hoc dictionary of rows. This carries the canonical
    facts, the identifiers needed to trace them, and an honest account of what
    could not be determined.
    """

    run_id: UUID
    business_id: Optional[UUID]
    artifact: UniversalArtifact
    classification: ArtifactClassification

    state_version_before: Optional[str] = None
    state_version_after: Optional[str] = None

    records_seen: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    records_ambiguous: int = 0

    evidence: tuple[Evidence, ...] = ()
    entities: tuple[Any, ...] = ()
    events: tuple[BusinessEvent, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    resolutions: tuple[EntityResolution, ...] = ()
    column_map: Optional[ArtifactColumnMap] = None
    document: Optional[ExtractedDocument] = None
    quality: Optional[DataQualityReport] = None
    profile: Optional[Any] = None
    context: Optional[BusinessContext] = None

    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    jev_calls: tuple[Any, ...] = ()
    status: IngestionStatus = IngestionStatus.COMPLETED

    @property
    def artifact_id(self) -> UUID:
        return self.artifact.artifact_id

    @property
    def run(self) -> IngestionRun:
        return IngestionRun(
            run_id=self.run_id,
            business_id=self.business_id,
            artifact_ids=[self.artifact.artifact_id],
            completed_at=_utcnow(),
            status=self.status,
            records_seen=self.records_seen,
            records_accepted=self.records_accepted,
            records_rejected=self.records_rejected,
            records_ambiguous=self.records_ambiguous,
            conflicts_detected=len(self.conflicts),
            warnings=list(self.warnings),
            errors=list(self.errors),
            state_version_before=self.state_version_before,
            state_version_after=self.state_version_after,
        )

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(e.evidence_id for e in self.evidence)

    @property
    def entity_ids(self) -> tuple[str, ...]:
        return tuple(e.entity_id for e in self.entities)

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(e.event_id for e in self.events)

    @property
    def conflict_ids(self) -> tuple[str, ...]:
        return tuple(c.conflict_id for c in self.conflicts)

    @property
    def succeeded(self) -> bool:
        return self.status in (IngestionStatus.COMPLETED, IngestionStatus.NEEDS_REVIEW)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "business_id": str(self.business_id) if self.business_id else None,
            "artifact_id": str(self.artifact_id),
            "content_hash": self.artifact.content_hash,
            "status": self.status.value,
            "state_version_before": self.state_version_before,
            "state_version_after": self.state_version_after,
            "classification": self.classification.to_dict(),
            "records_seen": self.records_seen,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "records_ambiguous": self.records_ambiguous,
            "evidence_ids": list(self.evidence_ids),
            "entity_ids": list(self.entity_ids),
            "event_ids": list(self.event_ids),
            "conflict_ids": list(self.conflict_ids),
            "column_map": self.column_map.to_dict() if self.column_map else None,
            "quality": self.quality.to_dict() if self.quality else None,
            "context": self.context.to_dict() if self.context else None,
            "limitations": list(self.limitations),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "jev_calls": [
                call.to_dict() if hasattr(call, "to_dict") else dict(call)
                for call in self.jev_calls
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Row reading
# ─────────────────────────────────────────────────────────────────────────────

#: Which row roles describe which event, per artifact kind.
_EVENT_FOR_ARTIFACT: dict[str, BusinessEventType] = {
    "pos_export": BusinessEventType.SALE,
    "invoice": BusinessEventType.INVOICE,
    "purchase_order": BusinessEventType.PURCHASE_ORDER,
    "supplier_quote": BusinessEventType.INVOICE,
    "bank_statement": BusinessEventType.PAYMENT,
    # A stock listing is an observation of stock on hand, not a movement. Reading it
    # as a receipt would add every counted unit to inventory a second time.
    "inventory_export": BusinessEventType.STOCK_OBSERVATION,
    "staff_schedule": BusinessEventType.SHIFT,
    "marketing_report": BusinessEventType.CAMPAIGN,
}

#: Artifact kinds whose rows are point-in-time observations, not transactions.
_STOCK_KINDS = frozenset({"inventory_export"})

#: Semantic role -> the entity kind it identifies.
_ROLE_ENTITY_KIND: dict[str, EntityKind] = {
    "product_name": EntityKind.PRODUCT,
    "sku": EntityKind.PRODUCT,
    "supplier_name": EntityKind.SUPPLIER,
    "customer_name": EntityKind.CUSTOMER,
    "customer_phone": EntityKind.CUSTOMER,
    "customer_email": EntityKind.CUSTOMER,
    "employee_name": EntityKind.EMPLOYEE,
    "branch_name": EntityKind.BRANCH,
    "location_name": EntityKind.LOCATION,
    "category": EntityKind.CATEGORY,
    "channel": EntityKind.CHANNEL,
}

def _is_stock_kind(artifact_kind: Optional[str]) -> bool:
    return artifact_kind in _STOCK_KINDS


def _deterministic_artifact_id(digest: str, business_id: Any) -> UUID:
    """A stable UUID for an artifact's content within one business.

    Derived from the content hash and business scope, so the same bytes always
    produce the same artifact id — which is what makes reprocessing idempotent and
    lets two different transports converge on identical evidence ids.
    """
    return UUID(content_hash(str(business_id), digest)[:32])


def _sheet_of(loaded: LoadedArtifact):
    """The sheet whose contents this pipeline reads.

    Multi-sheet workbooks are ingested one sheet at a time by the caller; within a
    single artifact the first sheet is the primary one, matching the loader's own
    ``primary_sheet`` ordering.
    """
    return loaded.primary_sheet


#: Roles that hold a human-readable name. These supply an entity's canonical name.
_NAME_ROLES = (
    "product_name", "supplier_name", "customer_name", "employee_name",
    "branch_name", "location_name", "campaign_name", "category", "channel",
    "notes",
)

#: Roles that hold a stable identifier. These are identifiers, never names.
_IDENTIFIER_ROLES = ("sku", "barcode", "customer_phone", "customer_email")


def _pick(
    values: Mapping[str, Any],
    evidence_by_role: Mapping[str, str],
    *roles: str,
) -> tuple[Any, str]:
    """First present value among ``roles``, with the evidence id *of that role*.

    Looking the evidence up under the first role while reading the value from a
    fallback role produces a fact with no provenance, which the contract correctly
    refuses. Resolving the role and its evidence together removes that trap.
    """
    for role in roles:
        if values.get(role) is not None:
            return values[role], evidence_by_role.get(role, "")
    return None, ""


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Parse a numeric cell. Returns ``None`` rather than 0 for bad input."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace(",", "").replace("،", "").replace(" ", "")
    for sym in ("SAR", "USD", "EUR", "AED", "ر.س", "ريال", "$", "€", "£"):
        cleaned = cleaned.replace(sym, "")
    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    if negative:
        parsed = -parsed
    return parsed


def _measured(
    value: Any,
    *,
    evidence_id: Optional[str] = None,
    confidence: float = 0.0,
) -> Measured:
    """Wrap a raw cell as a :class:`Measured`, preserving absence.

    A blank or unparseable cell yields an *absent* measurement with a reason, never
    a zero. Zero is a real business fact and must be stated deliberately.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return Measured.missing()
    parsed = _to_decimal(value)
    if parsed is None:
        # Unparseable: absent, not zero. The raw text is discarded here because
        # the evidence record already carries it verbatim.
        return Measured.missing()
    if evidence_id is None:
        return Measured.present(parsed)
    return Measured.present(parsed, evidence_ids=(evidence_id,))


def _cell(row: Sequence[Any], index: int) -> Any:
    return row[index] if 0 <= index < len(row) else None


@dataclass
class _IngestContext:
    """Accumulated state for one pipeline invocation."""

    business_id: Optional[UUID]
    registry: EvidenceRegistry = field(default_factory=EvidenceRegistry)
    resolver: EntityResolver | None = None
    entities: dict[str, Any] = field(default_factory=dict)
    events: list[BusinessEvent] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    resolutions: list[EntityResolution] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    seen: int = 0
    accepted: int = 0
    rejected: int = 0
    ambiguous: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# The pipeline
# ─────────────────────────────────────────────────────────────────────────────

class CanonicalOrbitIngestionPipeline:
    """The one entry point for ingesting a business artifact.

    Construct once per business (the resolver and entity store are per-business by
    construction, which is what keeps tenants isolated), then call
    :meth:`ingest` for every artifact regardless of transport.
    """

    def __init__(
        self,
        *,
        business_id: Optional[UUID] = None,
        timezone_name: str = "Asia/Riyadh",
        store: Optional[EntityStore] = None,
        jev: Optional[Any] = None,
        strict_currency: bool = True,
        seed_entities: Sequence[Any] = (),
        seed_events: Sequence[BusinessEvent] = (),
        seed_evidence: Sequence[Evidence] = (),
        seed_artifact_hashes: Sequence[str] = (),
        seed_artifact_ids: Sequence[UUID] = (),
        prior_state_version: Optional[str] = None,
    ) -> None:
        self.business_id = business_id
        self.timezone_name = timezone_name
        # EntityStore defines ``__len__``, so an empty store is falsy. ``or`` here would
        # silently discard a caller-supplied store and create a second one.
        self.store = store if store is not None else EntityStore(business_id=business_id)
        self.resolver = EntityResolver(self.store)
        if jev is None:
            from app.services.jev import JevService
            jev = JevService()
        self.jev = jev
        self.strict_currency = strict_currency
        self._accumulated_events: list[BusinessEvent] = list(seed_events)
        self._accumulated_evidence: list[Evidence] = list(seed_evidence)
        self._currencies: set[str] = set()
        self._accumulated_artifact_hashes: list[str] = list(dict.fromkeys(str(h) for h in seed_artifact_hashes if h))
        self._accumulated_artifact_ids: list[UUID] = list(dict.fromkeys(seed_artifact_ids))
        self._prior_state_version: Optional[str] = prior_state_version
        for seeded in seed_entities:
            self.store.register(seeded)

    def _apply_column_judgment(
        self,
        column_map: ArtifactColumnMap,
    ) -> ArtifactColumnMap:
        """Use bounded Jev only for ambiguous column roles."""
        if self.jev is None:
            return column_map
        from dataclasses import replace
        rewritten = list(column_map.mappings)
        for index, mapping in enumerate(rewritten):
            candidates = tuple(dict.fromkeys(
                c.role for c in mapping.candidates if getattr(c, "role", None)
            ))
            if not candidates or len(candidates) <= 1:
                continue
            decision = self.jev.decide_column_role(
                candidates=candidates,
                header=mapping.raw_header,
            )
            choice = str(getattr(decision, "choice", "") or "").lower()
            if choice in {c.lower() for c in candidates} and getattr(decision, "origin", "") == "jev":
                selected = next(c for c in candidates if c.lower() == choice)
                rewritten[index] = replace(
                    mapping,
                    selected_role=selected,
                    confidence=max(mapping.confidence, float(getattr(decision, "confidence", 0.0))),
                    origin=__import__("app.services.orbit.contracts", fromlist=["DecisionOrigin"]).DecisionOrigin.JEV,
                    notes=tuple(mapping.notes) + ("bounded Jev disambiguation",),
                )
        return replace(column_map, mappings=tuple(rewritten))

    # ── public API ───────────────────────────────────────────────────────────

    def ingest(
        self,
        content: bytes,
        *,
        source_name: str = "artifact",
        source_type: SourceType = SourceType.FILE,
        mime_type: Optional[str] = None,
        known_artifacts: Optional[Mapping[tuple[Optional[str], str], str]] = None,
        state_version_before: Optional[str] = None,
        column_mapping_override: Optional[Mapping[str, str]] = None,
    ) -> CanonicalIngestionResult:
        """Ingest one artifact and return the canonical result."""
        ctx = _IngestContext(business_id=self.business_id)
        ctx.resolver = self.resolver
        run = IngestionRun(business_id=self.business_id, status=IngestionStatus.RECEIVED)
        run.state_version_before = state_version_before

        # 1-4. Validate, hash, idempotency.
        artifact_type_hint = self._format_of(source_name)
        identity = artifact_identity(content, artifact_type_hint)
        decision = decide_ingestion(
            identity,
            business_id=str(self.business_id) if self.business_id else None,
            known_artifacts=known_artifacts or {},
        )
        if not decision.should_ingest:
            ctx.warnings.append(
                f"artifact already ingested as {decision.existing_artifact_id}; "
                "no duplicate canonical facts created"
            )

        if identity.content_hash not in self._accumulated_artifact_hashes:
            self._accumulated_artifact_hashes.append(identity.content_hash)
        if not any(a == _deterministic_artifact_id(identity.content_hash, self.business_id) for a in self._accumulated_artifact_ids):
            self._accumulated_artifact_ids.append(_deterministic_artifact_id(identity.content_hash, self.business_id))

        # Artifact identity is content-addressed, not random. A random UUID would make
        # the same bytes produce different artifact and evidence ids depending on
        # which transport delivered them, which would defeat the convergence
        # requirement: identical content must yield identical canonical state.
        artifact = UniversalArtifact(
            artifact_id=_deterministic_artifact_id(
                identity.content_hash, self.business_id
            ),
            business_id=self.business_id,
            ingestion_run_id=run.run_id,
            source_type=source_type,
            source_name=source_name,
            mime_type=mime_type,
            artifact_type=artifact_type_hint,
            content_hash=identity.content_hash,
            size_bytes=identity.size_bytes,
            status=IngestionStatus.RECEIVED,
            timezone=self.timezone_name,
        )

        # 5-7. Classify, extract, register evidence.
        loaded: Optional[LoadedArtifact] = None
        document: Optional[ExtractedDocument] = None
        try:
            if artifact_type_hint in (ArtifactType.PDF, ArtifactType.DOCX, ArtifactType.TEXT):
                document = self._ingest_document(content, source_name, ctx, artifact)
                classification = self._classify(
                    source_name, content, document=document, ctx=ctx
                )
            else:
                loaded = load_artifact(content, source_name)
                document = None
                classification = self._classify(
                    source_name, content, loaded=loaded, ctx=ctx
                )
        except IngestionError as exc:
            run.status = IngestionStatus.FAILED
            run.record_error(exc)
            return CanonicalIngestionResult(
                run_id=run.run_id,
                business_id=self.business_id,
                artifact=artifact.with_status(IngestionStatus.FAILED),
                classification=ArtifactClassification(),
                errors=run.errors,
                warnings=run.warnings,
                limitations=ctx.limitations,
                status=IngestionStatus.FAILED,
            )

        # 8-19. Semantics, rows, entities, normalization, events, state.
        column_map: Optional[ArtifactColumnMap] = None
        if loaded is not None:
            column_map = map_columns(
                _sheet_of(loaded).headers,
                rows=_sheet_of(loaded).rows,
                artifact_hint=classification.artifact_kind,
            )

            # Merchant-confirmed mappings are hints to the canonical mapper, not a
            # bypass around it. Accept both API shapes (role -> raw header and raw
            # header -> role), preserving the canonical ColumnMapping contract.
            if column_mapping_override:
                from dataclasses import replace
                override = dict(column_mapping_override)
                rewritten = []
                for mapping in column_map.mappings:
                    role = mapping.selected_role
                    if mapping.raw_header in override:
                        role = override[mapping.raw_header]
                    for k, v in override.items():
                        if v == mapping.raw_header and k in {r.canonical_name for r in ALL_ROLES}:
                            role = k
                    rewritten.append(
                        replace(
                            mapping,
                            selected_role=role,
                            confidence=max(mapping.confidence, 0.99) if role != mapping.selected_role else mapping.confidence,
                            notes=tuple(mapping.notes) + (("merchant-confirmed mapping",) if role != mapping.selected_role else ()),
                        )
                    )
                column_map = replace(column_map, mappings=tuple(rewritten))
            column_map = self._apply_column_judgment(column_map)

            # Always classify again after semantic mapping. The first pass only has
            # format/filename evidence; a filename such as "pos_export.csv" is a
            # useful prior but is not authoritative. Once canonical roles are known,
            # content must be allowed to replace a weak filename-only classification.
            # This also prevents a known filename hint from locking the pipeline in
            # NEEDS_REVIEW before the actual columns are inspected.
            classification = self._classify(
                source_name, content, loaded=loaded, ctx=ctx,
                mapped_roles=column_map.roles,
            )
            if classification.artifact_kind:
                column_map = map_columns(
                    _sheet_of(loaded).headers,
                    rows=_sheet_of(loaded).rows,
                    artifact_hint=classification.artifact_kind,
                )
                if column_mapping_override:
                    column_map = self._apply_column_judgment(column_map)

            self._ingest_rows(loaded, column_map, classification, ctx, artifact)
        elif document is not None:
            self._ingest_document_facts(document, classification, ctx, artifact)

        # The entity store is the business-wide index resolved so far. ``ctx.entities``
        # holds only this artifact's resolutions, so using it would make the
        # context shrink every time an unrelated file arrived.
        entity_list = tuple(self.store.all())

        # The context describes the business, so it is built from everything this
        # pipeline has ingested, not only from the artifact just processed.
        for event in ctx.events:
            if not any(e.row_hash == event.row_hash for e in self._accumulated_events):
                self._accumulated_events.append(event)
        all_events_raw = list(self._accumulated_events)
        evidence_by_hash = {e.hash: e for e in self._accumulated_evidence}
        for evidence in ctx.registry.all():
            evidence_by_hash.setdefault(evidence.hash, evidence)
        self._accumulated_evidence = list(evidence_by_hash.values())

        # State version derived from content, so re-ingestion is idempotent.
        state_version_after = compute_state_version(
            self.business_id,
            self._accumulated_artifact_hashes,
            [e.entity_id for e in entity_list],
            [e.row_hash for e in all_events_raw],
        )
        run.state_version_after = state_version_after

        from app.services.orbit.conflicts import detect_conflicts
        from app.services.orbit.context import build_business_context
        from app.services.orbit.events import build_events
        from app.services.orbit.profile import build_business_profile
        from app.services.orbit.quality import assess_quality
        from app.services.orbit.state import build_canonical_state

        conflicts = detect_conflicts(all_events_raw, ctx.registry)
        from app.services.orbit.conflicts import classify_ambiguous_conflict
        conflicts = tuple(classify_ambiguous_conflict(c, self.jev) for c in conflicts)
        events = build_events(all_events_raw)
        profile = build_business_profile(
            entity_list, events, classification, currencies=tuple(sorted(self._currencies))
        )
        quality = assess_quality(
            business_id=self.business_id,
            artifact=artifact,
            column_map=column_map,
            records_seen=ctx.seen,
            records_accepted=ctx.accepted,
            records_rejected=ctx.rejected,
            records_ambiguous=ctx.ambiguous,
            events=events,
            conflicts=conflicts,
            resolutions=ctx.resolutions,
            registry=ctx.registry,
        )
        state = build_canonical_state(
            business_id=self.business_id,
            entities=entity_list,
            events=events,
            conflicts=conflicts,
            profile=profile,
            quality=quality,
            artifact=artifact,
            registry=ctx.registry,
            previous_state_version=self._prior_state_version,
            artifact_ids=tuple(self._accumulated_artifact_ids),
            artifact_content_hashes=tuple(self._accumulated_artifact_hashes),
            ingestion_run_ids=(run.run_id,),
        )
        self._prior_state_version = state.state_version
        context = build_business_context(state, profile, quality, ctx.registry)

        status = IngestionStatus.COMPLETED
        if quality is not None and quality.critical_issues:
            status = IngestionStatus.NEEDS_REVIEW
        elif classification.needs_review or ctx.ambiguous:
            status = IngestionStatus.NEEDS_REVIEW

        return CanonicalIngestionResult(
            run_id=run.run_id,
            business_id=self.business_id,
            artifact=artifact.with_status(status, artifact_type=classification.artifact_type),
            classification=classification,
            state_version_before=state_version_before,
            state_version_after=state_version_after,
            records_seen=ctx.seen,
            records_accepted=ctx.accepted,
            records_rejected=ctx.rejected,
            records_ambiguous=ctx.ambiguous,
            evidence=tuple(self._accumulated_evidence),
            entities=entity_list,
            events=events,
            conflicts=conflicts,
            resolutions=tuple(ctx.resolutions),
            column_map=column_map,
            document=document,
            quality=quality,
            profile=profile,
            context=context,
            limitations=tuple(dict.fromkeys(ctx.limitations)),
            warnings=tuple(dict.fromkeys(ctx.warnings)),
            errors=tuple(ctx.errors),
            jev_calls=tuple(getattr(self.jev, "calls", ())),
            status=status,
        )

    # ── steps ────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_of(source_name: str) -> ArtifactType:
        from app.services.orbit.ingestion.classification import detect_format

        return detect_format(b"", source_name) or ArtifactType.UNKNOWN

    def _classify(
        self,
        source_name: str,
        content: bytes,
        *,
        loaded: Optional[LoadedArtifact] = None,
        document: Optional[ExtractedDocument] = None,
        ctx: Optional[_IngestContext] = None,
        mapped_roles: Sequence[str] = (),
    ) -> ArtifactClassification:
        return classify_artifact(
            filename=source_name,
            content=content,
            sheet_names=tuple(s.name for s in loaded.sheets) if loaded else (),
            headers=tuple(_sheet_of(loaded).headers) if loaded else (),
            mapped_roles=mapped_roles,
            document_text=(document.text if document else None),
            jev=self.jev,
        )

    def _register_evidence(
        self,
        ctx: _IngestContext,
        artifact: UniversalArtifact,
        *,
        raw_value: Any,
        normalized_value: Any,
        role: Optional[str],
        locator: SourceLocator,
        confidence: float,
        method: ExtractionMethod,
    ) -> str:
        """Register one piece of evidence and return its id.

        Evidence without a raw value is not registered: a fact with no provenance
        cannot become canonical state.
        """
        if raw_value is None or str(raw_value).strip() == "":
            return ""
        evidence = Evidence(
            artifact_id=artifact.artifact_id,
            business_id=self.business_id,
            source_type=artifact.source_type,
            source_locator=locator,
            raw_value=str(raw_value)[:500],
            normalized_value=None if normalized_value is None else str(normalized_value)[:500],
            semantic_role=role,
            observed_at=artifact.observed_at,
            confidence=confidence,
            extraction_method=method,
        )
        recorded, _created = ctx.registry.register(evidence)
        return recorded.evidence_id

    def _resolve_entity(
        self,
        ctx: _IngestContext,
        kind: EntityKind,
        *,
        name: Optional[str],
        identifiers: Optional[Mapping[str, str]] = None,
        evidence_ids: Sequence[str] = (),
    ) -> Optional[Any]:
        if not name and not identifiers:
            return None
        entity, resolution, _created = self.resolver.resolve_or_create(
            kind, name=name, identifiers=identifiers, evidence_ids=evidence_ids, jev=self.jev
        )
        ctx.resolutions.append(resolution)
        if resolution.outcome is ResolutionOutcome.AMBIGUOUS:
            ctx.ambiguous += 1
            ctx.warnings.append(
                f"ambiguous {kind.value} reference {name!r}; not merged: {resolution.note}"
            )
            return entity
        if entity is not None:
            ctx.entities.setdefault(entity.entity_id, entity)
        return entity

    def _ingest_rows(
        self,
        loaded: LoadedArtifact,
        column_map: ArtifactColumnMap,
        classification: ArtifactClassification,
        ctx: _IngestContext,
        artifact: UniversalArtifact,
    ) -> None:
        """Turn mapped rows into evidence, entities and events."""
        role_to_header = column_map.role_to_header
        if not role_to_header:
            ctx.warnings.append(
                "no column could be mapped to a canonical role; nothing ingested"
            )
            ctx.limitations.append(
                f"{artifact.source_name}: no mappable columns, so no facts were produced"
            )
            return

        for ambiguous in column_map.ambiguous_headers:
            ctx.ambiguous += 1
            ctx.warnings.append(
                f"column {ambiguous!r} is ambiguous: "
                f"{[c.role for c in column_map.by_raw_header[ambiguous].candidates[:3]]}"
            )

        for role, (kept, discarded) in column_map.role_collisions.items():
            ctx.warnings.append(
                f"columns {kept!r} and {discarded!r} both mapped to role {role!r}; "
                f"{kept!r} was used and {discarded!r} was not ingested"
            )

        method = (
            ExtractionMethod.SPREADSHEET_CELL
            if loaded.kind in ("xlsx", "xls")
            else ExtractionMethod.CSV_FIELD
        )

        sheet = _sheet_of(loaded)
        rows: Sequence[Sequence[Any]] = sheet.rows
        sheet_name: Optional[str] = sheet.name

        event_type = _EVENT_FOR_ARTIFACT.get(
            classification.artifact_kind or "", BusinessEventType.UNKNOWN
        )
        is_stock = classification.artifact_kind in _STOCK_KINDS

        report = classify_rows(rows, mapped_roles=role_to_header)
        for note in report.notes:
            ctx.warnings.append(note)
        if report.suspicious_totals:
            ctx.warnings.append(
                "a row labelled as a total does not reconcile with the rows above it"
            )

        column_index = {header: idx for idx, header in enumerate(_sheet_of(loaded).headers)}

        for row_index in report.data_rows:
            ctx.seen += 1
            row = rows[row_index]
            locator = SourceLocator(
                sheet=sheet_name, row=row_index + 1, locator=f"row {row_index + 1}"
            )

            # Currency is a property of the source, so it is collected from the
            # cells themselves while they are in hand. The lookup goes role ->
            # header -> index, because ``column_index`` is keyed by header.
            for role in ("sale_amount", "purchase_amount", "payment_amount",
                         "expense_amount", "unit_price", "cost", "ad_spend"):
                header = column_map.role_to_header.get(role)
                if header is None:
                    continue
                detected = detect_currency(_cell(row, column_index.get(header, -1)))
                if detected:
                    self._currencies.add(detected)

            values: dict[str, Any] = {}
            evidence_by_role: dict[str, str] = {}
            for role, header in role_to_header.items():
                raw = _cell(row, column_index.get(header, -1))
                values[role] = raw
                confidence = column_map.confidence_for(role)
                ev_id = self._register_evidence(
                    ctx, artifact, raw_value=raw, normalized_value=raw, role=role,
                    locator=locator, confidence=confidence, method=method,
                )
                if ev_id:
                    evidence_by_role[role] = ev_id

            event = self._build_event(
                ctx, artifact, values, evidence_by_role, locator,
                event_type, is_stock, classification, column_map,
            )
            if event is None:
                ctx.rejected += 1
                continue

            # A repeated row_hash is the same observation, not a new fact.
            if any(existing.row_hash == event.row_hash for existing in ctx.events):
                ctx.rejected += 1
                ctx.warnings.append(
                    f"row {row_index + 1} duplicated an earlier observation "
                    "and was not added twice"
                )
                continue

            ctx.events.append(event)
            ctx.accepted += 1

    def _build_event(
        self,
        ctx: _IngestContext,
        artifact: UniversalArtifact,
        values: Mapping[str, Any],
        evidence_by_role: Mapping[str, str],
        locator: SourceLocator,
        event_type: BusinessEventType,
        is_stock: bool,
        classification: ArtifactClassification,
        column_map: Optional[ArtifactColumnMap],
    ) -> Optional[BusinessEvent]:
        """Build one event, or return ``None`` when the row carries no fact."""
        product_name = values.get("product_name")
        if product_name is None and not any(
            values.get(r) for r in ("payment_amount", "sale_amount", "employee_name",
                                   "campaign_name", "stock")
        ):
            return None

        entity_refs: dict[str, str] = {}
        # One entity per *kind* per row. Resolving ``product_name`` and ``sku``
        # separately created two product entities for every line, which then
        # disagreed with each other and produced spurious conflicts.
        for kind in EntityKind:
            roles_for_kind = [
                role for role, mapped_kind in _ROLE_ENTITY_KIND.items() if mapped_kind is kind
            ]
            present = [r for r in roles_for_kind if values.get(r) not in (None, "")]
            if not present:
                continue

            # The entity is *named* by its human-readable name and *identified* by
            # its SKU/barcode. Naming it by the SKU would make every product called
            # "P330" in canonical state, which is unreadable and loses the only
            # label a merchant recognises.
            name_role = next(
                (r for r in _NAME_ROLES if r in present and kind.value in _ROLE_ENTITY_KIND
                 and _ROLE_ENTITY_KIND[r] is kind),
                None,
            )
            if name_role is None:
                name_role = present[0]
            name = str(values[name_role])
            identifiers: dict[str, str] = {
                r: str(values[r]) for r in present if r in _IDENTIFIER_ROLES
            }

            ev_ids = [evidence_by_role[r] for r in present if evidence_by_role.get(r)]
            entity = self._resolve_entity(
                ctx, kind, name=name, identifiers=identifiers,
                evidence_ids=[e for e in ev_ids if e],
            )
            if entity is not None:
                entity_refs[kind.value] = entity.entity_id

        event_time = None
        date_role = next(
            (r for r in ("date", "shift_date", "period_start") if values.get(r)), None
        )
        if date_role:
            normalized = normalize_time(values[date_role], normalize_timezone=self.timezone_name)
            if normalized.value is None:
                ctx.warnings.append(
                    f"unparseable {date_role} {values[date_role]!r} at {locator.locator}; "
                    "the event is stored without a date"
                )
            event_time = normalized.value

        # The role that actually supplies the quantity must be known before its evidence
        # is looked up: an inventory sheet has no ``quantity`` column at all and
        # falls back to ``stock``, and pairing the fallback value with the absent
        # role's evidence id would produce an unprovenanced fact.
        preferred_quantity_role = (
            "purchase_quantity"
            if classification.artifact_kind in ("purchase_order", "supplier_quote")
            else "quantity"
        )
        quantity_value, quantity_evidence = _pick(
            values, evidence_by_role, preferred_quantity_role, "stock"
        )
        quantity = _measured(quantity_value, evidence_id=quantity_evidence)
        amount_role = next(
            (r for r in ("sale_amount", "purchase_amount", "payment_amount",
                         "expense_amount", "ad_spend", "amount", "tax_amount")
             if values.get(r) is not None),
            None,
        )
        amount_value, amount_evidence = (
            (values.get(amount_role), evidence_by_role.get(amount_role or "", ""))
            if amount_role else (None, "")
        )
        amount = _measured(amount_value, evidence_id=amount_evidence)
        unit_price_value, unit_price_evidence = _pick(
            values, evidence_by_role, "unit_price"
        )
        unit_price = _measured(unit_price_value, evidence_id=unit_price_evidence)
        # Cost is read from its own role only. Falling back to the sell price here
        # would make every dataset without cost evidence report a margin of zero.
        cost_value, cost_evidence = _pick(values, evidence_by_role, "cost")
        cost = _measured(cost_value, evidence_id=cost_evidence)
        if amount.value is None and unit_price.value is not None and quantity.value is not None:
            # Derived, and marked as such so it is never mistaken for a source fact.
            amount = Measured.present(
                unit_price.value * quantity.value,
                evidence_ids=tuple(
                    e for e in (unit_price_evidence, quantity_evidence) if e
                ),
            ) if (unit_price_evidence or quantity_evidence) else amount

        location_ref = entity_refs.get(EntityKind.BRANCH.value) or entity_refs.get(
            EntityKind.LOCATION.value
        )

        # Event confidence is bounded below by the weakest mapped column it relies
        # on, so a fact built from a 0.5-confidence column is never reported at
        # full confidence.
        confidences = [
            column_map.confidence_for(r) for r in values if column_map.confidence_for(r) > 0
        ]
        confidence = round(min(confidences), 4) if confidences else 0.5
        external_reference = values.get("transaction_id")

        event = BusinessEvent(
            business_id=self.business_id,
            event_type=event_type,
            event_time=event_time,
            business_local_date=event_time.date() if event_time else None,
            timezone=self.timezone_name,
            entity_refs=dict(entity_refs),
            quantity=quantity,
            amount=amount,
            unit_price=unit_price,
            cost=cost,
            location_ref=location_ref,
            source_type=artifact.source_type,
            source_locator=locator,
            evidence_ids=tuple(sorted(set(v for v in evidence_by_role.values() if v))),
            confidence=confidence,
            external_reference=(
                str(external_reference) if external_reference is not None else None
            ),
        )
        return event

    def _ingest_document(
        self,
        content: bytes,
        source_name: str,
        ctx: _IngestContext,
        artifact: UniversalArtifact,
    ) -> Optional[ExtractedDocument]:
        document = extract_document(content, source_name)
        for limitation in document.limitations:
            ctx.limitations.append(f"{source_name}: {limitation}")
        for table_index, table in enumerate(document.tables):
            for row_index, row in enumerate(table.rows):
                ctx.seen += 1
                method = ExtractionMethod.DOCUMENT_TABLE
                locator = SourceLocator(
                    page=None, table=table_index, row=row_index + 1,
                    locator=f"table {table_index} row {row_index + 1}",
                )
                produced = False
                for value in row:
                    ev_id = self._register_evidence(
                        ctx, artifact, raw_value=value, normalized_value=value,
                        role=None, locator=locator, confidence=0.9, method=method,
                    )
                    if ev_id:
                        produced = True
                if produced:
                    ctx.accepted += 1
                else:
                    ctx.rejected += 1
        return document

    def _ingest_document_facts(
        self,
        document: ExtractedDocument,
        classification: ArtifactClassification,
        ctx: _IngestContext,
        artifact: UniversalArtifact,
    ) -> None:
        """Turn extracted document fields into evidence and, where clear, an event."""
        if document.is_empty:
            ctx.limitations.append(
                f"{artifact.source_name}: no text could be extracted, so no fields were read"
            )
            return
        evidence_ids: list[str] = []
        for field in document.fields:
            locator = field.locator
            ev_id = self._register_evidence(
                ctx, artifact, raw_value=field.raw_value,
                normalized_value=field.normalized_value, role=field.field_name,
                locator=locator, confidence=field.confidence,
                method=ExtractionMethod.DOCUMENT_TEXT,
            )
            if ev_id:
                evidence_ids.append(ev_id)
            ctx.seen += 1
            if ev_id:
                ctx.accepted += 1

        # A document only becomes an event when it states an amount and a date.
        amount_field = next(
            (f for f in document.fields if f.field_name in
             ("total", "subtotal", "sale_amount", "purchase_amount") and f.is_amount is not None),
            None,
        )
        date_field = next((f for f in document.fields if f.field_name.endswith("date")), None)
        if amount_field is None:
            ctx.warnings.append(
                f"{artifact.source_name}: no monetary total was extracted, so no event was created"
            )
            return

        entity_refs: dict[str, str] = {}
        for candidate in document.fields:
            kind = _ROLE_ENTITY_KIND.get(candidate.field_name)
            if kind and candidate.normalized_value:
                entity = self._resolve_entity(
                    ctx, kind, name=str(candidate.normalized_value),
                    evidence_ids=(ev_id for ev_id in evidence_ids),
                )
                if entity is not None:
                    entity_refs[kind.value] = entity.entity_id

        event_time = None
        if date_field is not None:
            normalized = normalize_time(
                date_field.raw_value, normalize_timezone=self.timezone_name
            )
            if normalized.value is None:
                ctx.warnings.append(
                    f"{artifact.source_name}: could not parse date {date_field.raw_value!r}"
                )
            event_time = normalized.value

        amount_evidence_id = self._register_evidence(
            ctx, artifact, raw_value=amount_field.raw_value,
            normalized_value=amount_field.normalized_value, role=amount_field.field_name,
            locator=amount_field.locator, confidence=amount_field.confidence,
            method=ExtractionMethod.DOCUMENT_TEXT,
        )
        if amount_evidence_id:
            evidence_ids.append(amount_evidence_id)

        money: NormalizedMoney = normalize_money(
            amount_field.normalized_value, raw_text=amount_field.raw_value
        )
        amount = (
            Measured.present(
                money.normalized_amount if money.normalized_amount is not None
                else money.source_amount,
                evidence_ids=(amount_evidence_id,) if amount_evidence_id else (),
            )
            if (money.normalized_amount is not None or money.source_amount is not None)
            else Measured.missing()
        )
        if money.source_currency is None and money.source_amount is not None:
            ctx.limitations.append(
                f"{artifact.source_name}: amount {money.source_amount} has no currency; "
                "it is not summed against other currencies"
            )

        event = BusinessEvent(
            business_id=self.business_id,
            event_type=_EVENT_FOR_ARTIFACT.get(
                classification.artifact_kind or "", BusinessEventType.INVOICE
            ),
            event_time=event_time,
            business_local_date=event_time.date() if event_time else None,
            timezone=self.timezone_name,
            entity_refs=entity_refs,
            amount=amount,
            source_type=artifact.source_type,
            source_locator=amount_field.locator,
            evidence_ids=tuple(evidence_ids),
            confidence=amount_field.confidence,
        )
        ctx.events.append(event)
        ctx.accepted += 1



# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience
# ─────────────────────────────────────────────────────────────────────────────

def ingest_artifact(
    content: bytes,
    *,
    business_id: Optional[UUID] = None,
    source_name: str = "artifact",
    source_type: SourceType = SourceType.FILE,
    mime_type: Optional[str] = None,
    pipeline: Optional[CanonicalOrbitIngestionPipeline] = None,
    state_version_before: Optional[str] = None,
) -> CanonicalIngestionResult:
    """Ingest one artifact through the canonical pipeline.

    Every entry point uses this. The transport differs; the truth model does not.
    """
    pipe = pipeline or CanonicalOrbitIngestionPipeline(business_id=business_id)
    return pipe.ingest(
        content,
        source_name=source_name,
        source_type=source_type,
        mime_type=mime_type,
        state_version_before=state_version_before,
    )


def ingest_artifacts(
    artifacts: Iterable[tuple[bytes, str]],
    *,
    business_id: Optional[UUID] = None,
    timezone_name: str = "Asia/Riyadh",
) -> tuple[CanonicalIngestionResult, ...]:
    """Ingest several artifacts sharing one entity store.

    Sharing the pipeline is what lets a POS export and an inventory sheet
    contribute to the same product entities instead of producing two disjoint sets.
    """
    pipe = CanonicalOrbitIngestionPipeline(
        business_id=business_id, timezone_name=timezone_name
    )
    return tuple(
        pipe.ingest(content, source_name=name) for content, name in artifacts
    )