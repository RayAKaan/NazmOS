# MIGRATION_MATRIX.md

**The exact 3-per-batch migration plan, current convergence status, and per-surface evidence.**
Rule: **EXACTLY THREE replacements per batch**, each batch fully tested + accepted before the next. No code was migrated in Phase 0. Evidence labels: [V] verified, [H] historical, [I] inferred, [B] blocked.

## 0. Global preconditions before ANY batch

1. **Repo compiles and `app.main` imports** — currently FALSE (see CURRENT_STATE.md §3): `backend/app/services/intelligence_api.py` (working tree) and `backend/tests/test_analytics_health_score.py` (committed at a49b2c5) break compileall, and `conftest.py:30` `from app.main import app` fails collection for the whole backend test tree. **Phase 1 must fix these first.** [V]
2. Velocity canonicalization (Phase 2B) fully converged — remaining inline `/30` sites below must be resolved so Jev Score prompts read canonical velocity. [V]
3. Deterministic ground-truth target exists for every surface being scored (labelled samples for thresholding). [I]

## 1. Batch 1 — Choice surfaces (adviser-rank, action, root cause)

| Surface | Code owner (verified) | Deterministic current | Jev shape | Action required for batch |
|---|---|---|---|---|
| `recovery.rank` | recovery agent / `recovery_match_service.py:145,297` (canonical velocity) | Yes [V] | Choice over rank buckets | Expose ranked candidate list + deterministic rank in evidence; Jev Choice keys = bucket ids |
| `recovery.action_type` | `orchestration/contracts.py:17-24` `CANONICAL_ACTION_TYPES` | Yes [V] | Choice over canonical actions | Jev output must be validated against contract set (output gate rejects non-contract keys) |
| `audit.root_cause_bucket` | `app/services/root_cause.py` (buckets) | Yes [V] | Choice over root-cause taxonomy | Deterministic bucket authoritative; Jev used only for confidence/advisory |

Batch 1 acceptance: determinism gate (Jev off → byte-identical), shadow parity audit, availability gate (Jev down → deterministic + `source="fallback"` label).

**Batch 1 STATUS: MIGRATED + ACCEPTED [V]** — all three surfaces now flow through
`app/services/canonical_controller.py` (`canonical_rank` / `canonical_action_type` /
`canonical_root_cause`) onto the single policy-checked choke point
(`ai_gateway.systemone_reason`, shadow=True). Deterministic decision always final;
Jev advisory only, validated against the surface contract (`JEV_OUT_OF_CONTRACT`
flag on discard). Evidence: `PHASE_2_B1_CANONICAL_CONTROLLER_EVIDENCE.md`
(24 canonical/provider/shadow tests + 239 security/phase4/phase5 baseline, exit 0
benchmark, compileall clean). No production Jev routing — shadow-only.

## 2. Batch 2 — Score surfaces

| Surface | Code owner (verified) | Deterministic current | Jev shape | Action required for batch |
|---|---|---|---|---|
| `inventory.stockout_tier` | **No symbol**; `classify_status`/urgency ints (`inventory_agent.py`, `analytics_service`) | Yes [V] | Score over urgency ladder | Create a named tier symbol fed by `classify_status` first; Score must mirror it |
| `inventory.anomaly_triage` | **ORPHANED** — detector emits, nothing persists to findings, no consumer [V] | Partial | Choice + Score | **Pre-req: persist anomalies (findings/evidence) so there is ground truth** |
| `procurement.supplier_risk` | supplier agent / supplier_network + `procurement_agent` | Yes [V] | Score over 3-level risk rubric | Needs deterministic risk basis (payment history/cost variance); defer batch slot if no ground truth |

**Batch 2 STATUS: MIGRATED (2) + DEFERRED (1) [V]** — `inventory.stockout_tier`
(contract `INVENTORY_STATUS_TIERS`, `classify_tier` wrappers canonical
`classify_status`) and `inventory.anomaly_triage` (pre-req satisfied: detector
output persists to `findings` via `app/services/anomaly_triage.py`, opt-in
consumer only) are on the canonical controller. `procurement.supplier_risk`
DEFERRED per §2 strict rule (no payment-history/cost-variance basis; existing
on-time/lead-time reliability rubric documented as substitute). Evidence:
`PHASE_2_B2_CANONICAL_MIGRATION_EVIDENCE.md` (15 Batch-2 + 39 combined tests,
finding-safe sqlite 58 passed, DB-free ai_policy gates 203 passed, compileall
clean). No production Jev routing — shadow-only.

