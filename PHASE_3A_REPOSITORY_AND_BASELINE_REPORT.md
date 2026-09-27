# PHASE 3A — Repository Mapping and Baseline

Status: GREEN (baseline) — Phase 3 implementation plan established.
Date: 2026-09-24
Branch: `phase1-core-infra-replacements` @ `6078008` (working tree, uncommitted)
Evidence labels: [V] verified by executed check, [B] repository evidence, [I] inference/proposal, [X] blocked, [!] risk.

---

## 1. Scope

Repositories the Continuous Business Improvement Loop (CBIL) must REUSE rather
than duplicate. This report records: (a) ground truth, (b) an architecture-to-
repository mapping for every CBIL stage, (c) the blocker ledger, (d) the
dependency graph, (e) the implementation sequence, and (f) the baseline.

No Phase 3 code was written yet. This is the reconnaissance + dependency-graph
phase required by the master directive §5–§6.

---

## 2. Ground truth (verified this session)

| Item | Value | Evidence |
|---|---|---|
| Repo root | `H:/NAZMOS_COMPLETE_LATEST/NAZMOS_LATEST_MERGED` | [V] `git rev-parse --show-toplevel` |
| Branch | `phase1-core-infra-replacements` | [V] |
| HEAD | `6078008` (test(analytics): repair coverage-aware health_score seed) | [V] |
| Working tree | 80+ modified tracked files, ~90 untracked (Phase 1/2 artifacts, reports, tests) | [V] `git status --short` |
| Compile gate | `python -m compileall -q app tests` → exit 0 | [V] |
| Python | 3.14.4; deps (temporalio, duckdb, aiosqlite, sqlalchemy, pytest) import ok | [V] |
| Postgres | `postgres:17-alpine` container `nazmos_latest_merged-postgres-1` HEALTHY; `SELECT 1` ok on `nazmos_test` | [V] |
| Redis | HEALTHY | [V] |
| Temporal | container `nazmos_latest_merged-temporal-1` reports **unhealthy** but 7233 LISTENS (172.31.0.4:7233) and host `Test-NetConnection 127.0.0.1:7233` → True; healthcheck probes `127.0.0.1/7233` in-container where the frontend binds the container IP → **healthcheck config bug, not a server failure** | [V][!] |
| Git remote | present (github.com/RayAKaan/NazmOS); **no commits made by this workstream** | [B] |

Key environment facts carried from Phase 2 (all re-verified this session where possible):
- Postgres role password realigned to `nazmos_v5_dev` (non-destructive `ALTER ROLE`); the
  compose postgres stanza still declares `POSTGRES_PASSWORD: nazmos_dev` (docker-compose.yml:10)
  while temporal + tests use `nazmos_v5_dev` (docker-compose.yml:42, AGENTS.md). [!]
- compose `nazmos-worker` container is currently stopped (it polled the same `nazm-execution`
  task queue with the stale credential and raced real Temporal runs). Compose `api`/`nazmos-worker`
  stanzas still hardcode `nazmos_dev` → they would fail auth if restarted. Left per no-destructive-ops rule. [!]
- WSL relay Postgres on `::1:5432` (wslrelay) is distinct from Docker postgres on `0.0.0.0:5432`.
  Always use explicit `127.0.0.1` in URLs to avoid ambiguity. [V]

---

## 3. Architecture-to-repository mapping (CBIL stages)

