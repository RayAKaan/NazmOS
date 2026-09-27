# PHASE_3C — Versioned Business State (`app/services/business_loop/state.py`)

> Every stage decides against an *exact, explainable business state*, never a guess. MASTER_PLAN §8.4, §19.

## What was built

A deterministic projection of accepted evidence into an immutable, versioned snapshot:

- **`BusinessStateSnapshot`** — tenant-scoped, schema-`loop-v1`, carries a composite `state_version` (SHA-256 over `tenant:business:evidence_ids`), evidence lineage, and quality flags.
- **`DomainState`** — one domain (inventory/demand/margin) with `values`, its own evidence ids, `missing_fields`, and stale/missing flags.
- **`project_state`** — the *only* stage that computes authoritative state: it consumes the EvidenceStore, not ad-hoc reads.
- **`project_inventory_domain`** — latest observation per SKU, `missing≠zero` (missing fields listed as `missing_fields`, never coerced to 0), stale-is-not-current via lineage freshness.

## Rules enforced (mirrors MASTER_PLAN §8.4)

| Rule | Implementation | Evidence |
|---|---|---|
| Missing is not zero | `missing_fields` tracked; absent `stock` stays absent | `test_state_projection_missing_field_not_zero` [V] |
| Stale is not current | records older than `max_age_days` → STALE flag; `is_stale` on snapshot | `test_state_is_stale_on_empty_or_old_evidence` [V] |
| Partial is not complete | `has_missing_required_fields` reports missing fields | [V] |
| Deterministic, replayable | identical evidence → identical `state_version` | `test_state_projection_is_deterministic_and_versioned` [V] |
| Explainable lineage | snapshot retains evidence ids per domain | [V] |

## Reuse vs parallel

`business_memory.optimistic_version` per-document counters remain the durable home; this composite `state_version` is the loop's aggregate decision-binding key (exactly what recommendation/governance bind to). No parallel durable store.

## Gaps

G-3B (composite business-state version) is the central gap this phase closes. Still NOT a durable store: snapshots are recomputed from evidence each cycle (correct-by-design for a content-addressed model).