## 3. Batch 3 — remaining surfaces

| Surface | Code owner (verified) | Deterministic current | Jev shape | Action required for batch |
|---|---|---|---|---|
| `procurement.reorder_urgency` | `procurement_agent.py` (reorder decisions) | Yes [V] | Score urgency ladder | Watch dead-stock 45-vs-30 window: state window explicitly |
| `pricing.margin_erosion_risk` | `pricing_agent.py`, `margin_agent.py`, `money_audit_service` margin analysis | Yes [V] | Score erosion rubric | Deterministic target = `gross_margin_pct`/margin thresholds; calibrate against it |
| `report.finding_priority` | findings creation/severity (`audit_engine`, report) | Yes [V] | Choice over severity contract | Tie to findings severity contract; advisory only until verified outcomes exist |

**Batch 3 STATUS: MIGRATED (3) [V]** — `procurement.reorder_urgency`
(contract `REORDER_URGENCY_BANDS`, `reorder_urgency_band()` over canonical
days-of-supply; window stated explicitly, `DEAD_STOCK_DAYS=45` dead code
avoided), `pricing.margin_erosion_risk` (contract `MARGIN_EROSION_BANDS`,
`margin_erosion_band()` calibrated to the 0.15/0.22/0.40 threshold set), and
`report.finding_priority` (contract `FINDING_PRIORITY_TOKENS` = the 5
`FindingSeverity` values, advisory-only until verified outcomes exist) are all
on the canonical controller. Evidence:
`PHASE_2_B3_CANONICAL_MIGRATION_EVIDENCE.md` (14 Batch-3 tests + 53 combined
Batch 1+2+3 green, DB-free ai_policy/finding gates 203 passed, compileall
clean; AI-budget daily-counter test-isolation bug fixed via `AIBudget.reset()`).
No production Jev routing — shadow-only.

## 4. Deferred / never (documented only)

| Surface | Rationale (verified) |
|---|---|
| `procurement.moq_risk` | Hard to calibrate without ground truth; keep deterministic |
| `pricing.owner_band_eligibility` | Governance/access rule; must stay deterministic [V] |
| `governance.shariah_review_triage` | Must never be delegated to a model [V] |
| `finance.cash_action_priority` | Money-critical; deterministic-first |
| `approval.routing_priority` / `approval.urgency_score` | Governance/dial semantics (0/inform, 1-94/approval, 95-100/auto) owned by autonomy_service; document only [V] |

## 5. Current velocity-convergence status (must be done first)

Canonical: `audit_core.py:58 coverage_aware_daily_velocity` (semantics verified: None→/30; qty>0 & coverage≤0→/1; zero qty→0).

CONVERGED (use canonical): `audit_core.py:172`, `money_audit_service.py:345`, `recovery_match_service.py:145,297`, `root_cause.py:52` (patched over SQL /30), `evidence_package.py:186`, `intelligence_api.py:30` (import), `inventory_orchestrator.py:17` (import). [V]

REMAINING INLINE `/30` (converge in Phase 1): `audit_engine.py:173` (`qty_30d / coverage_days` — also lacks canonical zero/None coercion), `inventory_orchestrator.py:46` (`/ 30.0`), `nazm_planner.py:486` (`profit_30d / 30`), `intelligence_api.py:233` (`qty_30d / 30.0`), `root_cause.py:38/110` (raw SQL, patched downstream), `evidence_package.py:188` (`/ 30` — synthetic-simulator fallback, deliberate). [V]

## 6. Dead-stock window divergence (resolve before velocity-dependent batches)

- `DEAD_STOCK_DAYS = 45` at `audit_core.py:28`, `money_audit_service.py:20` [V]
- 30-day scans: `audit_engine.py:127` and `goal_service.py:79` call `get_dead_stock_summary({"days_no_sale": 30})`; analytics 30-day default window (`analytics/repository.py:51`); canonical WS5 "<1 unit sold in window with stock" (`analytics/contracts.py:75`) [V]
- Decision needed: single canonical wording/window for Jev Score ladders. [I]

