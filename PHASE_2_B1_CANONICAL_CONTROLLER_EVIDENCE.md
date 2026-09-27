# PHASE 2 — BATCH 1 CANONICAL CONTROLLER EVIDENCE

- Date: 2026-09-23
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Purpose: evidence that the three Batch 1 Choice surfaces are migrated onto the
  policy-checked AI choke point (`ai_gateway.systemone_reason`) through the
  canonical controller, determinism/shadow/availability/contract gates green,
  and Jev is never authoritative.

## 1. Batch 1 roster — surface → cannonical entry point [V]
| Surface | Canonical entry point (`backend/app/services/canonical_controller.py`) | Contract frozenset |
|---|---|---|
| `recovery.rank` | `canonical_rank(payload=, deterministic_bucket=)` | `RANK_BUCKETS = {TOP, HIGH, MEDIUM, LOW, DO_NOTHING}` |
| `recovery.action_type` | `canonical_action_type(payload=, deterministic_action=)` | `CANONICAL_ACTION_TYPES` (from `app/orchestration/contracts.py:17-24`) |
| `audit.root_cause_bucket` | `canonical_root_cause(payload=, deterministic_bucket=)` | `ROOT_CAUSE_BUCKETS` (13 taxonomy keys incl. `UNCERTAIN`) |

Entry points keep the exact production signatures owner modules already use —
integration is a one-line substitution per surface.

## 2. Architecture (verify-then-finalize) [V]
`canonical_decision()` (canonical_controller.py:133) is the shared flow:
1. `deterministic_decision` is normalized; the controller NEVER manufactures a
   decision — it comes from the surface's existing deterministic logic.
2. If a contract frozenset is given, the deterministic decision must be IN the
   contract, else `CanonicalControllerError` (fail-closed).
3. A signed DLP-clean `ReasoningCapsule` is built via
   `build_capsule_for_payload` (no SKUs/ids/exact values cross the boundary).
4. Jev is consulted in **shadow mode** (`shadow=True`) through
   `systemone_reason`, passing `allowed_suggestions=contract` AND
   `allowed_decisions=contract`.
5. The final `decision` is ALWAYS the deterministic decision
   (canonical_controller.py:192).
6. A per-surface output-gate validator (`_validate_rank`,
   `_validate_action_type`, `_validate_root_cause`) checks the Jev suggestion
   against the contract; out-of-contract suggestions are discarded and flagged
   `risk_flags=["JEV_OUT_OF_CONTRACT"]`.
7. Every outcome is recorded to the shadow parity JSONL ledger with model
   (`jev-1.13.0`), capsule hash, provider, latency, and
   `source_label="deterministic_authoritative"` (canonical_controller.py:73-104).

### 2.1 Adapter surface-aware vocabulary [V]
`jev.consult()` gained `allowed_suggestions: frozenset[str] | None = None`
(`backend/app/services/ai_providers/jev.py`).
- Default (`None`): fail-closed — suggestions outside `VALID_SUGGESTIONS` are
  discarded → `source="fallback"` + `errors=["invalid_suggestion:<x>"]`.
- Surface passes its own vocabulary: out-of-vocabulary suggestions are surfaced
  verbatim (`source="jev"`) so the CALLER's output gate (canonical controller +
  gateway decision coercion) owns contract enforcement and emits
  `JEV_OUT_OF_CONTRACT`. The adapter is advisory and never authoritative.

### 2.2 Gateway default decision vocabulary [V]
`ai_gateway.py` defines
`DEFAULT_ALLOWED_DECISIONS = frozenset({"DO_NOTHING","REORDER","TRANSFER","DISCOUNT","PRICE_CHANGE","RECOVERY_MATCH","MANUAL_REVIEW"})`.
`systemone_reason()` takes `allowed_suggestions`/`allowed_decisions`; decision
coercion is now `decision.upper() not in (allowed_decisions or DEFAULT_ALLOWED_DECISIONS)`,
so surface deterministic values (e.g. `TOP`, `REORDER_THRESHOLD_LOW`) are
recorded verbatim instead of being clobbered to DO_NOTHING.

## 3. Verification run [H]
```
cd backend
$env:PYTHONPATH="...\backend"; $env:JEV_ENABLED="false"; $env:USE_TEMPORAL="false"
python -m pytest tests/test_canonical_controller.py tests/test_provider_failure_tests.py tests/test_shadow_parity.py -q
```
Result: **24 passed** (9 canonical-controller + 11 provider-failure/availability +
4 shadow-parity). [H]