The master loop stage | Existing implementation (reusable) | Reusable? | Missing behavior | Evidence
---|---|---|---|---
SOURCE SYSTEM OBSERVATION | `app/services/event_engine.py` (`ingest_event`, checksum SHA-256, `BUILTIN_EVENT_SCHEMAS` validation); `Event`/`EventType`/`EventSubscription` models; `app/schemas/events.py` | YES | zero synthetic-seed helper for tests; tenant resolution already in middleware | [B]
INGESTION | `app/services/event_processor.py` (dedupe on business_id/source/source_id/checksum); `app/services/etl_pipeline.py`; `app/services/data_normalizer.py`; `app/services/schema_detector.py`; `app/services/file_ingestion.py` | YES | durable ingestion-status/quarantine table is absent (events go straight to DB) → **3B gap** | [B]
VALIDATION + NORMALIZATION | event schema validation (`_validate_payload`); `evidence_package.py` (`ItemEvidence`, `AuditEvidencePackage`, `build_item_evidence`); `outcome_feedback_contract.py` | YES | a single normalized "accepted evidence row" abstraction linking observation→capsule hash | [B]
EVIDENCE LEDGER | `Event` rows + checksum; `EventDerivation` model; `evidence_package` capsule-hash references; `security/privacy_firewall.py` `ReasoningCapsule` (signed, DLP-clean) | YES | provenance/quality/flags columns on events; freshness metadata | [B]
VERSIONED BUSINESS STATE | `app/services/business_memory.py` (`memory_type` docs, optimistic `version` counter, `set_memory_path` version++ + `MemoryUpdate` audit row, `replay_events_to_memory` deterministic replay); `business_context.py`/`business_context_service.py`; `time_machine.py` (estimated); `regime_detection.py` | PARTIAL | NO per-business **state_version** composite; no state snapshot with evidence lineage across domains; no "missing≠zero / stale≠current" gates at the state layer → **3C gap** | [B]
DETERMINISTIC OPPORTUNITY DETECTION | `app/services/audit_core.py` (`analyze_product`, `gross_margin_pct`, `coverage_aware_daily_velocity`); `money_audit_service.py` (`compute_money_audit` → per-action `financial_model`/`evidence`/`financial_impact_type`); `recovery_match_service.py` (`generate_preview` → surplus items ≥30d supply, `estimated_recovery_value_sar`); `audit_engine.py` (`compute_urgency`); `anomaly_detector.py`; `margin_erosion.py`; `reorder_urgency.py` | YES (the detection math exists, scattered) | NO unified **Opportunity** record (id, type, state_version, evidence refs, detection-rule version, impact buckets, lifecycle status). De-facto surfaces: money-audit actions, recovery previews, findings → **3D gap** | [B]
DETERMINISTIC IMPACT | `money_audit_service` financial-impact types (CAPITAL_AT_RISK / REVENUE_AT_RISK / RECOVERABLE_OPPORTUNITY / SEASONAL / HEALTHY); `impact_ledger_service.py` (`impact_ledger` table, `verification ∈ pending/estimated/observed`, `attribution ∈ direct/partial/business_level/estimated/unattributable`); `financial_vocabulary.py` | YES | impact **kinds** (potential/expected/approved/executed/verified) not all modeled on one record; estimates already kept distinct from observed | [B]
REGISTERED ACTION CANDIDATES | `app/services/action_registry.py` `ACTION_REGISTRY` (9 actions: discount/reorder/recovery_match/margin_fix/transfer_inventory/restock/pricing_increase/pricing_decrease/expiry_alert) + `get_action_spec` + `can_execute`; `app/orchestration/contracts.py` `CANONICAL_ACTION_TYPES` (23) | YES | candidate list produced only by specific surfaces; no generic "eligible action categories for this opportunity" | [B]
JEV TYPED ADVISORY | `app/services/canonical_controller.py` (9 surfaces: canonical_rank/_action_type/_root_cause/_stockout_tier/_anomaly_triage/_reorder_urgency/_margin_erosion/_finding_priority; `canonical_decision` verify-then-finalize); `app/services/ai_gateway.py` (`systemone_reason`, Jev-first, shadow-only, fail-closed, `allowed_suggestions` contract gate); `app/services/ai_providers/jev.py` (typed Choice/Score/Noul, advisory only); `app/services/shadow_capture.py` (JSONL parity); `app/services/ai_budget.py` | YES | provider attribution + fallback already recorded (`source`, `provider`, `model`); the capability-specific fallback chain (Jev→OpenCode→LLM) is not yet a registered policy object → **3E verification step** | [B]
CONTRACT + DOMAIN VALIDATION | `canonical_controller` `_validate_*` output gates (JEV_OUT_OF_CONTRACT on discard); `ai_response_validator.py`; `output_gate.py`; `capabilities_service.py` | YES | consolidated typed-capability contract object (input/output/allowed values) per capability | [I]
RECOMMENDATION CONSTRUCTION | `app/services/decision_engine.py` (DecisionEngine generate/explain); `nazm_planner.py`; `planning_engine.py` (`create_plan`); `decision_scoring.py`; `IntelligenceDecision` model (`candidate_actions`, `ranked_action`, `confidence`, `risk_score`); `Plan` model; `finding_service.py` lifecycle (detected→…→approved→executing→completed→verified) | PARTIAL | NO versioned **Recommendation** object binding opportunity+state_version+evidence+impact-formula-version+action-contract-version+Jev-advisory-ref+policy-version+approval-requirements+expiry; no explicit lifecycle statuses (validated/policy_evaluated/awaiting_approval/reconciling/verifying/superseded/expired/disputed) → **3E gap** | [B]
GOVERNANCE + SHARIAH | `app/security/ai_policy.py` (capability flags); `app/services/policy_engine.py`; `app/services/autonomy_service.py` (dial ∈[0,100], ceilings, quiet hours, 2FA threshold); `app/services/constraint_service.py` (`filter_action`); `app/services/execution_guard.py`; `app/services/shariah_compliance.py`; `app/services/finding_approval_service.py` | YES | versioned policy evaluation row per recommendation; deterministic governance outcomes object (permitted/denied/review/approval/deferred) bound to policy version | [B]
OWNER APPROVAL | `agent.py`/`whatsapp.py` approval flows → `orchestration/runner.py` `run_agent_approval`; `approval_authorization` tests (test_approval_authorization.py) | YES | approval binding to EXACT recommendation version + material-parameter hash; stale-approval rejection at the recommendation layer | [B]
PRE-EXECUTION REVALIDATION | `orchestration/precheck.py`; `execution_guard.py`; `can_execute` | YES | revalidation asserting current state_version == recommendation state_version (stale-state gate) | [I]
REGISTERED ACTION EXECUTION | `app/orchestration/` (runner, keys, workflows, apply, record, operations, retry, temporal/{activities,worker,workflows,policies,schedules}); `ExecutionJob` model; Temporal `ManualActionWorkflow`/`AgentApprovalWorkflow`/`SimulatedWorkflow`; idempotency `derive_execution_key` (SHA-256) | YES | temporal schedules exist (drain, pos_sweep, learning_reconciliation, daily crons) | [B]
RECONCILIATION | `learning_reconciliation.py` (terminal-action ↔ LearnedOutcome+OutcomeFeedback); `outcome_tracker.py`; `money_audit_service.update_action_status` (VALID_TRANSITIONS, prediction_error_pct, measurement_window_days) | PARTIAL | requested-vs-actual execution reconciliation gating **retries** (only learner reconciliation exists) → **3H gap** | [B]
OUTCOME VERIFICATION | `outcome_ledger.py` (V1 SQLite, `record`, `record_verified_result`, `verified_outcomes` verified=1 only, idempotent on sha decision_key, DLP-clean); `impact_ledger_service`; `finding_service.verify_finding` (`verification_result {verified, actual_impact_sar, note}`) | YES | verification states (reported/observed/verified/partially/disputed/unverified) as an enum on the loop record — partially present (unknown/confirmed/partial/failed/rejected in ledger) | [B]
VERIFIED OUTCOME LEDGER | `outcome_ledger.py::OutcomeLedger` (reuse; **do NOT create parallel ledger**) | YES | none significant | [B]
BOUNDED LEARNING | `outcome_learning.py` (`record_unified_outcome`); `learning_reconciliation`; `learning_engine.py` (model_performance, thompson bandit); `learning_engine_advanced.py`; `learned_outcomes` model; `business_memory`/`branch_memory`/`product_memory`/`supplier_memory` | YES | explicit learning-eligibility gate object (traceability + verified + authorized + quality + provenance + contract) | [B]
UPDATED BUSINESS STATE | `business_memory.set_memory_path` version++ + MemoryUpdate audit; `event_processor` reprojection | PARTIAL | state refresh ties to new state_version (3C) | [B]
NEXT CYCLE | `orchestration/temporal/schedules.py` (DEFAULT_SCHEDULES); `services/runtime.py` run_agent loop; `services/orchestrator.py` run_orchestrator | PARTIAL | **NO explicit bounded, resumable, idempotent Cycle orchestrator** (stable cycle_id, stage tracking, retry budget, cooldowns, pause/resume, duplicate-trigger suppression) → **3I gap** | [B]

