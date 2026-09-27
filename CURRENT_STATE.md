# CURRENT_STATE.md

**What the repository actually is, and where it is right now.**

Date: 2026-09-20 (Phase 0 reality audit). All facts carry an evidence label. No fixes or migrations were performed.

## 1. Repository identity

- Repo root (git): `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\` [VERIFIED]
- Parent `H:\NAZMOS_COMPLETE_LATEST\` is NOT a git repo [VERIFIED]
- Remote: `https://github.com/RayAKaan/NazmOS` (remote `origin`) [HISTORICAL from prior session; remote verified as rejected push occurred to `origin/phase1-core-infra-replacements`]
- Branch: `phase1-core-infra-replacements` [VERIFIED]
- HEAD: `208ca04 phase2c: canonical decision/action serialization and outcome feedback contract` [VERIFIED]
- Recent history: `208ca04` → `5b92151` (merge of `origin/main`) → `a49b2c5` (phase2b velocity migration) → `8353de4`/`6c0166b` (docs/ci) → `bf5cdd6` (phase1 closeout) [VERIFIED via `git log`]

## 2. Working tree state (NOT committed)

`git status --short` — 143 entries:
- **58 modified** files (` M`), **6 deleted** (` D`, includes `backend/app/celery_app.py`), **79 untracked** (`??`) [VERIFIED]

The so-called "Phase 1 wave" is largely **uncommitted**: Temporal-orchestration files, Celery removal, docker-compose variants, telemetry, config, and a large pile of operator tooling under `docs/` (`align_temporal_pwd_*.ps1/.out`, etc.), plus new untracked orchestration code:
- `backend/app/orchestration/operations.py` (untracked, exists on disk, referenced by other code) [VERIFIED]
- `backend/app/orchestration/temporal/schedules.py` (untracked) [VERIFIED]
- `backend/tests/test_temporal_deployment.py` (untracked) [VERIFIED]
- `backend/alembic/versions/ff13_drop_celery_upload_task.py` (untracked migration) [VERIFIED]
- `docker-compose.temporal-pw-fix.yml` (untracked) [VERIFIED]
- `docs/phase2b_baseline_gate_report.md`, `docs/phase2b_final_report.md`, `backend/docs/phase2a_*.md` (untracked) [VERIFIED]

## 3. CRITICAL: the repository does not compile or import today

`python -m compileall -q app tests` (run from `backend/`) **FAILS** (exit 1) [VERIFIED — actually executed this audit]:

1. `backend/app/services/intelligence_api.py` — `IndentationError: unindent does not match any outer indentation level` at line 235. The region at lines 228–243 is corrupt: `if target == "demand" and item_id:` at column 0 after the 4-space function body, with a 12-space suite and a column-8 `return {`. [VERIFIED]
   - **HEAD version compiles** [VERIFIED: `git show HEAD:backend/app/services/intelligence_api.py` is correctly indented].
   - The break exists only in the **uncommitted working-tree edit** (diffstat vs HEAD: 27 lines, 8 insertions/19 deletions) [VERIFIED].
2. `backend/tests/test_analytics_health_score.py` — `SyntaxError: 'await' outside function` at line 95. `_seed()` body dedents to column 0 after `db.add_all(items)` (lines ~59–95). [VERIFIED]
   - This break is **already committed at HEAD** (`a49b2c5`) — `git show HEAD:` contains the same module-scope `await db.flush()` [VERIFIED, exact match].

**Cascade:** `intelligence_api.py` is imported by `intelligence_api_client.py:15`, which is imported by the routers `agent/chat/dashboard/money_audit/recovery_match` and `analytics_service`; `backend/tests/conftest.py:30` does `from app.main import app` — therefore **the ENTIRE backend test suite currently fails at collection** (pytest aborts with `IndentationError` while loading conftest). [VERIFIED — attempted `pytest` on the documented "fast subset" and reproduced exactly this]

Consequence: **every CI gate that depends on compileall or on the backend test suites is red at HEAD + working tree.** This is the dominant finding and the first thing Phase 1 must fix.

## 4. Live environment

Running locally (docker) at audit time [VERIFIED via `docker ps`]:
- `nazmos_latest_merged-postgres-1` — postgres:17-alpine, healthy, `0.0.0.0:5432`
- `nazmos_latest_merged-redis-1` — redis:7-alpine, healthy, `0.0.0.0:6379`
- `nazmos_latest_merged-temporal-1` — temporalio/temporal:latest, **status "Unhealthy" (3 days)**, port `0.0.0.0:7233` reachable [VERIFIED: TCP connect succeeds]
- `nazmos_latest_merged-nazmos-worker-1` — nazmos worker image, "Up 3 days", but its logs show **continuous gRPC polls failing with `dns error ... Name or service not known`** → the worker is crash-looping on poll retries and is NOT processing task queues right now. [VERIFIED via `docker logs --tail 15`]
- `jev-mvp` and `jev-mvp-pg` — image `jev-support-mvp:latest`, "Up about an hour", ports `0.0.0.0:8000→8000` and `8001→8000`. FastAPI app titled **"JEV Support Decision Infrastructure"** v0.2.0; see `JEV_FEASIBILITY_REPORT.md`. [VERIFIED: `/docs` and `/openapi.json` HTTP 200 on both ports]

Local toolchain [VERIFIED]:
- Python 3.14.4, pytest 9.1.1, `bandit` not installed locally, git working
- PostgreSQL databases present (via `psql -l`): `nazmos`, `nazmos_test`, `nazmos_test_ci`, `nazmos_test_ci2`, `nazmos_test_ci3`, plus `temporal`/`temporal_visibility` [VERIFIED]

