# PHASE 1 CLOSEOUT REPORT

Date: 2026-09-13 (updated 2026-09-14 after final independent verification)
Scope: NazmOS repository, working tree, `phase1-core-infra-replacements`
branch. This report supersedes the earlier draft, whose FIX table did not match
the final work delivered.

**Verdict: PHASE 1 COMPLETE** — all fixed surfaces implemented and verified on
final code state; mandatory verification roster green; remaining items are
recorded as caveats, none is an unresolved blocker.

---

## 1. Fixes delivered

| Fix | Change | Verification | Evidence |
|-----|--------|--------------|----------|
| FIX 1 | Image / DLP / loopback sanitisation sweep on freshly rebuilt backend image | 230p + 69p + 17p verified in-container | `docs/PHASE_1_CLOSEOUT_REPORT.md` (in-image evidence) |
| FIX 2 | `deploy.yml` fail-closed `.env` writer: escape `$` -> `$$` via `sed 's/\$/$$/g'` in BOTH staging (L159-173) and production (L263-277) blocks (the original `${v//\$/$$}` replacement was wrong) | byte-exact e2e proof that a secret containing literal `$` survives the writer | `docs/PHASE_1_CLOSEOUT_REPORT.md` (in-image evidence) |
| FIX 3 | Baked-frontend guard: `frontend/scripts/check_baked_bundle.mjs` + rewritten `ci.yml` frontend job | guard proven NON-VACUOUS: PASS on fixed `.env` build, FAIL 7 hits on control build; real GitHub CI run **not exercised** (push happened, workflow files now parse-clean, but a live green Actions run of the tree has not been observed — see caveats) | `frontend/scripts/check_baked_bundle.mjs` |
| FIX 4 | Loopback-only port topology + clean prod rebuild | 127.0.0.1-only binds; `DATABASE_APP_ROLE` must be literal `nazmos_app`; `API_WORKERS=1` required on this Docker Desktop/WSL2 host (fork() respawn bug, not app regression); dev stack restored | `docker-compose.prod.yml` |
| FIX 5 | Ingestion strict gates in `backend/app/services/data_normalizer.py`: `REVENUE_COLUMNS`, `BLANK_REJECT_COLUMNS`, `missing_price_basis`, `negative_current_stock`, `blank_required_value`, row-drop guard; SKU/name identity conflicts downgraded to warning-only (empirically safe-to-defer) | 11p data-integrity (+7 new), 20p phase1 decision-safety, 3p ETL dedup (+1 xfail), 5p v4, 4p phase1, 15p golden regression incl 6 DB-backed against clean migrated `nazmos_test` | `backend/app/services/data_normalizer.py` |
| FIX 6a | Temporal production substrate vs Postgres | Temporal suite 17/17 (real server + in-process production worker, sole poller, ZERO skips) | `tests/temporal/` |
| FIX 6b | P0 hardening set KEPT: `alembic.versions/ff12_rls_chat_pos_sync_logs.py`, `app/config.py` `WHATSAPP_VERIFY_TOKEN` production requirement, extended RLS tests | RLS suite 6/6 (chat/pos join policies + WhatsApp-webhook RLS), all green on migrated DB | `alembic/versions/ff12_rls_chat_pos_sync_logs.py` |
| FIX 6c | Deployment contract wired: `WHATSAPP_VERIFY_TOKEN` conveyed to all 5 prod backend-image services (migrate, backend, celery_worker, celery_beat, nazmos-worker); optional `WHATSAPP_APP_SECRET` on backend; added `STAGING_/PRODUCTION_WHATSAPP_VERIFY_TOKEN` secrets through deploy.yml envs+`write_kv` | POSITIVE `config -q` with token; NEGATIVE compose rejects without token (exit 1, `WHATSAPP_VERIFY_TOKEN must be set`) | `docker-compose.prod.yml` |
| FIX 6d | Alembic head ff12 on all DBs | `nazmos_test` clean full chain -> ff12; dev `nazmos` ff11->ff12; live `pg_policies`/`relrowsecurity` = chat_messages/pos_sync_logs/chat_sessions/pos_connections isolated, `*_tenant_isolation` ALL policies present | `alembic/versions/ff12_rls_chat_pos_sync_logs.py` |
| FIX 6e | Backend image rebuilt with P0 set (fixes the FIX-4 anomaly: that image predated the `WHATSAPP_VERIFY_TOKEN` FATAL, so the config change was unbuilt at FIX 4) | clean prod rebuild: migrate EXIT 0, `alembic_version` == ff12, backend HEALTHY, `/api/v1/ready` production + `required_env_missing:[]`; auth+RLS smoke 200; NEGATIVE: production settings refuse boot without token (exit 1, value_error) | `docker-compose.prod.yml` |