Cross-cutting (mostly present, must be preserved):
- Tenant isolation: `rls_tenant.py` middleware + `assert_business_access`; security tests green. [V]
- Auditability: `audit_log_service`, `security_events`/`ai_reasoning_requests`, `audit_core`. [B]
- Idempotency: `derive_execution_key`; ledger upserts; memory replay. [B]
- Observability: `telemetry.py`, `agent_observability.py`, `health_metrics.py`, `tracing.py`. [B]
- Versioning: `BusinessMemory.version`, `plan` versions, `IntelligenceDecision`; no composite business state_version. [B]
- UI transparency: dashboard/intelligence routers + Next.js frontend; no dedicated "loop console". [B]

---

## 4. Gaps requiring NEW code (consolidated)

| Gap | Phase | New artifact | Reuse |
|---|---|---|---|
| G-3B evidence freshness/quality/provenance | 3B | evidence-quality flags + freshness schema over existing `Event` rows | event_engine, evidence_package |
| G-3C versioned business state | 3C | `BusinessStateSnapshot` service: composite state_version, domain values, evidence lineage, freshness/missing flags | business_memory replay, context_engine |
| G-3D unified Opportunity | 3D | `Opportunity` record + `OpportunityEngine` (deterministic; rule version; impact buckets) | audit_core, money_audit, recovery_match.generate_preview |
| G-3E Recommendation lifecycle | 3E | versioned `Recommendation` + explicit lifecycle state machine | decision_engine, finding_service lifecycle, IntelligenceDecision |
| G-3E Jev contract object | 3E | TypedCapabilityContract per capability (input/output/values/fallback rules) | canonical_controller contracts, ai_policy |
| G-3H execution reconciliation | 3H | requested-vs-actual reconciliation gating retries at the orchestrator | orchestration/keys, money_audit VALID_TRANSITIONS |
| G-3I cycle orchestrator | 3I | `CycleOrchestrator`: stable cycle_id, stage ledger, idempotent triggers, retry budget, pause/resume, stale gates | temporal schedules, runner |
| G-3K loop console | 3K | read-only owner endpoints over the loop artifacts | dashboard/intelligence routers |

