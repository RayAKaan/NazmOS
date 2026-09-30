"""Evidence registry and provenance for Orbit Financial X-Ray."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceRecord:
    """Single evidence record linking a finding/metric to source data."""
    evidence_id: str
    source_type: str  # "source_row", "calculation", "cross_column"
    source_ref: dict[str, Any]  # {file_id, row_index, column, manifest_ref}
    calculation: dict[str, Any] | None = None
    timestamp: str = ""


class EvidenceRegistry:
    """Registry of all evidence records for an Orbit audit run.

    Provides full provenance: finding -> metric -> source rows -> file
    """

    def __init__(self):
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> str:
        """Add evidence record and return its ID."""
        self._records[record.evidence_id] = record
        return record.evidence_id

    def get(self, evidence_id: str) -> Any | None:
        """Get evidence record by ID."""
        return self._records.get(evidence_id)

    def get_by_finding(self, finding_id: str) -> list:
        """Get all evidence records for a finding."""
        return [r for r in self._records.values() if finding_id in r.evidence_id or finding_id in str(r.source_ref)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            eid: {
                "evidence_id": r.evidence_id,
                "source_type": r.source_type,
                "source_ref": r.source_ref,
                "calculation": r.calculation,
                "timestamp": r.timestamp,
            }
            for eid, r in self._records.items()
        }

    def __len__(self) -> int:
        return len(self._records)