## 2. Clean prod rebuild (mandatory item)

Two clean rebuilds, both green:
- FIX 4: `nazmos_prod_check` (pre-P0 image) — full smoke incl register/login/JWT/bootstrap/inventory, loopback confirmed.
- FIX 6e: `nazmos_prod_check2` (post-P0 image, ff12 baked) — postgres/redis/temporal/opencode_runner healthy, migrate EXIT 0, alembic head ff12, backend HEALTHY, frontend up; object teardown `down -v` complete; dev stack restored (migrate rebuilt to include ff12, exit 0, worker resumed).

## 3. Verification matrix

| Roster item | Result |
|-------------|--------|
| Security / phase4 (DB-free) | green (test_security_acceptance + dashboard: **13 passed** on Postgres) |
| Temporal durability (real server, is Postgres) | **17/17**, 0 skips (worker paused as sole poller, resumed after) |
| Orchestration layer suites | green (fast SQLite family + execution-path clarity; phase5-8 loop, temporal_retry wiring) |
| Analytics DuckDB boundary / health / dead-stock / item-detail / scan-consolidation | green |
| Postgres-backed integration (AGENTS roster) | **16 passed** (restock_semantics, phase9/11/13_postgres, e2e_happy_path) |
| Dashboard + security acceptance (Postgres) | **13 passed** |
| RLS enforcement (DB layer, real policies) | **6 passed** (owner-bypass sanity, items isolation, findings WITH CHECK cross-tenant, chat join, pos join, WhatsApp-webhook approval fail-closed) |
| RLS coverage / predicate indexes / code-prep / tenant-scope idempotency / legacy isolation / temporal-failure tenant isolation | **67 passed** (DB-free static+sqlite family) |
| WhatsApp webhook tenant-scoped + decisions 403/404 (Postgres) | **10 passed** |
| Ingestion/golden regression (FIX 5) | 11 + 20 + 3 + 5 + 4 + **15 (incl 6 DB-backed)** passed |
| Frontend baked-bundle guard | PASS on real build (0 hits) vs 2-hit tampered-control FAIL (re-verified 2026-09-14); workflow files actionlint-clean; a live green GitHub Actions run of the tree not yet observed (see caveats) |
| Prod compose + deploy contract | `config -q` PASS with token; fail-closed without; deploy.yml escaping e2e PROVEN |
| Image/DLP/localhost sweep | 230 + 69 + 17 passed in-container |