---

## 5. Blocker ledger

| # | Blocker | Impact | Status | Workaround |
|---|---|---|---|---|
| B1 | compose postgres stanza password `nazmos_dev` vs role `nazmos_v5_dev` mismatch | `docker compose up` api/worker stanzas would fail auth | OPEN [!] | env-URLs use `nazmos_v5_dev`; compose stanzas left untouched (no-destructive-op) |
| B2 | compose `nazmos-worker` stopped | no background task-queue worker | OPEN (documented) | real Temporal tests start an in-process worker (conftest) → zero skips |
| B3 | Temporal container healthcheck probes wrong host | `docker ps` shows unhealthy | OPEN [!] config bug | verified 7233 reachable from host; suites connect to `127.0.0.1:7233` and pass |
| B4 | no Jev live endpoint credentials / no OpenCode compat contract asserted | live fallback chain unverifiable | OPEN | shadow mode only; mocked Jev in synthetic slice, explicitly labelled |
| B5 | no composite business-state version | 3C must invent minimal version contract | OPEN | build `BusinessStateSnapshot` deterministically on top of memory replay |
| B6 | `procurement.supplier_risk` deferred in Phase 2 | not a CBIL blocker | closed (deferred) | documented |

---

## 6. Dependency graph (implementation order)

```
Evidence foundation (3B)
      ↓
Versioned Business State (3C)
      ↓
Opportunity Engine + Impact (3D)
      ↓
Jev Gateway contract + fallback verification (3E-part)
      ↓
Recommendation Lifecycle (3E-part)
      ↓
Governance + Shariah (3G)
      ↓
Execution + Reconciliation (3H)
      ↓
Outcome Verification + Learning (3I)
      ↓
Cycle Orchestrator (3I)
      ↓
Owner Command Center + Security/Observability (3K)
      ↓
Synthetic Vertical Slice e2e (3L) → Final acceptance
```

Tests layered per master directive §20: unit (deterministic fns/schemas) → contract
(adapters, action contracts, lifecycle transitions) → integration (DB/RLS/Temporal) →
e2e (complete synthetic loop) → failure-injection (timeouts, stale state, partial
execution) → regression (existing suites).

---

## 7. Baseline (verified this session)

