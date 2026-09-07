# Item 8 — Root-Cause Assertions

Each golden-fixture root cause is pinned by a dedicated assertion so it cannot
silently recur when the full suite passes. All assertions are DB-free:
pure-math + source-level checks that run in CI without Postgres.

Run:
```
cd backend
python -m pytest tests/regression/test_adversarial_matrix.py -q
```

## RC-1 — 6 observed days are never presented as a 30-day dataset (F)

- `money_audit_service.py` SQL measures observed coverage with
  `COUNT(DISTINCT DATE(transaction_at)) AS coverage_days_30d` and computes
  velocity through the shared `audit_core.coverage_aware_daily_velocity` helper.
- `audit_engine.py` inventory stockout scan divides by observed coverage days
  (`/ coverage_days`), never a hardcoded `/30`.
- `ProductAudit.observed_coverage_days` carries the real grain out so reports
  can state coverage before concluding.

Assertions: `TestRootCauseAssertions::test_rc1_*`

## RC-2 — Location grain never collapses (G)

- ETL `_apply_inventory_snapshot` raises `ValueError` when a file without a
  location column contains duplicate item names ("Refusing inventory import").
- The transaction conflict target is the four-column
  `(business_id, location_id, item_id, row_hash) WHERE row_hash IS NOT NULL`,
  matching the `ff08_loc_grain_tenant_model` partial unique index — so
  `ON CONFLICT` can never silently last-write-wins a multi-location row.

Assertions: `TestRootCauseAssertions::test_rc2_*` (source level) plus the
DB-backed `TestETLIntegration::test_missing_location_ingest_fails_closed_on_grain_collapse`
and `test_location_collapse_is_impossible_in_db` in `test_golden_fixture_regression.py`.

## RC-3 — UNKNOWN never becomes 0 (F)

- An item with insufficient demand evidence keeps classification `UNKNOWN`.
- `estimate_recovery("UNKNOWN", ...)` returns `expected_recovery=None` with
  confidence `INSUFFICIENT DATA`; it never fabricates a numeric recovery and
  never auto-labels the item as needing attention.

Assertions: `TestRootCauseAssertions::test_rc3_*` plus `TestFNoUnknownBecomesZeroNoSixBecomesThirty`.

## RC-4 — Tenant-scope / fail-closed writes (I-dimension)

Consolidated assertion that every mutation router hardened in the second audit
carries a `business_id` scope. Per-router guards live in
`TestISecondAuditTenantScopedWritesAndNoRawLeaks`.

## Results

`tests/regression/test_adversarial_matrix.py`: 31 passed (8 new root-cause
assertions added for Item 8).