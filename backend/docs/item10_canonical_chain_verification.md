# Item 10 — Final Architectural Verification of the Canonical Chain

Objective (per the remediation directive): prove the one canonical execution
path is coherent end-to-end and that all financial numbers have deterministic
provenance — that the audit, its evidence, its time-machine simulation, its
guest twin, and its action execution all derive from one shared deterministic
core and are tenant-bounded.

## Canonical chain (single path)

```
Raw merchant files
   │  ETL (etl_pipeline.py)
   │   • location grain preserved; fail-closed on location collapse (G)
   │   • source_transaction_id + 4-col content-hash dedup (ff08)
   ▼
transactions (Postgres, tenant RLS)
   │  COUNT(DISTINCT DATE(transaction_at)) = observed coverage
   ▼
money_audit_service.py
   │  coverage_aware_daily_velocity(qty_30d, coverage_days_30d)   ← shared
   ▼
audit_core.analyze_product(ProductMetrics)   ← single source of truth
   │  classify_inventory / estimate_recovery / stockout_financials
   ▼
ProductAudit  (classification, velocity, capital/days-supply/at-risk, order_qty)
   │
   ├──▶ money_audit.py time_machine — reuses the SAME coverage_aware_daily_velocity
   ├──▶ evidence_package.build_item_evidence — reuses the SAME helper
   └──▶ guest_audit_service — drives the SAME analyze_product
```

## Verification points (each confirmed against source + tests)

1. **Single velocity source.** `app/services/audit_core.coverage_aware_daily_velocity`
   is the only canonical daily-velocity formula. It is imported and used by:
   `money_audit_service.py`, `money_audit.py` (time-machine + evidence),
   `evidence_package.py`, `audit_engine.py`, and `guest_audit_service.py` (via
   `analyze_product`). Root-cause tests in `TestRootCauseAssertions` and the F/H
   matrix pin that 6 observed days are never presented as 30.

2. **ETL → audit provenance.** `etl_pipeline.py` persists raw transaction facts
   (item, location, quantity, transaction_at, source_transaction_id, row_hash).
   `money_audit_service.py:196` reads observed coverage with
   `COUNT(DISTINCT DATE(transaction_at))` and feeds it straight into the shared
   velocity helper — the same number that reaches the time-machine.

3. **Audit and its reports agree.** `time_machine` (money_audit.py:882) and
   `build_item_evidence` call the identical `coverage_aware_daily_velocity`, so a
   simulated 6-day dataset and its printed/evidence output match the audit row.

4. **Guest = authenticated math.** `guest_audit_service` routes through
   `audit_core.analyze_product`, proven by `test_phase_c_audit_core.py`
   (`test_guest_and_money_paths_agree_on_two_file_audit`) and the 600-case
   randomized equivalence test.

5. **Execution is tenant-bounded and actor-attested.** All action entry points
   (`routers/actions.py`, `routers/money_audit.py::execute_action`) call
   `ActionExecutor.execute_action` with an attested `user_id` and a
   tenant-scoped `business_id`. Every money-audit route first calls
   `assert_business_access`. Items 2–4 RBAC (service-boundary capability gate)
   remains enforced in `approve/reject_agent_action`.

6. **Canonical model matches migrations.** The 4-column
   `(business_id, location_id, item_id, row_hash)` dedup index and location grain
   are created by `ff08_loc_grain_tenant_model` (single alembic head), and the ETL
   `ON CONFLICT` target matches it exactly. Verified at the SQL level in
   `test_golden_fixture_regression.py::TestETLIntegration` (PostgreSQL).

## Chain-level test evidence (all green this session)

- `tests/regression/` golden fixtures + canonical acceptance: **passed**
  (incl. business-wide SAR 28,892 and no location collapse).
- `tests/phase_c_audit_core.py` equivalence: **passed**.
- `tests/test_chat.py` / `tests/test_dashboard.py` / `tests/test_guest_audit.py` /
  `tests/test_zero_cost_sqlite_mode.py`: **passed**.
- `tests/regression/test_adversarial_matrix.py` (31) + root-cause assertions: **passed**.

## Conclusion

The one canonical execution path is coherent: a single deterministic
`audit_core` math core fed by tenant-RLS-guarded, coverage-aware ETL data,
consumed identically by the authenticated money audit, its time-machine, its
evidence package, and the free guest audit, and acted upon only through
tenant-scoped, actor-attested execution. No alternate financial path bypasses
this core.
