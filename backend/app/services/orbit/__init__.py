"""Phase 1 — Universal Business Reality (Orbit).

This package is the Business Reality Layer. It turns arbitrary business
artifacts into canonical, evidence-backed business reality **without any LLM**.

Layering (import direction is enforced by a test, see
``tests/phase1/test_orbit_no_llm.py``)::

    API
      ↓
    BusinessContext              (what Phase 2 receives)
      ↓
    CanonicalBusinessState       (one authoritative state + state_version)
      ↓
    Evidence · Entities · Events · Conflicts
      ↓
    Semantic normalization
      ↓
    Ingestion

Authoritative boundaries:

* **Orbit owns truth.** Every canonical value traces to :class:`Evidence`.
* **unknown is never zero.** :class:`Measured` cannot represent "unknown" as a
  number.
* **Conflicts are recorded, never silently resolved.**
* **Determinism first.** Judgment (JEV) is consulted only for genuine ambiguity,
  and only through :mod:`app.services.jev`.
* **No LLM, no execution.** This layer never authorizes or performs an action.
"""
from app.services.orbit.contracts import (
    PHASE_1_CONTRACT_VERSION,
    ArtifactType,
    BusinessContext,
    BusinessEvent,
    BusinessEventType,
    BusinessProfile,
    BusinessType,
    CanonicalBusinessState,
    Conflict,
    ConflictRelationship,
    ConflictResolution,
    ConflictSeverity,
    ContentHashError,
    DataQualityReport,
    DecisionOrigin,
    DomainCapability,
    DomainCapabilityFlag,
    DomainFreshness,
    Entity,
    EntityKind,
    EntityResolution,
    ErrorCategory,
    Evidence,
    EvidenceRegistry,
    ExtractionMethod,
    FreshnessState,
    IngestionError,
    IngestionRun,
    IngestionStatus,
    MatchMethod,
    Measured,
    QualityDimension,
    QualityDimensionScore,
    QualityIssue,
    QualityIssueKind,
    ResolutionOutcome,
    RowRole,
    SourceLocator,
    SourceReliability,
    SourceType,
    UniversalArtifact,
    compute_state_version,
    content_hash,
    evaluate_freshness,
    normalize_identifier,
    normalize_text,
)

__all__ = [
    "PHASE_1_CONTRACT_VERSION",
    "ArtifactType",
    "BusinessContext",
    "BusinessEvent",
    "BusinessEventType",
    "BusinessProfile",
    "BusinessType",
    "CanonicalBusinessState",
    "Conflict",
    "ConflictRelationship",
    "ConflictResolution",
    "ConflictSeverity",
    "ContentHashError",
    "DataQualityReport",
    "DecisionOrigin",
    "DomainCapability",
    "DomainCapabilityFlag",
    "DomainFreshness",
    "Entity",
    "EntityKind",
    "EntityResolution",
    "ErrorCategory",
    "Evidence",
    "EvidenceRegistry",
    "ExtractionMethod",
    "FreshnessState",
    "IngestionError",
    "IngestionRun",
    "IngestionStatus",
    "MatchMethod",
    "Measured",
    "QualityDimension",
    "QualityDimensionScore",
    "QualityIssue",
    "QualityIssueKind",
    "ResolutionOutcome",
    "RowRole",
    "SourceLocator",
    "SourceReliability",
    "SourceType",
    "UniversalArtifact",
    "compute_state_version",
    "content_hash",
    "evaluate_freshness",
    "normalize_identifier",
    "normalize_text",
]