## 7. Batch acceptance template (every batch, no exceptions)

1. Determinism gate: Jev disabled/unavailable → output identical to today (source label + `risk_flags` correct). 
2. Shadow parity audit: N observed cases; divergence logged; deterministic wins.
3. Availability gate: Jev outage/budget-exhaust → deterministic result, `source="fallback"`, audit event written.
4. Governance gate: RLS tenant scoped; capsule DLP-clean; no business_id in capsule; `autonomy_dial` unchanged; execution still via Temporal dispatcher.
5. Contract gate: Jev keys validated against canonical sets (`CANONICAL_ACTION_TYPES`, findings severity); `ai_reasoning_requests` records model version + capsule hash.
6. CI: full backend tests green (post-Phase-1 its collection works again); compileall green; bandit medium+ clean; temporal-suite zero skips over real server + Postgres.

## 8. Sequencing note

Phase 1 (foundation acceptance) MUST precede Batch 1. The 2B-convergence + 2C acceptance + compile/import fix are the hard blockers. Nothing in Phase 0 (this audit) performed any migration.

## 9. Outcome / business-state foundation (MASTER_PLAN sec 17)

**sec 17 STATUS: MIGRATED [V]** — V1 outcome ledger captures one
decision→evidence→outcome row per canonical decision (SQLite, best-effort,
idempotent on the sha-derived decision key, `schema_version="v1"`):
`app/services/outcome_ledger.py::OutcomeLedger` (+`record` /
`record_verified_result` / `verified_outcomes` / `summary`) wired additively
into `canonical_decision` via `settings.AI_OUTCOME_LEDGER_PATH` (empty by
default — no production capture unless enabled). Verified-only consumption:
`verified_outcomes()` returns only `verified=1` rows, matching MASTER_PLAN sec 8
("learning consumes verified outcomes, never raw Jev output"). Rows never
contain plaintext business ids — only the sha-derived key. Evidence:
`PHASE_2_SEC17_OUTCOME_FOUNDATION_EVIDENCE.md` (12 tests green; 65 combined
canonical B1+B2+B3+sec17 green). No production Jev routing — shadow-only;
capture never blocks or changes a decision.

## 10. Phase 3 — Continuous Business Improvement Loop (CBIL)

**Phase 3 STATUS: MIGRATED (loop spine) [V]** — a complete, DB-free,
evidence-backed loop spine `app/services/business_loop/` with **29 new tests
green** (module units + synthetic vertical slice) and the 260-test Phase 3A
baseline re-verified green with Postgres env (0 failed; no regression). Full
detail in `PHASE_3A_REPOSITORY_AND_BASELINE_REPORT.md` and
`PHASE_3B..3L` reports at repo root.

| Stage | New capability | Reuse anchors (never re-implemented) | Evidence |
|---|---|---|---|
| 3B Evidence | `EvidenceStore` — idempotent, conflict/correction-aware, checksum + freshness + quality flags, dedupe | existing `Event`/ingestion cleanliness semantics | `test_business_loop_modules.py` [V] |
| 3C State | `BusinessStateSnapshot` — deterministic composite `state_version`, domain values, evidence lineage, `missing≠zero`/`stale≠current` | `business_memory.optimistic_version` counters (projection stays content-addressed, not a new durable store) | `test_state_projection_*` [V] |
| 3D/3F Opportunity+Impact | deterministic rules (EXCESS_INVENTORY ≥30d & ≥SAR500, STOCKOUT <5d, MARGIN <22%); impact POTENTIAL-only; `reproducible_impact` | `audit_core`, `recovery_match_service.generate_preview`, `ACTION_REGISTRY`, `CANONICAL_ACTION_TYPES` thresholds | `test_detect_*` [V] |
| 3E Advisory+Recommendation | typed advisory ladder (out-of-contract discarded, never coerced); versioned `Recommendation` with lifecycle + material-hash binding | `ai_gateway.systemone_reason` (shadow, same as `canonical_decision`), `decision_engine`/`IntelligenceDecision`/`finding_service` lifecycle | `test_consult_advisory_*`, `test_recommendation_*` [V] |
| 3G Governance | deterministic-only, AI-independent gate; unregistered→DENIED, ambiguity→DEFERRED; approval binds `id:vN:material_hash` | `ACTION_REGISTRY`, `autonomy_service` (unchanged) | `test_governance_*` [V] |
| 3H Execution/Reconciliation | preflight registry+preconditions; dry-run always `synthetic=True`; reconcile blocks blind retries on reported/unconfirmed | `orchestration/keys.py::derive_execution_key`, Temporal dispatcher (unchanged) | `test_execution_*` [V] |
| 3I Verification/Learning/Cycle | VERIFIED requires measured observed impact + distinct state versions; `learning_eligibility` verifies-first; bounded 21-stage `CycleOrchestrator`, idempotent `cycle_id`, retry budget, successful-no-op | **existing V1 `OutcomeLedger`** (`record`→`record_verified_result`), `learning_reconciliation` — no parallel ledger | `test_verification_ladder_*`, slice e2e [V] |
| 3L Synthetic slice | full e2e: evidence→state→opportunity→advisory(mocked Jev, source=mocked)→recommendation→governance→dry-run→reconcile→verify→learning | mocked Jev explicitly labelled, never labelled jev | `test_phase3_synthetic_vertical_slice.py` (29 tests total) [V] |