| Gate | Command | Result |
|---|---|---|
| Compile | `python -m compileall -q app tests` | exit 0 [V] |
| Fast gate (Postgres env set) | `pytest tests/security tests/phase4 tests/test_canonical_controller.py tests/test_outcome_ledger_v1.py tests/test_orchestration.py` with `USE_TEMPORAL=false`, `DATABASE_URL`/`TEST_DATABASE_URL` → `nazmos:nazmos_v5_dev@..nazmos_test` | **260 passed**, 0 failed, 0 errors, 290 warnings, 228.70s [V] |
| Same gate WITHOUT DB env | 227 passed + 33 `InvalidPasswordError` setup errors | the 33 are Postgres-backed suites needing `DATABASE_URL`/`TEST_DATABASE_URL` (test_idor_cross_tenant, test_celery_rls_tenant_context, approval/autonomy agent-action tests) [V] |
| Collection | same command `--collect-only` | 260 tests collected, 0.44s [V] |
| Postgres | `psql ... -tAc "SELECT 1"` on nazmos_test | `1` [V] |
| Temporal | `Test-NetConnection 127.0.0.1:7233` | True [V] |

Baseline is GREEN. The DB-free-vs-DB-backed distinction is the only quirk: security
RLS/IDOR/approval suites require a reachable migrated Postgres at the env URLs.

---

## 8. Implementation sequence (smallest coherent change per phase)

1. **3B Evidence** — add `evidence_quality` fields/freshness to a wrap layer (no schema change to Event; new reading helper).
2. **3C Business state** — `business_state.py`: `BusinessStateSnapshot` built from `business_memory.get_memory` replay; composite `state_version`; flags for missing/stale/partial; lineage refs to event checksums.
3. **3D Opportunity** — `opportunity_engine.py`: pure functions over a state snapshot emitting `Opportunity` records (type, rule_version, evidence refs, potential/expected impact). Reuse thresholds (margin ≥0.22 target, surplus ≥30d & ≥SAR500, stockout <5d supply) as constants already present.
4. **3E Recommendation** — `recommendation.py` lifecycle + versioning + approval-version binding; `typed_capability.py` contract objects; reuse `canonical_decision` for the advisory step (shadow).
5. **3G Governance** — deterministic evaluation binding recommendation → policy_version + outcome; approval binding (hash of material params).
6. **3H Execution/Reconciliation** — reuse `orchestration.runner` + `derive_execution_key`; add requested-vs-actual reconciliation at orchestrator level (no blind retry).
7. **3I Verification/Learning** — reuse `OutcomeLedger` (record → record_verified_result → verified_outcomes) + `learning_reconciliation` eligibility; no new ledger.
8. **3I Cycle orchestrator** — `cycle_orchestrator.py`: idempotent trigger, stage state machine, resume, cooldown, stale gates. Reuse temporal schedules for triggers.
9. **3K Command Center/Observability** — read-only endpoints + metrics.
10. **3L Synthetic vertical slice** — full loop e2e with synthetic data, mocked Jev explicitly labelled, dry-run execution marked synthetic; authority-boundary assertions (AI cannot authorize, estimates ≠ verified, etc.).
11. **Final** — PHASE_3_FINAL_ACCEPTANCE_REPORT.md; MIGRATION_MATRIX Phase 3 section.

---

## 9. Security / authority / data-migration implications

- No AI output authorizes anything: deterministic decision always final (reuse `canonical_decision`). [B]
- No new secret material; reused creds come from env. No secrets in this report. [V]
- No destructive DB/Temporal operations performed. Postgres role password change was Phase 2-documented, non-destructive. [V]
- New loop artifacts must stay DLP-clean (capsule hashes, no raw merchant ids beyond sha keys). [B]
- No `rls` change planned; existing RLS + `assert_business_access` cover the new read endpoints. [B]
- New tables (if any) will follow the existing Alembic chain (`ff13_*` present, alembic used by `migrated_db` fixture). Prefer SQLite-file ledger reuse (outcome_ledger pattern) to avoid migration churn unless a shared-DB model is required. [I]

---

## 10. Completion status

Reconnaissance, mapping, baseline, dependency graph, and sequence are COMPLETE.
Phase 3 implementation starts at 3B (Evidence) and proceeds per §8.