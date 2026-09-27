# PHASE_2_SEC17_OUTCOME_FOUNDATION_EVIDENCE.md

**Status: sec 17 MIGRATED [V] — Verified by tests.**

MASTER_PLAN sec 17: **outcome + business-state foundation (SQLite/duckdb
capture, ledger schema, V1 outcome schema)**. This is the durable capture
layer that ties each canonical decision to its measured outcome so the
learning loop (sec 8) consumes **verified outcomes only — never raw Jev
output**.

## 1. What was built (all additive, no production routing changed)

- **`backend/app/services/outcome_ledger.py`** — `OutcomeLedger`, a
  best-effort, schema-versioned (`OUTCOME_SCHEMA_VERSION = "v1"`) SQLite
  capture store over one `outcome_ledger_v1` table with a fixed `COLUMNS`
  list binding **decision + evidence + outcome** on a single snapshot row:
  - decision: `capability`, `deterministic_decision` (authoritative), `source`
    (jev | fallback | disabled), `agree`
  - evidence: `capsule_hash`, `model`, `provider`, `latency_ms`, `risk_flags`
  - outcome: `outcome_status` (unknown|confirmed|partial|failed|rejected),
    `verified`, `expected_impact_sar`, `actual_impact_sar`
  - API: `record()` (idempotent on sha-derived `decision_key`),
    `record_verified_result()`, `verified_outcomes()` (verified=1 only),
    `summary()` (disaggregated totals).
- **Wiring** — `backend/app/services/canonical_controller.py`:
  `_capture_outcome_ledger()` invoked from `canonical_decision` after
  `_record_shadow`. **Gated by `settings.AI_OUTCOME_LEDGER_PATH` (default
  empty — no capture in production unless explicitly enabled).** Best-effort:
  every exception is swallowed; capture can never block or change a decision.
- **Config** — `backend/app/config.py`: `AI_OUTCOME_LEDGER_PATH: str = ""`.
- **Tests** — `backend/tests/test_outcome_ledger_v1.py` (12 tests, DB-free /
  network-free, temp SQLite ledgers, injected Jev mock transports).

## 2. Determinism gate (Jev off ⇒ unchanged deterministic result)

`test_determinism_gate_preserved_with_capture_enabled`: Jev disabled →
`canonical_rank` returns `decision="LOW"`, `source="fallback"`,
`jev_consulted=False`, and exactly **one** ledger row captured.

`test_capture_row_agreement_jevs_disabled`: dissent = 0, and the raw captured
row is **not** consumable via `verified_outcomes()` (verified=0).

## 3. Shadow parity (Jev advisory; deterministic always wins)

`test_capture_row_binds_jev_shadow_consult`: Jev suggests `LOW` while
deterministic is `HIGH` → decision stays `HIGH`, `alternative_decision="LOW"`,
ledger records `dissent=1`. Deterministic authoritative, divergence captured.

## 4. Verified-only consumption (sec 8 invariant)

`test_verified_outcome` flows: `record_verified_result(decision_key, ...,
verified=True, actual_impact_sar, expected_impact_sar)` flips `verified=1` +
`outcome_status="confirmed"`; `verified_outcomes()` returns only those rows;
`summary()` reports `verified=1`, `by_outcome_status={"confirmed": 1}`.

`test_verified_only_consumption_excludes_raw_rows`: a second unverified row
(still `unknown`) is excluded — `verified_outcomes()` never exposes raw
captures to the learning loop.

## 5. Best-effort + idempotent + DLP

- `test_capture_never_blocks_decision_when_path_unwritable`: a path under a
  missing directory still yields `decision="HIGH"`, `source="fallback"` — the
  gap between "capture" and "decide" is fail-open on the capture side only.
- `test_idempotency_replay_coalesces_on_decision_key`: three replays of the
  same key produce exactly one row (mill/retry-safe).
- `test_ledger_row_never_contains_business_id_plaintext`: the only persisted
  reference to a business id is the sha-256-derived 24-hex decision key —
  plaintext ids never enter the ledger file.
- `test_derive_decision_key_deterministic`: same inputs → same key; different
  decision → different key; `len==24`.

## 6. V1 schema

`test_v1_outcome_ledger_schema_versioned` pins `OUTCOME_SCHEMA_VERSION == "v1"`;
every row carries `schema_version="v1"` and the full `COLUMNS` binding.

## 7. Gate / verdict trace

| Gate (matrix §7) | Result |
|---|---|
| Determinism | GREEN — deterministic decision byte-identical, source=`fallback` |
| Shadow parity | GREEN — Jev advisory only; dissent captured |
| Verified-only learning | GREEN — `verified_outcomes` is the exclusive consumer surface |
| DLP / contract | GREEN — no plaintext ids; contract-key decisions; sha keys only |
| CI | **12 tests green standalone; 65 combined canonical suites green** (284.49s, timeout=150); `python -m compileall -q app tests` exit 0 |

## 8. Verification commands (reproduce)

```powershell
cd backend
$env:JEV_ENABLED="false"; $env:USE_TEMPORAL="false"
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
python -m pytest tests/test_outcome_ledger_v1.py -q -p no:cacheprovider --timeout=150
```

Result: `12 passed`.

Then the combined canonical suite (B1+B2+B3+sec17):
`tests/test_canonical_controller.py tests/test_shadow_parity.py
tests/test_provider_failure_tests.py tests/test_inventory_stockout_tier.py
tests/test_anomaly_triage.py tests/test_batch3_canonical_surfaces.py
tests/test_outcome_ledger_v1.py` → **65 passed, 21 warnings in 284.49s**.

## 9. Scope guardrails honored

- No production Jev routing — shadow-only (already enforced).
- Capture is **opt-in** (`AI_OUTCOME_LEDGER_PATH` empty by default) and
  best-effort; decision path cannot be blocked or altered by it.
- No Postgres/Temporal dependency; SQLite stdlib only; DB-free tests.
- No commits pushed; working tree untracked files only.