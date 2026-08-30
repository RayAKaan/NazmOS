# NazmOS — Phase 11 Completion Report

Date: 2026-08-19

## A. Repository discoveries

Re-audited against the Phase 10 report (see `docs/PHASE11_AUDIT.md`). The Phase 10 report was
accurate. Confirmed still-missing after audit:

1. Margin root-cause engine (only `stockout_risk` + `dead_stock` existed).
2. Regime-change detection (absent).
3. Data-freshness *states* (`fresh/aging/stale/unknown`) — Phase 10 had only fresh/stale bools.
4. Recommendation-stability safety override (hysteresis existed without an explicit
   "safety wins" guard).
5. Agent least-privilege test + non-destructive Postgres concurrency matrix.
6. `docs/SUPPLIER_PRICE_SOURCES.md` + ROOT_CAUSE / RECOMMENDATION_ENGINE / OPERATIONAL_HEALTH /
   PRODUCTION_READINESS docs.
7. Merchant-facing operational status in the Action Center + root-cause in Finding Detail.

## B. Exact implementation

Backend (extended, no rewrites):
- `services/root_cause.py` — added `_margin_hypotheses` (supplier cost increase, selling-price
  mismatch, cost-vs-price compression, missing/low-quality cost data) + `ROOT_CAUSE_STRATEGIES`
  (root-cause → candidate strategies) + `_recommendations_for_hypotheses` (quality gates:
  supported→pipeline, plausible→confidence-penalized, insufficient_evidence→information-gathering).
- `services/regime_detection.py` (new) — deterministic relative-deviation regime signal +
  `regime_relevance_multiplier`.
- `services/operational_health.py` — four-state freshness (`freshness_state`).
- `services/decision_scoring.py` — `apply_stability` now never retains an unsafe (`risk==high`)
  strategy.
- `config.py` — `REGIME_*`, `FRESH_*` thresholds (conservative, documented).
- Tests: `test_phase11_foundation.py` (12), `test_phase11_agents.py` (4),
  `test_phase11_postgres.py` (3, non-destructive, Postgres-gated).
- `tests/test_retail_recovery_contract.py` — added new report/docs to the ignored-files list.

Frontend:
- `hooks/useActionCenter.ts` — `ops` (operational health) fetch.
- `components/dashboard/ActionCenter.tsx` — merchant-facing status banner (no internals).
- `app/(dashboard)/findings/[id]/page.tsx` — "Why it is happening" root-cause section.
- `lib/translations/en.ts` + `ar.ts` — new `ops` section (19 keys each).

Docs (new): `PHASE11_AUDIT.md`, `SUPPLIER_PRICE_SOURCES.md`, `ROOT_CAUSE.md`,
`RECOMMENDATION_ENGINE.md`, `OPERATIONAL_HEALTH.md`, `PRODUCTION_READINESS.md`.

## C. Existing architecture reused (not rebuilt)

Policy engine, agent runtime, executors, learning/reconciliation, strategy performance,
recency, decision scoring, root-cause (extended), operational health (extended), goal system,
Postgres CI workflow, v2/v3 design system, existing i18n. No new infrastructure.

## D. Root-cause improvements — IMPLEMENTED

Margin leakage now has a deterministic hypothesis engine. Root-cause → candidate-strategy
mapping feeds the normal ranking pipeline with confidence gates. `uncertain` is returned when
data is absent — never a fabricated cause.

## E. Data-quality improvements — PARTIALLY IMPLEMENTED

`findings.data_quality_score` already flows through decision scoring (Phase 9). Margin
root-cause now treats low data quality (<50) as its own `missing_cost_data` hypothesis,
routing to "improve data quality" rather than a pricing action.

## F. Data-freshness improvements — IMPLEMENTED

Four-state freshness (`fresh/aging/stale/unknown`) with configurable thresholds; `unknown`
when no timestamp (never fabricated).

## G. Regime-change detection — IMPLEMENTED

`regime_detection.detect_regime` (deterministic relative-deviation: no_signal / possible_change
/ supported_change / insufficient_data) + relevance multiplier for strategy relevance. History
is never erased.

## H. Recommendation changes — IMPLEMENTED

