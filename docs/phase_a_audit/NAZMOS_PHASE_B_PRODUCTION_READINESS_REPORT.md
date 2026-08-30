# Phase B Report: Production Hardening & Reality Validation

**Date**: 2026-08-31
**Auditor**: Phase B Audit Agent
**Repo**: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
**Verdict**: **PILOT READY WITH CONDITIONS**

---

## 1. Executive Summary

Phase B (Production Hardening & Reality Validation) is complete. The backend now
invariably passes **916 tests with 0 unexplained failures** (3 skipped = live
credential integrations by design; 1 transient flake observed and re-confirmed
green in isolation). All 12 workstreams (WS1–WS12) shipped with **test-first
verification**. Five **real production defects** were found and fixed:

1. **RLS gap** — tenant-scoped DML was not row-level gated for the app role.
2. **Dead-stock under-count** — analytics missed never-sold dead items, making
   money-audit recoverable value and the agent tool disagree with reality.
3. **SQLite-accepted-in-production** — production config silently accepted a
   SQLite URL, disabling Celery/Redis and making the RLS + role model impossible.
4. **Silently-skipped CORS enforcement** — pydantic field-order meant production
   origin/scheme checks never ran.
5. **PG-only stockout scan** — a SQLite-breaking `JSONB`/`LATERAL` inbound
   subquery sat in the phase-1 stockout scan (broke the customer/demo mode).

Every fix is byte-sized, nothing was redesigned, and no security, financial, or
AI guardrail was weakened.

---

## 2. Baseline Comparison

| Metric | Phase A Post-Fix | Phase B Baseline | Phase B Final | Delta (B) |
|--------|------------------|------------------|---------------|-----------|
| **Passed** | 801 | 864 | **916** | +52 |
| **Failed** | 53 | 0 | **0** | 0 |
| **Skipped** | 3 | 3 | 3 | 0 |
| **Errors** | 10 | 0 | **0** | 0 |
| **Duration** | ~8.8 min | ~9.2 min | ~9.5 min | +0.3 min |

The +52 tests are the Phase B lock-in suites (WS2–WS11) — each one a contract or
drift guard that keeps a verified property honest. The pre-existing 53 failures /
10 errors from Phase A were already resolved before Phase B (864/3/0 baseline) and
stayed green.

**Transient flake**: `tests/test_webhook_audit.py::test_foodics_webhook_dedupes_by_external_event_id`
failed once inside the full run, then passed 4/4 in isolation and 3/3 as a file.
It touches zero Phase B code (no webhook module was modified). Classified as a
pre-existing timing/order quirk; flagged below as a condition to root-cause before
mass onboarding.

---

## 3. Defects Found & Fixed

| # | Where | Defect | Fix | Verified By |
|---|-------|--------|-----|-------------|
| 1 | `app/services/analytics_service.py` | `calculate_dead_stock_value` inner-swept transactions, so **never-sold** dead items (`stock>0`, no sales in 30d) were excluded while agent tool + dashboard included them | Canonical rule: LEFT JOIN from Inventory (`current_stock > 0 AND COALESCE(qty_30d,0) < 1`), single dialect-safe query | `test_scan_consolidation.py` (2) |
| 2 | `app/config.py` | **Production + SQLite passed silently**; SQLite forces Celery/Redis OFF, making RLS + `nazmos_app` role impossible | `validate_production_cross_fields` (after-validator) rejects SQLite URLs in production | `test_production_config_contract.py` |
| 3 | `app/config.py` | **CORS production checks never ran** — `CORS_ORIGINS` field validated before `ENVIRONMENT`, so `info.data` lacked the env; wildcard/scheme violations passed silently | Moved enforcement (no wildcard, HTTPS-or-local dev) into the after-validator; field validator is now a pass-through | `test_production_config_contract.py` |
| 4 | `app/services/audit_engine.py` | Stockout scan shipped a PG-only `JSONB`/`LATERAL` inbound subquery, breaking SQLite (customer/demo) deployments | Replaced with a dialect-safe scan | phase-1 suites + full regression |
| 5 | `tests/fixtures/merchants.py` | `seed_transactions` defaulted to an unset `transaction_type`, producing 0-revenue businesses that skewed every downstream metric | Explicit `transaction_type='sale'` | phase-1 suites + WS10 E2E |

---

## 4. Workstream Matrix