**Authority boundaries locked in Phase 3** (asserted by tests, not just stated):
AI never authorizes (governance certified deterministic; slice approval labelled
SYNTHETIC); estimates ≠ verified (POTENTIAL until measured); attribution exact
(`source/provider` verbatim, fake never labelled jev); dry-run never a real
merchant action (`synthetic=True`); no blind retry; duplicate triggers
idempotent; out-of-contract advisory dropped flagged. Verified learning strictly
gated by `learning_eligibility` (verified+authorized+quality) consuming the
V1 outcome ledger — MASTER_PLAN sec 8 preserved.

**Owner Command Center (3K)** and live Temporal scheduling remain as the
documented next increments (read-only surfaces reuse dashboard/intelligence
routers; triggers reuse `orchestration/temporal/schedules.py`). Blockers B1–B4
(from PHASE_3A) unchanged — no destructive ops were performed on the live stack.

## 11. Phase 4 — Business Loop Runtime (durability)

**Phase 4 STATUS: IN-PROGRESS (4A contract + 4B durability + 4C advisory + 4D Temporal dispatch + 4E revalidation + 4F verified outcome linkage + 4G read-only console) [V]** — the
runtime contract is frozen (`PHASE_4A_RUNTIME_CONTRACT_REPORT.md`), run state
is durable: migration `ff14_cycle_runs`
(+ `ff15_cycle_runs_rls_coverage` re-asserting the policy in the scanner-visible
pattern; full chain verified against a scratch PG DB), async `CycleRepository`
seam, and `PostgresCycleRepository` proving the 4A durability contract
(lossless round-trip, idempotent create on `(business_id, cycle_id)`,
optimistic `version` concurrency, terminal protection, tenant scoping).
7/7 `test_cycle_run_repository.py` green; Phase 3 slice regression green.
Detail: `PHASE_4B_REPORT.md`.
4C wired the loop's Jev advisory through the canonical `ai_gateway` entry
(`canonical_advisor` → `systemone_reason` → `jev.consult`) and registered the
`business_loop.action_selection` AI-policy capability that was silently
blocking the loop's advisory in production. 11/11 `test_phase4_jev_advisory.py`
green (typed advisory, exact attribution, out-of-contract dropped, capsule
DLP-clean on the wire). Detail: `PHASE_4C_REPORT.md`.
4D made the loop a durable Temporal workflow: `business_cycle_run` orchestrates
`business_cycle_start` → `business_cycle_advance` (≤128, budget-guarded) with
`business_cycle_reconcile` as the reconcile-before-retry gate; worker restart
resumes from the persisted snapshot, no blind retries past budget, duplicate
triggers suppressed. 23/23 `tests/temporal` green (6 new), full non-temporal
regression green (1445 passed). Live `temporal-1` + rebuilt `nazmos-worker-1`
running and polling `nazm-execution`. Detail: `PHASE_4D_REPORT.md`.
4E added the persisted-cycle revalidation gate: the advance activity recomputes
`starting_state_version` + `evidence_watermark` from the resume's evidence and
hard-blocks (never blind-retries) on drift or cross-scope, so a resumed cycle
can not advance past a baseline its evidence can no longer reproduce.
DB-free `test_phase4_cycle_revalidation.py` (6) + postgres-backed Scenario F in
`tests/temporal` (7 total) green; full non-temporal regression green (1445).
Detail: `PHASE_4E_REPORT.md`.
4F linked the executed action to the canonical outcome and the EXISTING
`OutcomeLedger` V1 (still authoritative — no second ledger/store): new
`outcome_linkage.py` builds a durable linkage (tenant/business/cycle/execution/
recommendation + measured impact + attribution) in `state_output`, the advance
activity attaches it once per execution (readback-confirmed, tenant-scoped,
idempotent by key + persisted marker), `verify_outcome` now REQUIRES distinct
baseline/post state versions for VERIFIED, and the previously hardcoded learning
gates in `_stage_learning_eligibility` are computed (tenant + fresh watermark +
attribution-sufficient — a Jev advisory alone can never authorize learning).
DB-free `test_phase4_outcome_linkage.py` (30) + postgres-backed Scenario G in
`tests/temporal` (28 total) green; full non-temporal regression green (1481).
Detail: `PHASE_4F_REPORT.md`.
4G added the tenant-scoped, read-only Business Loop Command Center: a frozen read
model (`loop_console_readmodel.py`, `READ_MODEL_VERSION="1.0"`) projecting
`cycle_runs.state_output` into a 7-step lifecycle ladder + banded list + owner
detail (exact observed/potential impact, delta only when expected known, 21-stage
timeline, recovery, `outcome_key`), served by a GET-only `/api/v1/loop-console`
router backed by `cycle_run_repository.page()`/`outcome_keys()` and a fail-closed
`_scoped_verified_rows` over the EXISTING V1 `OutcomeLedger` (no second store).
No mutation verbs; `assert_business_access` on the principal (cross-tenant 403,
owner unknown-id 404); DLP-clean (exact SAR confined to owner detail). Frontend
`/loop` page + middleware auth + nav entries (tsc clean, eslint 0 errors, jest 7/7).
Detail: `PHASE_4G_REPORT.md`. PARTIAL ACCEPTANCE — DB-free surface + frontend fully
evidenced; Postgres-backed Section B (6) and the IDOR extension are staged but
PENDING-PG in this environment (no reachable Postgres).

