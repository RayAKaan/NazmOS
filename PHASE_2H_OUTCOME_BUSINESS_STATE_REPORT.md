# PHASE 2H REPORT - OUTCOME + BUSINESS-STATE FOUNDATION (sec 17)

Status: **GREEN** [V]

## Scope
- Outcome + business-state foundation (MASTER_PLAN sec 17): SQLite capture,
  ledger schema, V1 outcome schema — the durable layer that ties each decision
  to its measured, verified outcome so the learning loop (sec 8) consumes
  verified outcomes only, never raw Jev output.

## Evidence
- `app/services/outcome_ledger.py#OutcomeLedger`: versioned (`v1`) SQLite
  outcome ledger; one decision→evidence→outcome row per decision
  (`capability`, `deterministic_decision`, `source`, `agree`, `capsule_hash`,
  `model`, `provider`, `latency_ms`, `risk_flags`, `outcome_status`, `verified`,
  `expected/actual_impact_sar`). [V]
- Wiring: `canonical_controller._capture_outcome_ledger` after `_record_shadow`;
  **gated by `settings.AI_OUTCOME_LEDGER_PATH` (default empty)**; best-effort
  (can never block or change a decision). [V]
- Verified-only consumption invariant: `verified_outcomes()` returns only
  `verified=1` rows (MASTER_PLAN sec 8); idempotent on the sha-derived
  `decision_key` (24-hex; no plaintext business ids stored). [V]
- Config: `AI_OUTCOME_LEDGER_PATH: str = ""` in `app/config.py`. [V]

## Gate / verdict
| Gate | Result |
|---|---|
| V1 schema / versioning | GREEN — `OUTCOME_SCHEMA_VERSION == "v1"`, every row stamped |
| Ledger semantics | GREEN — append-only via idempotent upsert on decision_key |
| Verified-only learning | GREEN — verified=1 rows only; raw captures never consumable |
| DLP | GREEN — no plaintext business ids in ledger files |
| Best-effort / availability | GREEN — missing/unwritable path never blocks a decision |
| CI | GREEN — `tests/test_outcome_ledger_v1.py` 12 green; 65 combined canonical green; compileall exit 0 |

Cross-reference: `PHASE_2_SEC17_OUTCOME_FOUNDATION_EVIDENCE.md`;
`MIGRATION_MATRIX.md` §9.