Regression baseline (AI security + phase4 + phase5 gate suites):
`python -m pytest tests/security tests/phase4 tests/test_phase5.py -q`
Result: **239 passed** — no regressions from the adapter/gateway/controller work. [H]

Benchmark (determinism gate, re-captured on final code):
`python -m benchmarks.jev_shadow_parity`
```
total=3  agree=3  diverge=0  jev_down=0  deterministic_total=3   EXIT=0
```
Ledger: `backend/results/jev_shadow_parity.jsonl` (6 rows, 3 per run). [H]

`python -m compileall -q app tests` → exit 0. [H]

## 4. Defects found & fixed during migration (non-destructive code fixes)
1. **Adapter fail-closed was too strict** — `jev.consult()` rejected any
   suggestion outside its flat `VALID_SUGGESTIONS` at the adapter layer, so the
   surface's output gate (canonical controller) could never enforce a contract
   and emit `JEV_OUT_OF_CONTRACT`. Fix: `allowed_suggestions` parameter (surface
   vocabulary passthrough), owner = caller's output gate. [FIXED]
2. **Gateway coercion clobbered authoritative values** — the audit DB recorded
   surface deterministic decisions such as `REORDER_THRESHOLD_LOW` as
   `DO_NOTHING`. Fix: `allowed_decisions` passthrough from the controller; only
   genuinely out-of-contract values fall back to DO_NOTHING. [FIXED]
3. **`GLOBAL_AI_BUDGET` singleton leaked across tests** — the YOLO gateway test
   hit `ai_budget_exhausted` because calls accumulated between tests, so the
   decision coercion path (which the test exists to prove) never ran. Fix:
   autouse `_reset_ai_budget` fixture in `test_canonical_controller.py` and
   `test_provider_failure_tests.py` calling `GLOBAL_AI_BUDGET.begin_audit()`
   before each test. [FIXED]
4. **`_validate_root_cause` signature mismatch** — validators are called
   uniformly as `validate_suggestion(suggestion, base_decision)` but the
   root-cause validator only accepted one argument
   (`TypeError: takes 1 positional argument but 2 were given`). Fix: aligned
   signature with `_validate_rank`/`_validate_action_type`. [FIXED]

## 5. Batch acceptance gates (TEST_AND_ACCEPTANCE_GATES.md §6.1–6.3) [V]
| Gate | Status | Evidence |
|---|---|---|
| Determinism gate (Jev off → identical output) | GREEN | `test_determinism_gate_action_type_jev_off`, `test_determinism_gate_rank_jev_broken`; benchmark `deterministic_total=3` |
| Shadow parity audit (divergence logged, deterministic wins) | GREEN | `test_shadow_parity_jev_agrees_decision_unchanged`, `test_shadow_parity_jev_dissents_deterministic_wins`; ledger rows `source_label=deterministic_authoritative` |
| Availability gate (Jev down/budget → fallback + audit) | GREEN | `test_provider_failure_tests.py` 11 passed (connect/fault/429/500/502/503/529/timeout/fatal-exit/budget-exhaust/encoding) |
| Contract gate (Jev keys vs canonical sets) | GREEN | `test_contract_gate_out_of_contract_suggestion_discarded`, `test_contract_gate_root_cause_taxonomy`, `test_rank_bucket_contract_and_governance`, `test_contract_enforcement_deterministic_decision`, `test_contracts_are_disjoint_notable` |
| Governance gate (RLS/capsule DLP; no business_id in capsule) | GREEN | `build_capsule_for_payload` + `capsule.capsule_hash` recorded; `test_rank_bucket_contract_and_governance` |
| CI (backend unit baseline) | GREEN | `tests/security tests/phase4 tests/test_phase5.py` → 239 passed; compileall exit 0 |

## 6. Batch 1 verdict
**MIGRATED + ACCEPTED — all three Batch 1 Choice surfaces are now governed by
the canonical controller. Jev contributes advisory confidence / an alternative
suggestion only; the deterministic decision is always final; every call is
captured to the shadow ledger. No surface has been switched to production
Jev routing (Jev remains shadow-only, per MASTER_PLAN §6/§8).**