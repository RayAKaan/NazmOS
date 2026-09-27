# PHASE_3B — Evidence Foundation (`app/services/business_loop/evidence.py`)

> Evidence in → verified learning out. MASTER_PLAN §8. Area: evidence lifecycle, normalization, integrity.

## What was built

A DB-free, idempotent evidence ledger that standardizes raw observations into loop records with:
- **schema stamping** (`schema_version = loop-v1`) so reprojection is explicit
- **idempotency** via SHA-256 over the canonical payload — replay is a no-op
- **provenance** (source type/reference, event timestamp, ingestion timestamp)
- **validation status** (accepted | rejected | quarantined | duplicate)
- **quality flags** (fresh | stale | partial | missing | revised | conflict)

`normalize_observation` enforces the Phase A missing-fields and cross-tenant rules at the boundary: an observation missing a required field (sku/stock/cost/sell) is REJECTED (`missing_fields:...`), a payload claiming another tenant is REJECTED (`cross_tenant_rejection`). Nothing invalid silently reaches accepted evidence.

## Reuse vs parallel ledger

Per AGENTS.md and MASTER_PLAN §8, this is the loop-local normalized view **on top of** the existing `event_engine` SHA-256 checksum + `BUILTIN_EVENT_SCHEMAS` concept — it does **not** create a second durable store. The production durable home remains the `Event` tables; a thin `Event -> EvidenceRecord` adapter is documented for live wiring. `checksum_of` mirrors `event_engine` canonicalization (`sort_keys`, UTF-8-safe).

## Integrity behavior (never a silent overwrite)

| Scenario | Behavior | Evidence |
|---|---|---|
| Duplicate payload replay | returns the accepted record with FRESH flag | `test_evidence_store_duplicate_rejected_by_checksum` [V] |
| Correction of a prior record | REVISED flag + `prior_evidence_id` lineage pointer | `test_evidence_correction_preserves_prior_lineage` [V] |
| Correction referencing unknown prior | CONFLICT flag (never silently dropped) | `test_evidence_conflict_flagged_not_silently_overwritten` [V] |
| Payload missing required fields | REJECTED with reason | `test_evidence_normalize_rejects_missing_and_cross_tenant` [V] |
| Cross-tenant payload | REJECTED (`cross_tenant_rejection`) | same test [V] |
| Stale observation | STALE/MISSING quality flag, never treated as current | `test_evidence_freshness_flag` [V] |
| Canonical checksum determinism | identical digest regardless of key order | `test_evidence_idempotency_checksum_deterministic` [V] |

## Files & test coverage

- `backend/app/services/business_loop/evidence.py` (EvidenceRecord, EvidenceStore, checksum_of, freshness_flag, normalize_observation)
- `backend/tests/test_business_loop_modules.py::EvidenceFoundation` [V]

## Gaps (from PHASE_3A report)

- G-3C Evidence version watermark is present in every record (loop schema) — resolved.
- G-3K (pinned Event↔Evidence identity) remains a durable-wiring concern, not a loop-internal one; deferred to production wiring. [!]

## Status

PASS. All §8 integrity rules implemented, DB-free, deterministic. Baseline regression gate: `260 passed` (Phase 3A suite) [B].