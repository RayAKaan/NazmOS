"""Ingestion idempotency (spec §28).

The audit found **no ``content_hash`` field anywhere in the repository**, so there
was no content-addressed way to answer "have we already ingested this?".

This module provides that anchor. The rule is simple and absolute:

    same bytes  ->  same artifact  ->  one logical fact

Re-uploading a file must create a *new ingestion attempt* (for the audit trail)
but must **not** create a duplicate artifact or duplicate business facts.

Three levels, because they fail differently:

1. **Byte level** - identical file bytes. Same artifact, reused.
2. **Row level** - identical logical record in a different file layout. Same event,
   thanks to the deterministic ``row_hash`` on :class:`BusinessEvent`.
3. **State level** - the same set of artifacts and events must yield the same
   ``state_version``, which is why :func:`compute_state_version` is content-derived.

What this deliberately does NOT do is deduplicate *within* a file: two genuinely
distinct rows that happen to hash identically are a data-quality signal, reported
rather than silently dropped.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    ArtifactType,
    content_hash,
    deterministic_fingerprint,
)


class IdempotencyOutcome(str, Enum):
    NEW = "new"
    REUSED = "reused"          # identical artifact already known
    DUPLICATE_ROWS = "duplicate_rows"  # same rows, different artifact


@dataclass(frozen=True)
class ArtifactIdentity:
    """The content identity of an artifact."""

    content_hash: str
    size_bytes: int
    artifact_type: ArtifactType

    @classmethod
    def from_bytes(cls, content: bytes, artifact_type: ArtifactType) -> "ArtifactIdentity":
        return cls(
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            artifact_type=artifact_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "artifact_type": self.artifact_type.value,
        }


@dataclass(frozen=True)
class IdempotencyDecision:
    """What ingestion should do with this artifact."""

    outcome: IdempotencyOutcome
    content_hash: str
    #: The artifact this one should be merged into, when reused.
    existing_artifact_id: Optional[str] = None
    reason: str = ""

    @property
    def should_ingest(self) -> bool:
        return self.outcome is IdempotencyOutcome.NEW

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "content_hash": self.content_hash,
            "existing_artifact_id": self.existing_artifact_id,
            "reason": self.reason,
            "should_ingest": self.should_ingest,
        }


def artifact_identity(content: bytes, artifact_type: ArtifactType) -> ArtifactIdentity:
    """Content identity for a raw artifact."""
    return ArtifactIdentity.from_bytes(content, artifact_type)


def decide_ingestion(
    identity: ArtifactIdentity,
    *,
    business_id: Optional[str],
    known_artifacts: Mapping[tuple[Optional[str], str], str],
) -> IdempotencyDecision:
    """Decide whether to ingest or reuse, given what is already known.

    ``known_artifacts`` maps ``(business_id, content_hash) -> artifact_id``.

    The tenant is part of the lookup **key**, not a filter applied afterwards.
    That is deliberate: a flat ``content_hash -> artifact_id`` map would let a hash
    ingested by one tenant be "reused" for another, handing the second tenant the
    first tenant's artifact id. Keying by ``(business_id, content_hash)`` makes
    that structurally impossible rather than merely discouraged.

    The caller supplies the map so this module stays free of database concerns and
    is trivially testable.
    """
    if business_id is None:
        # Pre-tenant / guest upload: nothing to dedupe against yet.
        return IdempotencyDecision(
            outcome=IdempotencyOutcome.NEW,
            content_hash=identity.content_hash,
            reason="no business scope yet; recorded as a new artifact",
        )

    existing = known_artifacts.get((business_id, identity.content_hash))
    if existing is not None:
        return IdempotencyDecision(
            outcome=IdempotencyOutcome.REUSED,
            content_hash=identity.content_hash,
            existing_artifact_id=existing,
            reason=(
                "identical content already ingested for this business; "
                "reusing the existing artifact instead of duplicating it"
            ),
        )

    return IdempotencyDecision(
        outcome=IdempotencyOutcome.NEW,
        content_hash=identity.content_hash,
        reason="content not previously ingested for this business",
    )


def record_fingerprint(*parts: Any) -> str:
    """Stable fingerprint for cross-artifact duplicate detection."""
    return deterministic_fingerprint(*parts)


def rows_fingerprint(rows: Iterable[Sequence[Any]], headers: Sequence[str]) -> str:
    """Content fingerprint for a logical record set, independent of file layout.

    Two files that carry the same records in a different column order or with extra
    blank columns still hash identically, which is what lets us detect a re-upload
    that was merely reformatted.
    """
    normalized_rows = []
    for row in rows:
        pairs = []
        for idx, value in enumerate(row):
            if idx >= len(headers):
                break
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            pairs.append(f"{headers[idx].strip().lower()}={text}")
        if pairs:
            normalized_rows.append("|".join(sorted(pairs)))
    normalized_rows.sort()
    return content_hash(*normalized_rows)


def dedupe_records(
    records: Sequence[Mapping[str, Any]],
    *,
    key_fields: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into unique rows and duplicate rows.

    Duplicates are *reported*, never silently dropped: a merchant uploading the
    same row twice is a data-quality signal, and hiding it would misrepresent the
    data.
    """
    seen: dict[str, int] = {}
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for record in records:
        key = "|".join(
            str(record.get(field, "")).strip().lower() for field in key_fields
        )
        if key in seen:
            seen[key] += 1
            duplicates.append({**dict(record), "_duplicate_index": seen[key]})
            continue
        seen[key] = 1
        unique.append(dict(record))

    return unique, duplicates


def duplicate_rate(record_count: int, duplicate_count: int) -> float:
    """Fraction of duplicate records. ``None`` is impossible: 0 records -> 0.0."""
    if record_count <= 0:
        return 0.0
    return round(duplicate_count / record_count, 6)