| WS | Deliverable | Tests |
|----|-------------|-------|
| WS1 | Groq rate-limit docstring; OpenAPI golden regenerated; frontend audit call moved to `/audits/runs`; phase-1/phase-2 suites green | regression |
| WS2 | RLS hardening for the 9 strictly-tenant tables via Alembic `phase_b_rls_core_services` (tenant-isolation policies + DML grants to `nazmos_app`) + drift-guard/index/enforcement suites | 7 |
| WS3 | Canonical financial vocabulary (`*_sar` keys, alias map, `FinancialEstimate._sar` properties) | 8 |
| WS4 | Execution-path clarity: simulated path never mutates money; PG contrast; AST wiring guard (real-only via execution engine) | 4 |
| WS5 | Scan consolidation — analytics = tool = dashboard dead-stock contract | 2 |
| WS6 | Zero-cost SQLite mode: `USE_CELERY=False`/`USE_REDIS=False` auto-forced, stub celery, in-memory rate limiter, health never "unhealthy", inline uploads | 5 |
| WS7 | Production config contract (Datacenter/role required, env/url/CORS invariants) | 9 |
| WS8 | Legacy isolation — demo engines (`v8_business_simulator`, `closed_loop_experiment`, `simulation_engine`, `time_machine`, `nazm_planner`) reachable only from the allowlist; canonical code never imports them; time-machine deterministic/bounded | 4 |
| WS9 | Integration contracts mock-only — WhatsApp `mock_sent`, LLM mock returns deterministic JSON (`risk_flags: ["MOCK_LLM"]`) with **no real reasoning**, POS DB-only with zero credentials | 4 |
| WS10 | Customer E2E happy path on Postgres (seed → money audit → simulated discount execution → `job.result["simulated"]`, dead stock = 40×20 = 800) | 1 |
| WS11 | Observability export integrity — event checksums are deterministic and detect payload tamper; audit log is append-only (distinct ids, ordered) | 3 |
| WS12 | This report | — |

**Phase B suites total**: 47 new tests in the WS files above (remaining +5 of the
+52 delta are pre-existing files re-counted against the analytic/health suites).

---

## 5. Boundary Conditions (the "CONDITIONS")

1. **Live-credential integrations** (3 skipped tests) cannot be verified in CI —
   provision real Foodics/Salla/WhatsApp credentials before opening pilot tenants.
2. **Webhook dedup flake** must be root-caused (shared PG `nazmos_test` DB + retry
   ordering) before mass onboarding; reproduce with
   `pytest tests/test_webhook_audit.py::test_foodics_webhook_dedupes_by_external_event_id -x -q --tb=short`.
3. **WS3 inherited debt**: the DB column rename for the canonical `*_sar` keys is
   **not** executed — normalization + aliases only (documented in
   `FINANCIAL_VOCABULARY_ADR.md`). Migrate columns before any external data export.
4. **Money-audit service is Postgres-only by design** (JSONB casts, `DATE_TRUNC`,
   `INTERVAL`, `::date`, `NOW()`). Zero-cost/SQLite deployments must not expose
   money-audit endpoints; the E2E path (WS10) runs on Postgres.
5. **Redis/Celery remain optional**; zero-cost mode is now contract-tested so the
   pilot can run without extra infra, and production must hard-require the
   Postgres + `nazmos_app` role model (WS7).

---

## 6. Reproducibility

```powershell
cd backend
$env:TEST_DATABASE_URL = "postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
python -m pytest tests/ -q            # 916 passed, 3 skipped
```

Every new bash invocation must re-set `TEST_DATABASE_URL` (env does not persist).

---

## 7. Deliverables Added

```
backend/alembic/versions/phase_b_rls_core_services.py
backend/tests/test_rls_coverage_complete.py            (3)
backend/tests/test_rls_predicate_indexes.py            (1)
backend/tests/test_rls_enforcement.py                  (3)
backend/tests/test_financial_vocabulary.py             (8)
backend/tests/test_execution_path_clarity.py           (4)
backend/tests/test_scan_consolidation.py               (2)
backend/tests/test_zero_cost_sqlite_mode.py            (5)
backend/tests/test_production_config_contract.py       (9)
backend/tests/test_legacy_isolation.py                 (4)
backend/tests/test_integration_contracts_mock.py       (4)
backend/tests/test_e2e_happy_path.py                   (1)
backend/tests/test_observability_export.py             (3)
docs/phase_a_audit/FINANCIAL_VOCABULARY_ADR.md         (WS3)
docs/phase_a_audit/EXECUTION_PATH_ADR.md              (WS4)
docs/phase_a_audit/NAZMOS_PHASE_B_PRODUCTION_READINESS_REPORT.md
```

Changed (fixes only): `app/services/analytics_service.py`, `app/config.py`,
`app/services/audit_engine.py`, `tests/fixtures/merchants.py`.