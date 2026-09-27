"""Anomaly triage persistence (Batch 2 pre-req for inventory.anomaly_triage).

MIGRATION_MATRIX Batch 2 pre-req: "persist anomalies (findings/evidence) so
there is ground truth". ``app.services.anomaly_detector.AnomalyDetector`` was
verified as orphaned (zero callers/imports/tests/persists). This module closes
the persistence gap by writing each detected anomaly to the canonical ``findings``
store through ``finding_service.create_finding`` so the surface has deterministic
ground truth before any advisory AI channel runs.

This is an OPT-IN path: it is intentionally NOT wired to any production trigger
yet (Phase 2 shadow-only posture). Callers (services, tasks, tests) must pass a
business-scoped db session; the session owner commits.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.finding_service import create_finding

_SEVERITY_BY_TYPE = {"spike": "high", "drop": "medium"}
_DETECTOR_LABEL = "anomaly_detector.zscore"


def triage_severity(anomaly_type: str) -> str:
    """Map a detector signal to the findings FindingSeverity vocabulary.
    SPIKE -> high, DROP -> medium, unknown -> medium (fail-safe)."""
    return _SEVERITY_BY_TYPE.get(anomaly_type, "medium")


async def persist_anomaly(
    db: Any,
    business_id: UUID | str,
    anomaly: dict[str, Any],
    *,
    threshold_z: float | None = None,
) -> UUID:
    """Persist one detected anomaly row as a finding. Returns the finding id."""
    a_type = anomaly.get("type", "unknown")
    evidence = dict(anomaly)
    if threshold_z is not None:
        evidence["threshold_z"] = threshold_z
    evidence["detector"] = _DETECTOR_LABEL

    return await create_finding(
        db,
        business_id,
        domain="inventory",
        category="anomaly",
        severity=triage_severity(a_type),
        title=f"Sales anomaly {a_type}: {anomaly.get('item_name', 'item')}",
        explanation=(
            f"z-score {anomaly.get('z_score')} on {anomaly.get('date')} "
            f"(observed {anomaly.get('value')}, expected {anomaly.get('expected_value')})."
        ),
        evidence=evidence,
        affected_entities=[
            {"type": "item", "id": anomaly.get("item_id"), "name": anomaly.get("item_name")}
        ],
        confidence=0.0,
        source=_DETECTOR_LABEL,
        action_risk="low",
    )


async def persist_anomalies(
    db: Any,
    business_id: UUID | str,
    anomalies: list[dict[str, Any]],
    *,
    threshold_z: float | None = None,
) -> list[UUID]:
    """Persist many detected anomaly rows; empty input yields empty list."""
    return [await persist_anomaly(db, business_id, a, threshold_z=threshold_z) for a in anomalies]


async def detect_and_persist(
    db: Any,
    business_id: UUID | str,
    item_id: str,
    item_name: str,
    daily_sales: list[dict[str, Any]],
    *,
    threshold_z: float = 2.5,
    detector: Any | None = None,
) -> list[UUID]:
    """OPT-IN consumer: run the detector, persist its output as findings.

    Detector is imported lazily so this module stays lightweight for consumers
    that only import ``persist_anomalies``. No production trigger calls this yet.
    """
    from app.services.anomaly_detector import AnomalyDetector

    det = detector or AnomalyDetector()
    anomalies = det.detect_anomalies(item_id, item_name, daily_sales, threshold_z=threshold_z)
    return await persist_anomalies(db, business_id, anomalies, threshold_z=threshold_z)