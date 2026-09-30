# TEST_AND_ACCEPTANCE_GATES.md

**What "green" means for NazmOS, what currently blocks it, and how every gate is measured.**
Evidence labels: [V] verified this audit, [H] historical, [B] blocked.

## 1. CI gates (`.github/workflows/ci.yml`)

| Gate | Command / mechanism | Current status (2026-09-20) |
|---|---|---|
| Python compile | `python -m compileall -q app tests` then `compileall -q ../scripts` | **RED [V]** — `intelligence_api.py:235` (IndentationError) + `test_analytics_health_score.py:95` (await outside function). Reproduced locally. |
| Bandit SAST | `pip install bandit[toml]`; `bandit -r backend/app --exit-zero -f json -o bandit.json`; script fails on medium+ findings | **RED (pre-existing) [V-inspected]** — MEDIUM findings at `backend/app/services/health_metrics.py:117/151/198` (bandit not installed locally; findings from earlier CI evidence). Not to be fixed in Phase 0. |
| gitleaks | pre-commit + CI | Baseline unknown this audit [B] |
| Backend tests w/ PostgreSQL | job `backend-tests`: postgres 17 service + `DATABASE_URL=...nazmos_test`, `USE_TEMPORAL=false`; `pytest -q --ignore=tests/temporal` | **UNCOLLECTABLE [V]** — all collections fail at `conftest.py:30` `from app.main import app` due to the `intelligence_api.py` syntax error (proved by running the documented fast subset). |
| Temporal integration | job `temporal-backend`: real dev server + Postgres, `USE_TEMPORAL=true`, `pytest tests/temporal -q`, grep for "skipped" → fail if any count | **UNCOLLECTABLE [V]** — same import failure. (Container side: Temporal reachable on 7233 but container health "unhealthy"; nazmos worker crash-looping on DNS (`docker logs`); operator env.) |

Local docker services running: postgres:17 (5432, healthy), redis:7 (6379, healthy), temporal:latest (7233 reachable, container unhealthy), nazmos-worker (up but erroring). [V]

## 2. Documented runbook commands (AGENTS.md)

Fast SQLite subset (no Postgres):
```
cd backend
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="false"
python -m pytest tests/test_analytics_health_score.py tests/test_analytics_duckdb_boundary.py tests/test_analytics_dead_stock.py tests/test_analytics_item_detail.py tests/test_scan_consolidation.py -q
```
→ **Fails at collection now** (reproduced: `IndentationError` from `intelligence_api.py` via conftest). [V]

Postgres-backed integration (integration runner only): same env with `TEST_DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test`, `USE_TEMPORAL=false`:
```
python -m pytest tests/test_dashboard.py tests/test_e2e_happy_path.py -q
```
Orchestration/Temporal-substrate fast tests: `tests/test_orchestration.py tests/test_execution_path_clarity.py tests/test_phase5.py ... test_phase8_loop.py`, `USE_TEMPORAL=false` REQUIRED (else `execute_workflow` hangs polling a live server). [V]

Temporal suite (real server + worker): `USE_TEMPORAL=true`, sqlite `DATABASE_URL`, `pytest tests/temporal -q` — 8 pass + 9 Postgres-only skips on sqlite; with Postgres, 17 scenarios, zero skips enforced by CI. [H+V]

## 3. The Phase 2B / 2C acceptance gates (currently blocked)

- `backend/tests/test_rls_enforcement.py` — full Alembic migration chain on a disposable schema in `nazmos_test`, SET ROLE `nazmos_app` RLS proof:
  - `test_owner_bypasses_rls`
  - `test_app_role_isolates_tenant_rows`
  - `test_app_role_new_policies_isolate_findings` (WS2 findings/audit_runs/impact_ledger)
  - `test_app_role_join_policies_isolate_chat_messages`
  - `test_app_role_join_policies_isolate_pos_sync_logs`
  - **`test_whatsapp_webhook_approval_is_tenant_scoped_under_rls`** — the unauthenticated WhatsApp webhook must fail closed under real RLS: correct-tenant button transitions `agent_actions` → `executed`; wrong-tenant button must see zero rows (RLS) and emit ⚠️ denial (statuses asserted at lines 487-491). [V]
  - Historical gate run (`docs/phase2b_baseline_gate_report.md`): 179 passed, 1 failed — that one failure was this WhatsApp test failing on a Temporal connection refused at localhost:7233 (environment). Today it is additionally uncollectable due to the app-import break. [H][V]