| Item | New capability | Reuse anchors (never re-implemented) | Evidence |
|---|---|---|---|
| 4A Runtime contract | frozen `CycleRun.serialize()` key set = lossless seam; 21 ordered stages; resume cursor = first stage ∉ {ok, skipped}; recovery rules (idempotent start, reconcile-before-retry, optimistic guard, terminal protection, next-cycle new run) | existing `CycleOrchestrator`, `CycleStage`, `derive_cycle_id` | `PHASE_4A_RUNTIME_CONTRACT_REPORT.md` |
| 4B Durable CycleRun persistence | `cycle_runs` table (uq `(business_id, cycle_id)`, tenant index, stage check, FK CASCADE, RLS policy, `nazmos_app` grant); async `PostgresCycleRepository` with `CycleRunConflictError`, `_version` optimistic guard, `all(business_id)` console shape | `businesses` FK, RLS pattern from `phase_b_rls_core_services` / `b7c8d9e0f1a2`, grant pattern `ff11` | `test_cycle_run_repository.py` (7) [V], scratch-DB chain apply [V] |
| 4C Jev-native typed advisory | loop advisory via canonical gateway: `canonical_advisor` → `systemone_reason` → `jev.consult`; `business_loop.action_selection` registered in `AI_CAPABILITIES` + `AI_CAPABILITY_FLAGS` (was silently policy-blocked); Deterministic always authoritative; `mocked` never `jev`; fallback never Jev; out-of-contract dropped; DLP-clean on the wire (`capsule.for_prompt()` only) | `ai_gateway.systemone_reason`, `consult_advisory`, `ReasoningCapsule`, `JevClient(transport=…)` mock pattern from `test_canonical_controller.py` | `test_phase4_jev_advisory.py` (11) [V], `ai_policy.py` registration [V], regression `test_canonical_controller.py`+`test_business_loop_modules.py`+`test_phase3_slice`+`test_cycle_run_repository.py` (64) [V] |
| 4D Temporal durable dispatch | `CycleRun` over Temporal: `business_cycle_run` workflow orchestrates `business_cycle_start` → `business_cycle_advance` (≤128, budget-guarded) → `business_cycle_reconcile` (reconcile-before-retry, requeue vs fail at budget); crash-resume from persisted snapshot; duplicate-trigger suppression; 3 TRANSIENT retry policies; async `synthetic_mocked_advisor` (deadlock fix); `ff15_cycle_runs_rls_coverage` (scanner-visible policy); OpenAPI golden regenerated (stale loop-console routes) | `cycle_runs` snapshot seam (4A/4B), `CycleOrchestrator.run_one_stage`, Temporal `build_worker`, RLS pattern `b7c8d9e0f1a2` | `test_phase4_*`+`tests/temporal` (23) [V], full non-temporal regression (1445) [V], compileall [V], live containers polling `nazm-execution` [V] |
| 4E Persisted-cycle revalidation | a resumed `CycleRun` may NOT advance past its pinned baseline when the resume evidence can no longer reproduce it: `CycleOrchestrator.revalidate_persisted(run)` recomputes `project_state` version + evidence watermark from the resume store and compares to persisted `starting_state_version`/`evidence_watermark`; drift or cross-scope → verdict `ok=False` → `business_cycle_advance` blocks (`blocked=True`, `state_output["revalidation"]` persisted, no stage attempt consumed); not-yet-pinned runs (pre-STATE_PROJECTION) are allowed (`not_pinned`); clean same-evidence resumes stay `consistent` | `cycle_runs` snapshot seam (4A/4B), `CycleOrchestrator` from 4D, `_state_version` + `project_state` (state.py), `EvidenceRecord` checksum/idempotency (evidence.py), `_rebuild_evidence` | `test_phase4_cycle_revalidation.py` (6) [V], `tests/temporal` Scenario F (7 total) [V], full non-temporal regression (1445) [V], compileall [V] |
| 4F Verified outcome linkage | executed action → `OutcomeRecord` → measurement → verification → existing `OutcomeLedger` V1: `verify_outcome` VERIFIED now requires measured impact + DISTINCT baseline/post state versions (identical reused snapshot never VERIFIED); `learning_eligibility` gates `attribution_sufficient` + `state_versions_not_distinct`; `_stage_learning_eligibility` flags are COMPUTED (tenant-authorized, fresh watermark, attribution-sufficient) and `outcome_linkage` persisted; `business_cycle_advance` attaches once per execution — key = sha256(tenant:execution_key:recommendation_id:recommendation_version)[:24], idempotent (V1 `ON CONFLICT` + persisted `outcome_recorded` marker), readback-confirmed via `OutcomeLedger.row()`, tenant-scoped (`tenant_unscoped` refused), Jev advisory alone never sufficient, unknown/pending executions never attach | `OutcomeLedger` V1 record + `record_verified_result` + `OutcomeRecord`/`verify_outcome` + `learning_eligibility` (all existing), `cycle_runs.state_output` seam (4A/4B), `/* Phase 4F — the gates are COMPUTED */` in `_stage_learning_eligibility` | `test_phase4_outcome_linkage.py` (30) [V], `tests/temporal` Scenario G (28 total) [V], full non-temporal regression (1481) [V], compileall [V] |
| 4G Tenant-scoped read-only Loop Console | read-only projection over persisted `cycle_runs.state_output` (+ existing V1 `OutcomeLedger`): `loop_console_readmodel.py` (`READ_MODEL_VERSION="1.0"`, 7-step lifecycle ladder, banded list summaries, owner detail with exact observed/potential impact + `impact_delta_sar` only when expected known, 21-stage timeline, recovery, outcome_key via `outcome_linkage`/`outcome_recorded`); `cycle_run_repository.page()` bounded + deterministic sort + `outcome_keys()`; `/api/v1/loop-console` GET-only router with `_scoped_verified_rows` fail-closed + `assert_business_access` (cross-tenant 403, owner unknown-id 404); frontend `/loop` page (RouteGuard, no capability require), middleware `"loop"` auth, Sidebar/MobileNav entries | existing `cycle_runs.state_output` seam (4A/4B), `OutcomeLedger` V1 `verified_outcomes` (unchanged; no second store), `assert_business_access` (Phase B) | `test_phase4_loop_console.py` (17 passed, 6 PG-gated) [V]; 3K string-contract `test_loop_console.py` green [V]; full non-temporal regression (82, all skips PG) [V]; security suite 189 passed [V]; IDOR extension + Section B staged PENDING-PG [~]; frontend tsc clean, eslint 0 errors, jest 7/7 [V]; compileall clean [V]. Detail: `PHASE_4G_REPORT.md` |
| 4H/4I | Hardening — NORMAL + PARTIAL FAILURE + RETRY + REPLAY + RESTART + CONCURRENCY converge on one truth: shared `CycleRunConflictError` (single source in `cycle.py`); `start()` returns the EXISTING run for a duplicate trigger token incl. completed (terminal never regresses; new logical cycle = new token); `run_one_stage` safe-convergence (already-`ok` stage advances WITHOUT re-running the handler; persisted `running` EXECUTION converges to a guarded unconfirmed receipt, never blind-re-run); `InMemoryCycleRepository` = deep-copy store + per-row version + terminal immutability (DB-free concurrency tests carry the SAME semantics as Postgres); `_saved_snapshot` rehydrates the REAL projected baseline via `BusinessStateSnapshot.from_dict`; reconciliation adds `status="unknown_external_outcome"` + `reconciliation_required=True` (additive; `allow_retry`/`reason` untouched) and verification hard-guards it → `unverified`; approval persists `approve_binding` `binding_key` and EXECUTION re-derives + refuses on `approval_material_mismatch`; `record_verified_result` rowcount-aware (absent row → False, phantom never verified) | the SAME canonical pieces hardened: `CycleOrchestrator`/`cycle_runs` + `CycleRun.reconcile` (4D/4E), `OutcomeLedger` V1 + `attach_outcome` readback (4F), `approve_binding`/`evaluate_governance` (4C), `loop_console` read surfaces (4G, untouched) | **ACCEPTED** — `PHASE_4H_FAILURE_MATRIX.md` (4H-A) [V]; `tests/test_phase4_hardening.py` **25 passed** [V] (CRASH 1–8 + G1–G7 mapped); Phase 4 aggregate DB-free **49 passed** [V]; **4H-P real Postgres** (nazmos_test @ ff15, `tests/test_cycle_run_repository.py` + hardening) **32 passed** [V]; **4H-S real Temporal dev-server + Postgres** `tests/temporal` **28 passed, 0 skipped** [V]; full gate `test_security_acceptance.py + phase4 + security` **248 passed, 0 errors** [V]; compileall clean [V]. Detail: `PHASE_4H_HARDENING_REPORT.md` |