## 5. What the code base consists of (headline numbers)

- Backend: FastAPI app under `backend/app/` — 1197 tracked files repo-wide [VERIFIED]
- ~152 test files under `backend/tests/`: 119 flat + 16 `security/` + 6 `temporal/` + 2 `phase4/` + 1 `phase5/` + 1 `phase6/` + 3 `regression/` + 1 `fixtures/` + 1 `load/` + 2 `adversarial/` [VERIFIED]
- 8 domain agents under `backend/app/intelligence/agents/`: recovery, inventory, procurement, pricing, margin, finance, compliance, supplier [VERIFIED]
- No `backend/app/agents/` directory; no `ai_policy.py`/`ai_capsule.py`/`jev_brain.py` under `backend/app/services/` [VERIFIED]
- Zero Jev / TypeSafe / `systemone` references anywhere in `backend/` (source, config, tests) [VERIFIED by grep]

## 6. Critical architecture correction from the audit

**`ai_gateway.reason()` has ZERO production callers.** [VERIFIED]
- Only `tests/security/test_ai_isolation.py:350` calls `gateway.reason`; production imports only `budget_snapshot` (`routers/pilot.py:11`). [VERIFIED]
- The production AI surface goes: `routers/{agent,chat,dashboard,money_audit,recovery_match}` + `analytics_service` → `IntelligenceAPIClient` → `intelligence_api.{reason,analyze,predict}` → `ab_decision_framework`, `ai_reasoning`, `ai_challenge` → **`llm_orchestrator` (Groq `llama-3.3-70b-versatile` / Gemini `gemini-2.5-flash-lite`)**, NOT the policy/budget/capsule gateway. [VERIFIED]
- The gateway (policy kill-switch + `GLOBAL_AI_BUDGET` + `ReasoningCapsule` + OpenCode transport + durable audit) is fully built but currently exercised only by tests. AI policy flags exist (`ai_policy.py` `AI_CAPABILITY_FLAGS`) but the policy gate is only enforced inside `ai_gateway.reason`. [VERIFIED]

This means: extending `ai_gateway.reason` with a Jev/SystemOne transport is **greenfield and safe** (nothing in production today depends on its internal routing), but it ALSO means the "one safe AI interface" is not yet the real production path — Phase 2 must either wire production through the gateway or make the gateway the Jev entry point (recommendation: gateway becomes the Jev entry; keep Groq/Gemini chat where it is).

## 7. Phase / feature status legacies

- **Phase 1 core-infra wave**: in-flight in the working tree (uncommitted). New orchestration files untracked; `celery_app.py` deleted; Temporal remains the declared execution substrate. Worker currently non-functional due to DNS error in the running container (operator env).
- **Phase 2B (velocity canonicalization)**: implementation present (`a49b2c5`); **acceptance NOT green** — the untracked `docs/phase2b_final_report.md` states status **PARTIAL** and lists remaining callers to converge. This audit confirms still-inline `/30` sites: `audit_engine.py:173`, `inventory_orchestrator.py:46`, `nazm_planner.py:486`, `intelligence_api.py:233`, `root_cause.py:38/110` (patched), `evidence_package.py:188` (synthetic-only). Canonical fn: `audit_core.py:58`.
- **Phase 2C**: `contracts.py` (2C-A) and `outcome_feedback_contract.py` (2C-B) committed at `208ca04`; 2C-C (cleanup/convergence) not started; acceptance never executed.
- **RLS**: enforced via `SET LOCAL app.current_tenant_id` + `SET LOCAL ROLE` (`database/connection.py:179-197`, per-session and per-transaction listeners); `DATABASE_APP_ROLE` config-driven, literal `nazmos_app` supplied by env. The WhatsApp approval tenant-scope gate test exists (`tests/test_rls_enforcement.py::test_whatsapp_webhook_approval_is_tenant_scoped_under_rls`) but is currently **uncollectable** because of the app-import break.
- **Admin/dev containers**: `nazmos` + `nazmos_test` present; several stale `nazmos_test_ci*` schemas remain.

## 8. Historical gate numbers (untracked docs) — for context, NOT current status

- `docs/phase2b_baseline_gate_report.md`: 179 passed, 1 failed — the failure was the RLS WhatsApp test failing on "Temporal connect to localhost:7233 refused" (environment, not code). [HISTORICAL]
- `docs/phase2b_final_report.md`: status PARTIAL (velocity convergence incomplete). [HISTORICAL]
- These must NOT be read as current: the tree has since changed and now fails compile/collection.

## 9. Corrected facts vs earlier assumptions

- Prior claim "ai_gateway is the one production AI choke point" — **incorrect**; production chat/analyze bypasses it today. [VERIFIED, above]
- Prior claim "Phase 2B implementation complete / acceptance pending" — **partially wrong**; implementation committed but reconciliation leftovers remain and the tree does not compile. [VERIFIED]
- "Dead-stock thresholds inconsistent: 30/45/60 days" — the verified discrepancy is **45 vs 30**: `DEAD_STOCK_DAYS = 45` (`audit_core.py:28`, `money_audit_service.py:20`) vs 30-day-based scans `execute_agent_tool("get_dead_stock_summary", {"days_no_sale": 30})` (`audit_engine.py:127`, `goal_service.py:79`) and 30-day default analytics window (`analytics/repository.py:51`, `analytics/contracts.py:75` WS5 rule `< 1 unit sold`). No verified 60-day threshold in dead-stock logic. [VERIFIED]