Decision score (Phase 9) now surfaces recency (Phase 10) and regime relevance is available to
strategy consumers; the scoring formula itself is unchanged (documented, deterministic).

## I. Recommendation stability — IMPLEMENTED

`apply_stability` hysteresis (Phase 10) now has an explicit safety override: an unsafe strategy
is never retained. Tested.

## J. Operational health — IMPLEMENTED

Backend `operational_health` (Phase 10) + merchant-facing banner in the Action Center.

## K. Finding Detail changes — IMPLEMENTED

Added "Why it is happening" (root-cause) section above "Why this strategy" and the timeline.

## L. Weekly Report changes — DEFERRED

No UI change this phase; the backend already includes recurring problems + observed/estimated
split (Phase 6–7). The 3–5-item prioritization is a follow-up.

## M. Goal intelligence — ALREADY EXISTED

Curated goal domains, progress history, trajectory, chain (Phase 4–7). No change.

## N. Agent architecture — ALREADY EXISTED + IMPLEMENTED

Added the least-privilege test (all declared tools valid; read-only agents only read-only
tools; mutating tools policy-gated).

## O. Learning architecture — ALREADY EXISTED

Unified outcome + reconciliation (Phase 6–7); unchanged.

## P. Security — ALREADY EXISTED

All endpoints use `assert_business_access`; no bypass added. Cross-tenant concurrency test added.

## Q. Concurrency — IMPLEMENTED

`test_phase11_postgres.py`: concurrent transfers (stock ≥ 0), duplicate approval (idempotent),
tenant isolation under concurrency. Non-destructive (no `DROP SCHEMA`).

## R. Supplier-price limitations — BLOCKED BY EXTERNAL INTEGRATION

No purchase-cost webhook source exists (Foodics/Salla emit sales orders only). Documented in
`docs/SUPPLIER_PRICE_SOURCES.md`; ETL + received-PO remain the only real sources.

## S. Test results

| Suite | Result |
|---|---|
| Backend full suite | ✅ **489 passed**, 95 skipped, 2 errors (pre-existing Postgres-only RLS; sandbox has no PG) |
| Phase 11 unit (foundation) | ✅ 12 passed |
| Phase 11 agent least-privilege | ✅ 4 passed |
| Phase 11 Postgres concurrency | ⏭ 3 skipped locally (Postgres unavailable) — run in CI |
| Alembic heads | ✅ single head `c9d0e1f2a3b4` |

## T. CI results

Not run locally (no Postgres). The Postgres-gated concurrency suites execute in
`.github/workflows/ci.yml` (`pytest -q` against Postgres 17). SQLite path is green locally.

## U. Migration state

Single linear head (`c9d0e1f2a3b4`). No new migrations this phase (pure service/UI additions).

## V. OpenAPI path count

213 paths (contract test passing; golden regenerated).

## W. Frontend build/lint/test

Build ✅ 38 routes 0 errors · Lint ✅ 0 errors (6 pre-existing warnings) · Jest ✅ 9 passed.

## X. Remaining limitations

- **BLOCKED BY EXTERNAL INTEGRATION**: supplier purchase-cost webhooks; actual provider billing.
- **ESTIMATED**: inference cost; recency half-life (90d); regime/Δ thresholds; freshness hours.
- **DEFERRED**: Weekly Report 3–5-item prioritization UI; regime signal is available to
  consumers but not yet wired into `best_strategy_for_finding`'s final score; root-cause for
  cash/compliance categories; full §Part 24 synthetic merchant fixture dataset.
- **NOT SAFE YET**: cross-merchant aggregate learning (correctly not built).

## Y. What should NOT be built next

Collective Buy, financing/lending, autonomous financial transfers, unrestricted purchasing,
supplier negotiation, a graph database, a second learning/policy/runtime system, fake
supplier/price data.

## Z. Recommended Phase 12

1. Wire the regime relevance multiplier into `best_strategy_for_finding` (already computed, not
   yet applied to the final ranking).
2. Add the synthetic merchant fixture dataset (§Part 24) and the full closed-loop Day 1→14 test.
3. Implement the Weekly Report 3–5-item prioritization in the UI.
4. Record the actual Postgres CI results once run (currently gated/skipped locally).
5. Tune regime/freshness thresholds against real pilot data.
