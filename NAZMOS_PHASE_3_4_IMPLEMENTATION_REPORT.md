# NazmOS Phase 3–4 Implementation Report

## Scope

Implemented locally only. No GitHub changes were made.

### Phase 3 — OpenCode Brain Boundary

- Added explicit mapping from OpenCode decision labels to canonical NazmOS action types.
- Fixed registry validation so `TRANSFER` maps to `transfer_inventory` and `PRICE_CHANGE` maps to a registered pricing capability.
- Preserved deterministic decision on all OpenCode failure/fallback paths.
- Hardened OpenCode subprocess environment: only provider credentials are passed, rather than the full application environment.
- Hardened JSON extraction for CLI/event output that contains a structured decision inside surrounding output.
- Timeout handling now kills and waits for the child process before returning fallback.

### Phase 4 — AI Decision Value

- Added decision-value comparison model with explicit:
  - GOOD_OVERRIDE
  - BAD_OVERRIDE
  - NEUTRAL_OVERRIDE
  - UNRESOLVED
- Agreement is explicitly neutral and never counted as AI improvement.
- Added AI call/failure, latency, cost, hallucination, and constraint-violation metrics.
- Added strict/effective baseline/final accuracy calculation.
- Added a local experiment runner that keeps ground truth outside the OpenCode reasoning path.
- The runner never executes financial actions.

## Tests

- Python compilation: PASS
- AST parsing of changed Phase 3/4 files: PASS
- Existing project pytest collection: BLOCKED in this environment because the project's PostgreSQL test bootstrap requires `asyncpg`, which is not installed.

This environment does not have Docker or OpenCode installed, so no real OpenCode or PostgreSQL runtime result is claimed.

## Files changed/added

- `backend/app/services/opencode_brain.py`
- `backend/app/services/decision_value.py`
- `backend/tests/phase4/test_decision_value.py`
- `backend/tests/phase4/test_opencode_brain.py`
- `scripts/phase4/run_experiment.py`
- `NAZMOS_PHASE_3_4_IMPLEMENTATION_REPORT.md`

## Next runtime step

Run the project in the existing Docker/OpenCode environment and execute the Phase 4 experiment with real OpenCode calls. Do not substitute mock AI for the primary experiment.
