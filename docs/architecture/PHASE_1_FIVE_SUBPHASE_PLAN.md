# Phase 1 — Five Subphase Completion Plan

This branch completes Phase 1 (Universal Business Reality) from the live repository state.

## Subphase 1 — Truth-path convergence

Goal: make Orbit the only business-truth producer.

Current live work:
- authenticated upload processing enters the canonical Orbit ingestion service
- guest audit output is derived from canonical events
- Foodics and Salla translate provider payloads and call Orbit
- ETL compatibility writes are performed by CanonicalProjector
- merchant-confirmed column mappings remain inside the canonical mapper

Remaining gate:
- no active route may instantiate ETLPipeline as a parser/truth producer
- no active route may build BusinessSnapshotBuilder as an alternate truth path
- POS adapter tests must prove products/inventory/transactions are not written outside the projector
- guest/authenticated equivalent inputs must converge on identical canonical semantics

## Subphase 2 — Canonical persistence and history

Goal: make canonical state durable and cumulative.

Deliver:
- persist artifacts, evidence, entities, aliases, conflicts, quality, profile, semantic mappings, state versions and Jev calls
- rehydrate prior canonical state before a new artifact is ingested
- preserve content-addressed evidence IDs across process restarts
- preserve state version lineage across multiple uploads
- make state rebuild and reprocessing deterministic
- ensure compatibility tables remain projections only

Gate:
- upload A then upload B retains A+B state
- restart between A and B still retains A+B
- identical re-upload creates no duplicate canonical facts
- evidence and event references remain valid

## Subphase 3 — JEV boundary and security

Goal: make bounded Jev a reusable structured-judgment layer.

Deliver:
- one JevService and typed decisions
- Orbit artifact/column/row/entity/time/conflict/quality/profile/route capabilities
- deterministic-first call policy
- signed privacy-safe capsules
- exact capsule-hash lineage
- durable Jev audit records
- disagreement preservation
- JEV failure fallback
- Orbit has no LLM dependency
- active architecture has no OpenCode runtime

Gate:
- invalid Jev choices rejected
- Jev cannot execute or authorize
- PII/secrets are not sent
- no Jev key is required for deterministic-only Orbit operation

## Subphase 4 — Phase 1 product surface and operations

Goal: expose the canonical reality layer and make it reproducible.

Deliver:
- Phase 1 fixtures and golden dataset
- canonical Orbit API surface
- data quality/conflict/evidence drill-down
- universal document upload support
- Docker Desktop workflow
- health checks
- Make targets
- environment/startup validation
- minimal Orbit frontend surface

Gate:
- clean Docker environment can migrate, seed, ingest and query canonical reality
- UI values have source/timestamp/confidence lineage

## Subphase 5 — Final acceptance and CI

Goal: prove the architecture rather than relying on documentation.

Deliver:
- architecture guard tests
- tenant/IDOR/upload security tests
- migration tests
- full Phase 1 suite
- regression suite
- frontend suite
- CI fixes
- repository hygiene sweep
- completion report

Hard completion condition:
- one canonical ingestion pipeline
- ETL only projects canonical state
- no hardcoded Orbit metrics
- explicit unknown/conflict/freshness
- JEV bounded and audited
- no LLM in Orbit
- no OpenCode runtime
- Docker + CI green
