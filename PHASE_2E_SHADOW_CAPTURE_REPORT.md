# PHASE 2E REPORT - SHADOW CAPTURE (parity ledger + outcome capture)

Status: **GREEN** [V]

## Scope
- Durable shadow capture: one row per decision bound to its evidence, so
  divergences between Jev and deterministic are logged and the deterministic
  decision always wins (shadow-only; no production routing).

## Evidence
- JSONL shadow parity ledger: `app/services/shadow_capture.py#ShadowParityRecorder`
  (default `backend/results/jev_shadow_parity.jsonl`; `_ledger_path()` follows
  `AI_CALL_LEDGER_PATH` when configured). Emitted for every conservative
  `canonical_decision` call. [V]
- V1 outcome ledger (MASTER_PLAN sec 17):
  `app/services/outcome_ledger.py#OutcomeLedger` — SQLite capture with
  `OUTCOME_SCHEMA_VERSION="v1"`, one decision→evidence→outcome row per decision,
  idempotent on the sha-derived `decision_key`, `verified_outcomes()` exclusive
  verified-only consumption surface, plaintext business ids never stored. [V]
- Capture is **best-effort and opt-in**: `_capture_outcome_ledger` swallows all
  exceptions and runs only when `settings.AI_OUTCOME_LEDGER_PATH` is set;
  `record()`/`record_verified_result()`/`summary()` fail-open without blocking a
  decision (tests prove unwritable-path + missing-dir safe). [V]
- Shadow parity contract gate: Jev out-of-contract suggestion discarded +
  `JEV_OUT_OF_CONTRACT`; dissent (`agree=False`) explicitly captured. [V]

## Gate / verdict
| Gate | Result |
|---|---|
| Parity capture | GREEN — every decision recorded with agree/dissent + source |
| Verified-only learning | GREEN — `verified_outcomes()` = verified=1 only |
| DLP | GREEN — no plaintext business ids in ledger files |
| Best-effort | GREEN — capture can never block or change a decision |
| CI | GREEN — `tests/test_outcome_ledger_v1.py` 12 green; combined 65 green |

Cross-reference: `PHASE_2_SEC17_OUTCOME_FOUNDATION_EVIDENCE.md`.