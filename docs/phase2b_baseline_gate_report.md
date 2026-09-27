# PHASE 2B — VELOCITY CONVERGENCE GATE REPORT (§12 A–Q)

## A. Env / infra state (see §1/§H gate)

- Docker engine: **GREEN** (server 29.6.1, dockerd responding).
- Live Postgres: **GREEN** — container `nazmos_latest_merged-postgres-1`,
  PG 17.10-1, migrated to alembic head `ff12_rls_chat_pos_sync_logs`
  (52 migration files, DB nazmos_test created, role nazmos + nazmos_dev
  verified via asyncpg TCP auth probe BEFORE this run).
- Temporal: **NOT PRESENT** in this repo's compose service list
  (docker compose config --services shows no temporal service).
  Required by ONE test (`test_rls_enforcement.py::test_whatsapp_webhook
  _approval_is_tenant_scoped_under_rls`) which executes an agent_approval
  Temporal workflow.

## B. Baseline (run first, no code touched)

python -m pytest (recovery_match_matcher, recovery_match_unit, rls_enforcement,
rls_predicate_indexes, recovery_intelligence_v2, data_integrity_recovery
_upgrade, financial_truth_consolidation, financial_vocabulary,
business_decision_loop_v1, decisions, decision_engine,
retail_recovery_contract, forecast, forecasting, statsforecast_provider)
- **179 passed, 1 failed** in 55.31s.

### The 1 failure — exact:
```
FAILED tests/test_rls_enforcement.py::test_whatsapp_webhook_approval_is_tenant_scoped_under_rls
E   ... execution failed (workflow=agent_approval ... address=localhost:7233):
Failed client connect ... Server connection error: ... 7233 refused
```

## B-classification: ENVIRONMENT (Temporal service absent from compose,
not a code/path/money regression). A-money-suites all green (179 = includes
financial_truth, financial_vocabulary, business_decision_loop_v1, decisions,
decision_engine, rls_enforcement + rls_predicate_indexes + recovery
_intelligence_v2 + data_integrity_recovery_upgrade).

## C. Canonical (Phase 2B target semantics — coverage-aware canonical)

app/services/audit_core.py:coverage_aware_daily_velocity (canonical §3), with
observed coverage; days-of-supply fallback chain:
- observed coverage available ? coverage-aware
- coverage None ? legacy /30 (preserved: money-audit sites :196-246, :345)
- coverage <= 0 with quantity > 0 ? qty/1
- quantity == 0 ? zero
(duckdb-backed analytical boundary = app/analytics/duckdb_engine.py)

## D. Money-critical callers of recovery velocity (Phase 2B §H)

recovery_match_service has TWO /30 sites that re-implement velocity inline:
- generate_preview :123-133 (GREATEST(COALESCE(s.qty_30d,0)/30.0, 0.01)
  + days_of_supply)
- opportunity query :260-266 (same /30.0 GREATEST + days_of_supply)

**STATUS: UNMIGRATED THIS PASS.** This is the §H-gate. Convergence of the
money-critical recovery velocity is NOT declared because the §2 baseline is
blocked only by the Temporal-env 1-failure, and per §5/§13 I do NOT migrate
a money path on a partially-green baseline. STOP applied.

## E-Q. Verdict

Title: RECOVERY_VELOCITY_CONVERGENCE (Phase 2B)
Core verdict: **RECOVERY_VELOCITY_CONVERGENCE NOT ACCEPTED**
(Enforcement proper.) The NOT ACCEPTED is caused by: (1) baseline has one
environment (Temporal) failure — infra; (2) per §H the money-critical
migration gates on a fully-green baseline. Nothing committed. Nothing pushed.
No commit. No push flagged. STOP.