## 31. Phase 4 final verdict — CONDITIONALLY PILOT READY [V]

**VERDICT: DOUBLE-GREEN for a synthetic single-tenant pilot in SHADOW / MOCKED
mode; the real-outcome pilot is CONDITIONALLY READY (conditions C1–C3).**
Phase 4's continuous Business Improvement Loop is durable, observable,
deterministic, tenant-bounded, restart-safe, and converges on ONE business truth
across NORMAL + PARTIAL FAILURE + RETRY + REPLAY + RESTART + CONCURRENCY —
re-verified end-to-end in the final gate session, INCLUDING a freshly re-brought-up
real Temporal server.

- **CORE EVIDENCE (final gate, in-session [V])**: `backend/tests/phase4` **43 passed** (4I-M 11 + 4I-N 12 + 4I-D 6 + 4I-Q/R/S 6); PG gate `test_cycle_run_repository.py` **7** + loop_console/RLS/celery **73** + `test_security_acceptance.py` **9**; `tests/security` **237**; 4H aggregate **133**; strict dispatch + sqlite **16**; `test_ai_isolation.py` **15** (post `supplier_risk`); **Temporal (real server + Postgres) 29 passed / 0 skipped [V]**; full backend gate ~1540 + openapi golden 1 [B]; frontend 72 tests / lint 0 errors / build EXIT=0 [B].
- **CONDITIONS (C1–C3, open)**: C1 real Jev API key + live smoke; C2 live external execution behind `EXECUTION_ENABLED` with real owner-auth identity; C3 refresh full Postgres + Temporal gates on the go-live branch.
- **JEV MODE**: SHADOW / MOCKED — `JEV_LIVE=False JEV_ENABLED=False` probed honestly; unconfigured Jev fails closed (`fallback` + `jev_not_configured`, decision basis preserved); out-of-contract suggestions dropped + flagged; mock/fallback never labelled jev.
- **GOVERNANCE**: deterministic only (`deterministic-governance` certificate); approval simulated (`simulated_owner_approval`); AI never authorizes/approves.
- **EXECUTION SAFETY**: in-loop EXECUTION = dry-run surrogate (`synthetic=True`) AND runner kill switch `EXECUTION_ENABLED` raises `ExecutionDisabledError` when OFF; unconfirmed external receipt after restart is guarded, never blind re-run.
- **RECOVERY / BACKUP**: restart converges without duplicate effect (S1/N2); restore reconstitution deterministic — identical evidence → identical version+watermark, divergence detectable (S2); terminal cycles immutable, concurrency via `CycleRunConflictError`.
- **RESTRICTED (go-live commissioning, explicitly NOT declared here)**: real Jev API key + live smoke; live external execution behind `EXECUTION_ENABLED` with real owner-auth identity; real (non-simulated) owner approval. Re-run full Postgres + Temporal gates at go-live.

