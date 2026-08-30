# NazmOS — Dead Code & Legacy Audit

> Sections 27–28 of the mission brief.
> Classification rules: `DEFINITELY DEAD` = declared/orphaned, zero references anywhere (app, tests, scripts, docs). `LIKELY DEAD` = referenced only by tests/scripts, no production import. `LEGACY / SUPERSEDED` = part of an earlier version's experiment superseded by a later phase. `TEST-ONLY` = used only in tests. `DEVELOPMENT-ONLY` = scripts/tooling, not shipped. `ACTIVE` = referenced in production app.

## 1. Summary

- The repo has accumulated **multiple experiment generations** (v9 → v12) whose data generators, runners and evaluators remain in `scripts/` and `sample_data/` but are not part of the runtime app.
- The **backend production surface** (`app/`) is largely wired; the truly dead code is mostly at the **table level** and in **experiment `scripts/` + `sample_data/` directories**.
- Several `models.py` tables are **not referenced by any service/router** and appear `LIKELY DEAD` (found earlier during database audit).

## 2. Dead / Unused Database Tables

> Evidence: grepped `app/`, `tests/`, `scripts/` for table names; no ORM write path or direct SQL reference.

| Table (models.py) | references in app code | Verdict |
|---|---|---|
| `recipes` | — (no import; no `INSERT`) | `LIKELY DEAD` |
| `parts_compatibility` | — | `LIKELY DEAD` |
| `enabled_modules` | referenced conceptually (module gating) but not this table (usage differs) | `LIKELY DEAD` (schema drift) |
| `pricing_rules` | present in ORM, not in planner/decision path | `LIKELY DEAD` |
| `pricing_recommendations` | no service/route use | `LIKELY DEAD` |
| `notification_preferences` | — | `LIKELY DEAD` |
| `notifications` | frontend "notifications" channel not wired to this table (uses events) | `LEGACY / SUPERSEDED` |
| `reports` | — | `LIKELY DEAD` |
| `executed_actions` | superseded by `agent_actions` (`action_executor`, `agent_action_executor`) | `LEGACY / SUPERSEDED` |
| `constraint_blocks` | used — by `execution_guard.record_constraint_block` | `ACTIVE` |
| `analytics_cache` | — | `LIKELY DEAD` (v1 analytics, superseded by real-time KPIs) |
| `permission_definitions` | `capabilities_service.build_capabilities` reads it | `ACTIVE` (verify import) |
| `team_invitations` | — | `LIKELY DEAD` (no invite flow endpoint found) |

## 3. Experiment / Version Directories

| Dir | Contents | Verdict |
|---|---|---|
| `scripts/v9/`, `scripts/v9_*.py`, `sample_data/v9/` | experiment runners + 5 business-case datasets | `LEGACY / SUPERSEDED` (replaced by v10-v12) |
| `scripts/v10/`, `scripts/v10_*.py`, `sample_data/v10/` | al-Noor data + evaluator | `LEGACY / SUPERSEDED` |
| `scripts/v11/`, `scripts/v11_*.py`, `sample_data/v11/` | new data + evaluator | `LEGACY / SUPERSEDED` |
| `scripts/v12/*`, `sample_data/v12/` | strict normalizer/eval/latency | `LEGACY` but most recent (parity with strict pipelining) |
| `scripts/v2_step1..4` (any) | older runtime-validation scripts | `LEGACY` |
| `scripts/reality_*.py`, `scripts/runtime_*.py`, `scripts/load_smoke_test.py` | live-run helpers (reality capture, Playwright journey, E2E) | `DEVELOPMENT-ONLY` (runtime harness, not shipped code) |
| `scripts/backup_postgres.py`, `restore_postgres.py`, `verify_workspace.py`, `check_env.py`, `wait_runtime.py` | ops tooling | `DEVELOPMENT-ONLY` |

## 4. Production vs Experimental Binaries

Grepping `app/` imports found no production reference to:
- `ab_decision_framework` ← **referenced only by tests + `routers/money_audit.py` (counterfactual/compare modes)** → `PARTIAL`: live in money-audit experimental endpoints, `TEST-ONLY` otherwise.
- `learning_engine_advanced` ← only `tests/test_learning_advanced.py` → `TEST-ONLY`.
- `closed_loop_experiment` ← mostly test/experiment harness → `TEST-ONLY`/`LIKELY DEAD`.
- `calibration_service`, `agent_observability` ← used by observability endpoints (verify); otherwise `TEST-ONLY`.

Partially referenced (kept, but lesser-used): `profit_optimizer` (used by `routers/orchestrator.py`), `prophet_service` (forecast router + tasks), `knowledge_graph` (used across audit/intelligence), `evidence_package` (money audit), `simulation_engine` (intelligence API), `credential_vault` (adapters + tasks).

## 5. Dead Code Risks

1. **Schema duplication**: `executed_actions` vs `agent_actions` — migration risk, ambiguous existing data.
2. **Unused financial columns**: `money_at_risk_sar` / `expected_recovery_sar` preserved for compatibility with new `capital_at_risk_sar` / `recoverable*` (duplicate semantics, drift risk).
3. **Experiment data in repo**: `sample_data/v9..v12` grows the repo / confuses CI; no runtime consumption.
4. **Old scripts**: runtime validation scripts can be confused for production entrypoints.

## 6. Recommendation (documentation only)

- Tag superseded structures in DB audit (already reflected in `NAZMOS_DATABASE_ARCHITECTURE.md`).
- Never "clean up" code during this audit — produce findings only; removal is a follow-up engineering decision.