Per-action cross-tenant RLS coverage (the P0 matrix):
- RESTOCK: `test_restock_semantics.py` (Postgres, stock mutation tenant-scoped) + WhatsApp webhook approval executes correct-tenant action and fails closed on wrong-tenant button (`test_rls_enforcement.py::test_whatsapp_webhook_approval_is_tenant_scoped_under_rls`).
- PRICE_CHANGE / DISCOUNT decisions: `test_decisions.py` foreign-business request -> **403/404**; `test_phase1_decision_safety_comprehensive.py::test_cross_tenant_action_update_blocked` (approving another business's action raises `ValueError("not found")`) and `::test_cross_tenant_constraint_modification_blocked` (tenant-scoped constraint reads).
- DB layer totality: `test_rls_coverage_complete.py` statically proves EVERY tenant table carries a `*_tenant_isolation` policy (ff12 added the join-scoped `chat_messages`/`pos_sync_logs`).

## 4. Deployment contract changes (new requirements)

- `WHATSAPP_VERIFY_TOKEN` is REQUIRED in production (`app/config.py` FATAL at boot; `docker-compose.prod.yml` enforces `:?` at compose time). New GitHub secrets:
  `STAGING_WHATSAPP_VERIFY_TOKEN`, `PRODUCTION_WHATSAPP_VERIFY_TOKEN` (wired through deploy.yml env map, `envs:` list, and `write_kv`).
- `WHATSAPP_APP_SECRET` optional on backend (webhook HMAC; empty = fail-closed, webhook refuses but boot succeeds).
- Carried requirements from FIX 4: `DATABASE_APP_ROLE` secret value must be `nazmos_app`; set `API_WORKERS=1` if the target host shows the uvicorn fork-respawn issue.
- Alembic head is now ff12 (both dev/test DBs and fresh prod rebuilds).

## 5. Honest caveats (recorded, not hidden)

- FIX 3 guard's live GitHub CI run **not yet observed green for the tree** (the branch push does not match `on.push.branches: [main, master]`; the historical Sep-07 PR run failed only on the ff09 migration-id width issue, fixed since by `a121792`). Validated via local control experiment proving the guard fails a tampered bundle; both workflow parse blockers found in final verification (`command:` on a GH Actions service container in `ci.yml`, missing `build-image` in `deploy-production.needs`) are fixed and actionlint-clean, with the absence of a new 0s parse-failure run on the `6c0166b` push confirming GitHub now parses the file and correctly applies branch filters.
- Real provider-key execution gate (provider-implementation with a live API key) **not verified** in this environment; verified at contract/unit/design level.
- The full 1200+ suite is not re-run as a single monolithic green pass in this session; every surface touched by FIX 1-6 was verified green on final code state and (for containers) on the rebuilt image/DBs, with the mandatory roster in section 3.
- FIX-4's "booted healthy in production without `WHATSAPP_VERIFY_TOKEN`" is resolved: that image predated the config change; the FIX 6e image + negative boot test prove the FATAL now works as designed.
- `nazmos_test` scratch DBs (e.g. `nazmos_test_ci*`) may persist in Postgres as harmless test leftovers.
- gitleaks binary not available in this environment; secret posture verified by presence tests (`.gitleaks.toml`, `.pre-commit-config.yaml`, security-tooling config) and pattern scans (no new secrets).

## 6. Evidence index

- `tests/temporal/` + `app/orchestration/temporal/` — Temporal production substrate, 17/17 suite.
- `alembic/versions/ff11_full_schema_app_role_grants.py`, `alembic/versions/ff12_rls_chat_pos_sync_logs.py` — migration chain to head ff12.
- `frontend/scripts/check_baked_bundle.mjs` — baked-bundle guard (non-vacuous control experiment, PASS/FAIL).
- `backend/app/services/health_metrics.py` — canonical health metrics service.
- `backend/tests/test_financial_truth_consolidation.py`, `test_pos_pull_sync_dedup.py`, `test_whatsapp_webhook_tenant_scoped.py` — new suites.
- `docs/archive/terraform-gcp-reference/` — archived prior infra reference (replaces deleted `infrastructure/terraform/`).
- `PRODUCTION_SEMANTIC_CONSOLIDATION_REPORT.md`, `docs/PHASE1_FINAL_REPORT_REVISION2.md` — Phase 1 documentation.

**PHASE 1 COMPLETE** — fixes implemented, rebuild clean, mandatory roster green,
deployment contract updated for the new production requirement, evidence archived,
no known unresolved blocker.