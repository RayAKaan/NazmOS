# PHASE_3I — Verification, Learning Eligibility & Cycle Orchestration (`outcomes.py`, `cycle.py`)

> Execution success ≠ business success. Only measured, verified, traceable, authorized outcomes enter learning. MASTER_PLAN §14, §15, §16.

## Verified outcome (`outcomes.py`)

- `VerificationStatus` ladder reported → observed → (partially) verified. A VERIFIED outcome requires a measured `observed_impact_sar` + distinct baseline/post state versions + a named method. A receipt alone can never reach VERIFIED (`test_verification_ladder_estimate_never_equals_verified` [V]).
- `verify_outcome` records the *measurement* as the truth source; whether the observed value came from the injected `verification_evaluator` (an external measurement authority) — the loop never invents the number. In the slice, `observed_impact_sar == 2000.0` came from pre/post state comparison (`_measurement_authority`) — asserted [V].
- `learning_eligibility` gates verified learning: requires traceable source + VERIFIED + tenant/purpose authorized + quality satisfied; otherwise reasons (e.g. `outcome_not_verified`) [V].
- Verified path persists through the EXISTING V1 `OutcomeLedger` (`VerifiedOutcomeLedger`) — verified-only consumption, no parallel ledger [I].

## Cycle orchestrator (`cycle.py`)

- Stable `cycle_id` = sha256(tenant:business:trigger:trigger_token) — duplicate triggers with the same token **return the same in-flight/run** (idempotent; `test_duplicate_trigger_suppressed` [V]).
- 21-stage state machine from `CycleStage` (evidence discovery → … → next_cycle), each stage a pure handler over the DB-free modules.
- Bounded work: `max_opportunities_per_cycle`, `max_recommendations_per_cycle`, `max_retries_per_stage` with an explicit retry budget. A stale/no-evidence cycle is blocked (`stale_state_no_evidence`), and a no-opportunity cycle is a *successful no-op* (`opportunity_count==0`, `learning_eligible=False`) — asserted [V].
- Resilient driving: `run_one_stage` (exactly one stage, returns False at completion/block), `run_all` (bounded, never infinite). Errors record into the stage state + `last_error`, retried up to budget.
- Serialization seam (`CycleRun.serialize`) is the durability contract for Temporal/DB.

## Gaps

G-3F / G repeated-trigger intercycle cooldown is implemented at policy level (`cooldown_seconds`); live scheduling is a Temporal wiring task, not loop logic.