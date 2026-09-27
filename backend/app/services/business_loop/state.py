"""Versioned business state (Phase 3C) — deterministic projection of evidence.

Builds a composite, versioned representation of a business from ACCEPTED
evidence records. Rules enforced here (MASTER_PLAN §8.4):
    * missing is not zero
    * stale is not current
    * partial is not complete
    * invalid evidence can never enter authoritative state
    * a new projection never erases the ability to explain prior decisions
      (every snapshot keeps state_version + evidence lineage)

Reuse notes:
    * ``app.services.business_memory`` holds optimistic per-document `version`
      counters + ``MemoryUpdate`` audit rows; that is the durable home. This
      module is the loop-local *composite* snapshot with an explicit
      ``state_version`` across domains so recommendations/governance can bind
      to the exact state that produced them.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.business_loop.contracts import EvidenceQualityFlag
from app.services.business_loop.evidence import EvidenceRecord, EvidenceStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_version(*, business_id: str, tenant_id: str, evidence_ids: tuple[str, ...]) -> str:
    """Deterministic composite version: content-addressed, monotonic via history."""
    composite = f"{tenant_id}:{business_id}:{':'.join(sorted(evidence_ids))}"
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()[:24]


@dataclass
class DomainState:
    """One business domain (inventory, demand, margin, ...) within a snapshot."""

    domain: str
    values: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    observed_at: str = ""
    quality_flags: tuple[EvidenceQualityFlag, ...] = ()
    # missing/partial flags are explicit and separate from zero:
    missing_fields: tuple[str, ...] = ()
    stale: bool = False


@dataclass
class BusinessStateSnapshot:
    """Immutable composite view of the business at one state_version."""

    tenant_id: str
    business_id: str
    state_version: str
    schema_version: str
    created_at: str
    domains: dict[str, DomainState]
    evidence_lineage: tuple[EvidenceRecord, ...]
    quality_flags: tuple[EvidenceQualityFlag, ...]

    def domain(self, name: str) -> DomainState | None:
        return self.domains.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "business_id": self.business_id,
            "state_version": self.state_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "domains": {
                k: {
                    "values": v.values,
                    "evidence_ids": list(v.evidence_ids),
                    "observed_at": v.observed_at,
                    "quality_flags": [f.value for f in v.quality_flags],
                    "missing_fields": list(v.missing_fields),
                    "stale": v.stale,
                }
                for k, v in self.domains.items()
            },
            "quality_flags": [f.value for f in self.quality_flags],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BusinessStateSnapshot":
        """Lossless round-trip of ``to_dict`` (PHASE_4A serialize contract).

        Rehydrates the durable projection produced by ``_stage_state_projection``
        (``state_output["state"]``) so a resumed cycle can restore ``run._snapshot``
        with the REAL domains/quality flags rather than the empty-domain fallback
        ``_saved_snapshot`` would otherwise invent.
        """
        domains: dict[str, DomainState] = {}
        for name, d in (data.get("domains") or {}).items():
            domains[str(name)] = DomainState(
                domain=str(name),
                values=dict(d.get("values") or {}),
                evidence_ids=tuple(d.get("evidence_ids") or ()),
                observed_at=d.get("observed_at", ""),
                quality_flags=tuple(EvidenceQualityFlag(f) for f in d.get("quality_flags") or ()),
                missing_fields=tuple(d.get("missing_fields") or ()),
                stale=bool(d.get("stale", False)),
            )
        return cls(
            tenant_id=str(data["tenant_id"]),
            business_id=str(data["business_id"]),
            state_version=str(data.get("state_version", "")),
            schema_version=str(data.get("schema_version", "loop-v1")),
            created_at=str(data.get("created_at", "")),
            domains=domains,
            evidence_lineage=(),
            quality_flags=tuple(EvidenceQualityFlag(f) for f in data.get("quality_flags") or ()),
        )


def _is_stale(record: EvidenceRecord, now: str, max_age_days: int = 7) -> bool:
    from app.services.business_loop.evidence import freshness_flag

    return freshness_flag(record, now, max_age_days) == EvidenceQualityFlag.STALE


def project_inventory_domain(
    records: list[EvidenceRecord], now: str, *, max_age_days: int = 7
) -> DomainState:
    """Project an inventory domain from accepted inventory observations.

    Missing stock/cost/sell is recorded in ``missing_fields`` — it is NOT
    coerced to zero. Only the most recent observation per sku is folded in.
    """
    values: dict[str, Any] = {}
    evidence_ids: list[str] = []
    latest_by_sku: dict[str, tuple[EvidenceRecord, int]] = {}
    for i, r in enumerate(records):
        if r.observation_type not in ("inventory.changed", "inventory.observed"):
            continue
        sku = r.payload.get("sku")
        if not sku:
            continue
        current = latest_by_sku.get(sku)
        if current is None or i > current[1]:
            latest_by_sku[sku] = (r, i)

    missing_fields: set[str] = set()
    flags: set[EvidenceQualityFlag] = set()
    for sku, (r, _i) in latest_by_sku.items():
        entry: dict[str, Any] = {
            "observation": r.observation_type,
            "evidence_id": r.evidence_id,
        }
        for field_name in ("stock", "cost", "sell", "sku"):
            if field_name in r.payload:
                entry[field_name] = r.payload[field_name]
            elif field_name not in ("sku",):
                missing_fields.add(field_name)
        if "days_of_supply" in r.payload:
            entry["days_of_supply"] = r.payload["days_of_supply"]
        if "days_supply" in r.payload:
            entry["days_supply"] = r.payload["days_supply"]
        if _is_stale(r, now, max_age_days):
            flags.add(EvidenceQualityFlag.STALE)
        values[sku] = entry
        evidence_ids.append(r.evidence_id)

    return DomainState(
        domain="inventory",
        values=values,
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
        observed_at=now,
        quality_flags=tuple(flags),
        missing_fields=tuple(sorted(missing_fields)),
        stale=False,
    )


def project_state(
    evidence: EvidenceStore,
    *,
    tenant_id: str,
    business_id: str,
    now: str | None = None,
    domains: tuple[str, ...] = ("inventory", "demand", "margin"),
    max_age_days: int = 7,
) -> BusinessStateSnapshot:
    """Project the composite, versioned business state from accepted evidence.

    This is the ONLY way a loop stage obtains authoritative state: it consumes
    the evidence store, not ad-hoc reads.
    """
    now = now or _now_iso()
    accepted = [
        r for r in evidence.accepted()
        if r.tenant_id == tenant_id and r.business_id == business_id
    ]

    flags: set[EvidenceQualityFlag] = set()
    for r in accepted:
        flags.update(r.quality_flags)

    domain_map: dict[str, DomainState] = {}
    if "inventory" in domains:
        domain_map["inventory"] = project_inventory_domain(accepted, now, max_age_days=max_age_days)
        if domain_map["inventory"].missing_fields:
            flags.add(EvidenceQualityFlag.PARTIAL)
        if not domain_map["inventory"].values:
            flags.add(EvidenceQualityFlag.MISSING)

    evidence_ids = tuple(dict.fromkeys(r.evidence_id for r in accepted))
    return BusinessStateSnapshot(
        tenant_id=tenant_id,
        business_id=business_id,
        state_version=_state_version(
            business_id=business_id, tenant_id=tenant_id, evidence_ids=evidence_ids
        ),
        schema_version="loop-v1",
        created_at=now,
        domains=domain_map,
        evidence_lineage=tuple(accepted),
        quality_flags=tuple(dict.fromkeys(flags)),
    )


def is_stale(snapshot: BusinessStateSnapshot, now: str | None = None, max_age_days: int = 7) -> bool:
    """A snapshot is stale when insufficient FRESH evidence produced it."""
    if EvidenceQualityFlag.MISSING in snapshot.quality_flags:
        return True
    if len(snapshot.evidence_lineage) == 0:
        return True
    now = now or _now_iso()
    latest = max((r.observed_at for r in snapshot.evidence_lineage), default="")
    try:
        age_days = (datetime.fromisoformat(now) - datetime.fromisoformat(latest)).days
    except (TypeError, ValueError):
        return True
    return age_days > max_age_days


def has_missing_required_fields(snapshot: BusinessStateSnapshot, required: tuple[str, ...] = ("stock", "cost", "sell")) -> list[str]:
    """Report which required fields are missing across the inventory domain."""
    inv = snapshot.domain("inventory")
    if inv is None:
        return list(required)
    missing: set[str] = set()
    for sku_values in inv.values.values():
        for rf in required:
            if rf not in sku_values:
                missing.add(rf)
    return sorted(missing)