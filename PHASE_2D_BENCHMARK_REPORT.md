# PHASE 2D REPORT - DETERMINISTIC BASELINE BENCHMARK

Status: **GREEN** [V]

## Scope
- Deterministic-only benchmark / shadow-parity harness proving the pre-migration
  deterministic outputs, as the byte-identical ground truth for every Batch 1/2/3
  surface (the "determinism gate").

## Evidence
- Benchmark runner: `backend/benchmarks/jev_shadow_parity.py` (shadow parity
  harness). [V]
- Shadow ledger artifact: `backend/results/jev_shadow_parity.jsonl` — every row
  records `capability`, `deterministic` (authoritative decision),
  `jev_suggested`, `jev_source`, `agree`, `decision`, e.g.:
  `{"capability":"opencode_brain","deterministic":"REORDER","jev_source":"fallback",
    "jev_suggested":null,"agree":true,"decision":"REORDER"}`. [V]
- Baseline determinism is byte-identical: Jev-off runs in every canonical suite
  assert identical decisions, `source="fallback"`, correct `risk_flags`, and a
  correct `source_label="deterministic_authoritative"` shadow row. [V]
- Ground-truth per surface (owner modules) captured in MIGRATION_MATRIX §1-3:
  rank buckets, `CANONICAL_ACTION_TYPES`, root-cause taxonomy,
  `INVENTORY_STATUS_TIERS`, `ANOMALY_TRIAGE_BUCKETS`, `REORDER_URGENCY_BANDS`,
  `MARGIN_EROSION_BANDS`, `FINDING_PRIORITY_TOKENS`. [V]

## Gate / verdict
| Gate | Result |
|---|---|
| Deterministic baseline | GREEN — byte-identical output with Jev off on all 8 surfaces |
| Benchmark parity data | GREEN — JSONL shadow ledger continuously appended |
| CI | GREEN — benchmark runner + ledger tests in canonical/shadow/outcome suites |

Cross-reference: `MIGRATION_MATRIX.md` §§1-3,5-6;
`backend/results/jev_shadow_parity.jsonl`.