- **Phase 2B full caller-convergence acceptance** — `docs/phase2b_final_report.md` marks PARTIAL; remaining inline `/30` sites listed in MIGRATION_MATRIX §5. [H][V]
- **Phase 2C acceptance** — `contracts.py` (2C-A) + `outcome_feedback_contract` (2C-B) committed (`208ca04`); acceptance suite never executed; 2C-C not started. [V]
- Legacy-exclusion enforcement: `tests/test_legacy_isolation.py` `PROTECTED_CANONICAL` set + import tests (the "never import demo executors" gate). [V]

## 4. Test inventory (current, for planning gates)

`backend/tests/` (≈152 .py total): 119 flat files + `security/` 16, `temporal/` 6, `phase4/` 2, `phase5/` 1, `phase6/` 1, `regression/` 3, `fixtures/` 1, `load/` 1, `adversarial/` 2. No `tests/phase7` or `tests/phase8` dirs — phase 5–8 coverage is flat (`test_phase{5..8}_*.py` / `_foundation` / `_loop`). Postgres-specific: `test_phase9_postgres.py` (concurrent transfers cannot overdraw; duplicate execution prevented), `test_phase11_postgres.py` (stock never negative; duplicate approval idempotent; tenant isolation under concurrency), `test_phase13_postgres.py` (concurrent non-negative; duplicate approval; concurrent reconciliation no duplicate learning). [V]

## 5. Enforcement details that gates must uphold (verified)

- No production fallback to local runner: `runner.py:290-296` raises `TemporalExecutionError`; `startup_checks.py:32-35` fail-closed; `config.py:343-349` forbids `USE_TEMPORAL=false` in production. [V]
- Idempotency: `execution_key` SHA-256 (`app/orchestration/keys.py`, business_id+action+entity+payload+source) checked pre-apply; stored in executed_actions/agent_actions/execution_jobs. [V]
- Workflow order (local + Temporal mirror): capability → constraints → idempotency → apply → record. [V]

## 6. Recommended new gates for Jev (Phase 2+)

1. **Determinism gate**: Jev disabled/unavailable ⇒ byte-identical deterministic output (source label, risk_flags).
2. **Shadow parity audit**: observed-case divergence logging; deterministic wins.
3. **Availability gate**: outage/budget-exhaust ⇒ deterministic + `source="fallback"` + audit event.
4. **Contract gate**: Jev keys validated vs `CANONICAL_ACTION_TYPES` / findings severity; `ai_reasoning_requests` rows carry model version + capsule hash.
5. **Governance gate**: RLS tenant-scoped; capsule DLP-clean (no business_id/SKU/SAR/stock in prompts — enforced by `test_dlp`, `test_privacy_firewall`, `test_master_prompt`, `test_ai_isolation`); `autonomy_dial` untouched; execution via Temporal dispatcher only.
6. **Mock transport first**: hermetic mock-Jev transport in CI; opt-in real-Jev job.

## 7. What unblocks everything (the ONE thing)

Fix the two compile breaks so `python -m compileall -q app tests` passes and `from app.main import app` works:
1. Revert/repair the working-tree edit to `backend/app/services/intelligence_api.py` (lines 228-243) — restore HEAD indentation [V].
2. Fix `backend/tests/test_analytics_health_score.py` `_seed()` indentation (restore the awaited block under the test) — **committed** at a49b2c5, so requires a proper fix commit [V].
Only then can collection, compileall, backend-tests, and the temporal suite run at all.