Detail: `PHASE_4I_FINAL_ACCEPTANCE_REPORT.md` · `PHASE_4I_ACCEPTANCE_MATRIX.md` ·
`PHASE_4I_REPOSITORY_AUDIT.md` · `PHASE_4I_PILOT_SCOPE.md` ·
`PHASE_4I_PILOT_AUTONOMY_POLICY.md` · `PHASE_4I_PILOT_DATA_CONTRACT.md` ·
`PHASE_4I_OPERATIONS_RUNBOOK.md` · `docs/PILOT_OPERATIONS_RUNBOOK.md` (repo).
| 4I Pilot readiness | the FULL pilot closure on the hardened loop: rehearsal across all 21 stages on synthetic tenant/business (also `biz-imm`/`biz-sum`), with az-verified biz propagation (a run for one business can never read another's evidence — scoped `_ingest`/`_orchestrator`; async mock advisor); failure drills A–L (stage-ahead, cross-scope, revalidation drift block, terminal re-start returns existing run, approval-material mismatch refusal, unconfirmed external receipt after restart — guarded, no blind re-run, no duplicate effect, kill-switch `ExecutionDisabledError`, verified-only learning, Jev-fallback provenance, end-state pull-back); Jev readiness probe (env truth `JEV_LIVE=False JEV_ENABLED=False`, unconfigured → `fallback`+`jev_not_configured` determinant preserved, shadow mode keeps deterministic final + DLP-clean outbound via stub transport, out-of-contract dropped+flagged, mock/fallback never labelled jev); ops drills Q1/Q2 (DB-free read model full observability incl. honest `execution.synthetic=True` + `approval.mode=simulated_owner_approval` + unknown external outcome `unverified`+`reconciliation_required` + `unconfirmed_external_outcome_after_restart`), R1/R2 (`EXECUTION_ENABLED` real config surface, in-loop dry-run only), S1/S2 (persisted completed run round-trips critical fields; restore reconstitution deterministic — identical `starting_state_version`+`evidence_watermark` — divergence detectable) | the SAME canonical surfaces — `CycleOrchestrator`/`cycle_runs` (4D/4H), `consult_advisory`/`deterministic_only_advisor` + `ai_gateway.systemone_reason` shadow (4C), `approve_binding`/`evaluate_governance` (4C/4H), `loop_console` read model (4G), `systemone_reason`/`jev.consult` fail-closed (4C) | **ACCEPTED — CONDITIONALLY PILOT READY (shadow/mocked mode green; C1–C3 open)** — `backend/tests/phase4` **43 passed** [V] (4I-M rehearsal **11** + 4I-N drills **12** + 4I-D Jev readiness **6** + 4I-Q/R/S ops **6**); full-4I detailed evidence in `PHASE_4I_ACCEPTANCE_MATRIX.md` + `PHASE_4I_FINAL_ACCEPTANCE_REPORT.md` (repo root). Explicit limitations: Jev not live (shadow/mocked only, honest labels), live external execution intentionally not exercised, owner approval simulated — all documented for the go-live commissioning step |