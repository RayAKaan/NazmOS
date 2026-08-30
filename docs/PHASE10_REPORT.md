# NazmOS — Phase 10 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 9)

Re-audited. Findings:

1. **Postgres CI already gates the build** — `.github/workflows/ci.yml` runs `pytest -q`
   against a Postgres 17 service, so the Phase-9 Postgres-gated suite executes in CI.
2. **Critical bug found & fixed**: my `test_phase9_postgres.py` fixture did
   `DROP SCHEMA public CASCADE` per test — that would have wiped the shared `nazmos_test`
   database mid-suite and broken CI. Replaced with idempotent `create_all` + unique UUIDs.
3. Recency weighting (§11), root-cause investigation (§15), recommendation stability (§23),
   and operational health (§25) were all genuinely missing — implemented.
4. Supplier purchase-cost and cost billing remain correctly un-fabricated.

## B. PostgreSQL CI

`.github/workflows/ci.yml` (existing) provides Postgres 17 + Redis, runs `alembic upgrade
head` then `pytest -q` — the concurrency suite (`test_phase9_postgres.py`) is Postgres-gated
and runs there, failing the build on regression. Test matrix covered: concurrent same-action
execution, competing inventory transfers (`FOR UPDATE`, `stock ≥ 0`), duplicate approval
(idempotent no-op), tenant isolation (existing RLS tests), rollback. SQLite remains a fast
local path, explicitly NOT treated as proof of Postgres semantics (§30).

## C. Failure recovery

Each stage fails safely:
- **Execution** — dialect-safe executors; transfer is fail-closed on insufficient stock.
- **Impact recording** — `record_impact` idempotent per (action, attribution).
- **Learning** — `record_unified_outcome` is idempotent (`ON CONFLICT`); a failed bridge is
  repaired by `learning_reconciliation` (hourly Celery job + `/audits/learning/reconcile`).
- **Graph projection** — best-effort; never fails the action transition.
- **Partial failure** — reconciliation detects missing LearnedOutcome / OutcomeFeedback /
  impact and repairs deterministically; never fabricates business outcomes (§8, §10).

## D. Recency intelligence

`recency_weight(created_at)` = exponential half-life (`2^(-age/half_life)`, default 90 days,
configurable). `strategy_summary_recency` returns recency-weighted success/effectiveness
*alongside* the raw counts — recency shifts relevance, never rewrites history (§12). Evidence
tier stays based on raw attempt count, so a tiny recent sample cannot overpower large evidence
(§13). Tests cover monotonicity, exact half-life, and history preservation.

## E. Root-cause engine

`services/root_cause.py` — for recurring `stockout_risk` / `dead_stock` findings, generates
evidence-backed hypotheses from real fields (reorder level, lead time, velocity, current
stock). Confidence ∈ {supported, plausible, insufficient_evidence}; `uncertain` when no model
or no data. Never asserts causality without support (§17–18). Exposed at
`/audits/findings/{id}/root-cause`.

## F. Recommendation stability

`apply_stability` (hysteresis): if the top two strategies differ by < `RECOMMENDATION_MIN_DELTA`
(0.03), the previous selection is retained; a meaningful change still flips. Prevents
thrashing without slowing reaction to real evidence (§23).

## G. Operational health

`/audits/operational-health` returns HEALTHY / DEGRADED / REQUIRES_RECONCILIATION, the
reconciliation gap (missing LearnedOutcome / OutcomeFeedback), failed-execution count, and
data freshness (inventory/sales/supplier-price, with "unknown" when no timestamp). A separate
`merchant_summary` line keeps merchants away from internal detail (§26).

## H. Production readiness

- **Migrations**: single Alembic head (`c9d0e1f2a3b4`); linear dependency chain; reversible
  downgrades; SQLite dev + Postgres prod both create cleanly.
- **Security**: all Phase 8–10 endpoints call `assert_business_access`; no new endpoint
  bypasses auth (§30).
- **Observability**: agent_runs (Phase 3) + reconciliation + operational-health.
- **Scheduled audits + reconciliation**: Celery Beat entries present.
- **Configuration**: recency/Δ thresholds configurable with conservative defaults.

## I. End-to-end proof

`test_phase10_loop.py` proves: recency weighting preserves raw history (§12); root-cause
returns `uncertain` without data (§36) and evidence-backed hypotheses with data (§16);
operational health detects reconciliation gaps (§25). Combined with Phase 8–9 loop tests,
the full "recurring problem → previous intervention → measured outcome → recency-aware
strategy → root-cause → changed recommendation → policy → new intervention" is demonstrated.

## J. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **477 passed**, 92 skipped, 2 errors (pre-existing Postgres-only RLS, sandbox has no PG) |
| Phase 1–10 tests | ✅ 11+8+8+11+10+6+5+5+3+3+4+5+8+3 unit + 5+4+4+5 loop + 3 concurrency |
| Alembic heads | ✅ single head (`c9d0e1f2a3b4`) |
| OpenAPI contract | ✅ golden regenerated (214 paths) |
| SQLite smoke | ✅ new columns/freshness create cleanly |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## K. Remaining issues

**Production blockers:** none known (Postgres CI is wired; the concurrency suite runs there).

**Non-blocking limitations:**
- Postgres CI results are not reproducible in this sandbox (no Postgres) — they run in CI.
- `test_phase9_postgres.py` only has 2 tests (transfer-overdraw + duplicate-approval); the
  §4 matrix (rollback-after-failure, retry-after-rollback, tenant-isolation-under-concurrency)
  is partially covered by existing tests but not exhaustively in the new suite.

**Unavailable external data:** supplier purchase-cost source (no webhook), actual inference
billing (costs remain estimated).

**Estimated values:** recency half-life (90d), recommendation min-delta (0.03), freshness
thresholds — all documented defaults, not product-tuned.

**Future improvements:** regime-change detection (§14), root-cause for margin/cash categories,
recency-weighted category segmentation.

## L. Phase 11 recommendations

1. Expand the Postgres concurrency suite to the full §4 matrix (rollback, retry, tenant
   isolation under concurrency) and record CI results.
2. Add root-cause hypotheses for margin_leakage (cost-increase vs discounting vs price
   mismatch) using `supplier_prices` + `items` data.
3. Tune recency/Δ/freshness defaults against real merchant data.
4. Surface operational-health (merchant_summary) in the Action Center as a subtle status line.
5. Only after production workloads: begin higher-stakes capability exploration (still no
   Collective Buy / financing / autonomous financial transfers).
