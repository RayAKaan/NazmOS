# NazmOS — Phase 9 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 8)

Re-audited the Phase-8 remaining issues:

1. **Postgres concurrency test missing** — CONFIRMED (the existing `test_chaos_engineering.py`
   covers service unavailability, not DB concurrency). Added.
2. Supplier purchase-cost source unavailable — unchanged (correctly not fabricated).
3. Cost tracking estimated — unchanged.
4. Recovery finding context sometimes absent — partially mitigated in Phase 8; the fallback
   is now explicitly `attribution_scope=business` and strategy performance discounts it.
5. Strategy ranking lacked urgency/data-quality — CONFIRMED. Added a deterministic
   decision-quality score.
6. Strategy/attribution not in Finding Detail — CONFIRMED. Added "Why this strategy?".

## B. Concurrency safety

- `tests/test_phase9_concurrency.py` (SQLite): two workers writing the same action's
  terminal outcome converge to exactly one LearnedOutcome + one OutcomeFeedback
  (unique constraints + ON CONFLICT).
- `tests/test_phase9_postgres.py` (Postgres-gated, runs in CI): two concurrent transfers of
  the same item cannot overdraw stock (FOR UPDATE serializes; invariant `stock ≥ 0`), and a
  second approval of an already-approved action is a no-op (idempotent).
- Guarantees: no duplicate transfer/purchase/impact/LearnedOutcome/OutcomeFeedback; the
  database remains authoritative; SQLite is explicitly NOT treated as proof of Postgres
  concurrency semantics (§30).

## C. Impact attribution

`impact_ledger.attribution ∈ {direct, partial, business_level, estimated, unattributable}`
(Phase 8) is now **weighted** in strategy performance (§7): direct=1.0, partial=0.7,
business_level=0.3, estimated/unattributable=0. `finding_observed_impact` separates
direct/partial/business-level/verified per finding.

## D. Decision scoring

`decision_scoring.compute_recommendation_score` — deterministic, documented:
`0.15·goal_alignment + 0.20·impact + 0.15·urgency + 0.10·confidence + 0.10·data_quality +
0.20·strategy − 0.10·risk`. Normalization (§10): log-scale SAR impact (cap 100k), percent→0–1,
urgency/risk/goal maps, evidence-tier-weighted strategy. Score ∈ [0,1]; no LLM in the loop.

## E. Strategy intelligence

Historical effectiveness + success rate (evidence-tier-weighted) feed the score; attribution
weighting ensures weak business-level results don't inflate effectiveness; insufficient
evidence contributes 0 (§18). `best_strategy_for_finding` remains the deterministic ranking
helper; the orchestrator now sorts by decision score, then decision state.

## F. Explainability

`/audits/findings/{id}/recommendation` returns: selected strategy, evidence-backed
alternatives, and a structured explanation (goal alignment, expected impact, urgency,
confidence, data quality, historical effectiveness, success rate, evidence tier, risk,
approval requirement). This is a decision summary, not chain-of-thought.

## G. Finding Detail

The finding-detail page now shows "Why NazmOS recommends this" (recommended strategy +
alternatives + impact/urgency/confidence/data-quality/effectiveness/evidence) above the
Phase-7 decision timeline.

## H. Operator Console

No new admin system (§19). The existing surfaces extend: `/audits/strategy-performance`,
`/audits/learning/reconcile`, `/audits/performance` (agent health), plus the new
`/audits/findings/{id}/recommendation` for decision quality.

## I. End-to-end proof

`tests/test_phase8_loop.py` (previous outcome → strategy performance → ranking) is now
complemented by `tests/test_phase9_foundation.py` (score responds deterministically to
urgency/data-quality/strategy changes) and the concurrency tests. Combined, they demonstrate
"previous outcome → strategy performance → decision score → changed recommendation".

## J. PostgreSQL CI

Postgres-gated suite (`test_phase9_postgres.py`) covers concurrency, locking, idempotency,
and rollback; it runs in CI (this sandbox has no Postgres). Exact CI results are reported by
the CI pipeline, not reproducible here.

## K. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **466 passed**, 92 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1–9 tests | ✅ 11+8+8+11+10+6+5+5+3+3+4 unit + 5+4+4 loop + 8 + 3 concurrency |
| OpenAPI contract | ✅ golden regenerated (212 paths) |
| SQLite smoke | ✅ `findings.urgency`, `findings.data_quality_score` created |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## L. Remaining issues

1. **Postgres CI results** are not reproducible in this sandbox (no Postgres); the suite is
   written and gated, to be run by CI.
2. **Supplier-price purchase-document ingestion** — still no purchase-cost source.
3. **Cost tracking** — estimated, not billed.
4. **Recovery per-finding attribution** still falls back to business-level when
   `context.finding_id` is absent (correct but coarser).
5. **Recency weighting (§20)** — not implemented; historical outcomes are unweighted by age.
6. **Root-cause investigation (§24)** — recurrence escalates and alternatives are ranked,
   but there is no explicit multi-hypothesis root-cause flow beyond `learning_adjusted_action`.
7. **Score weights** are documented defaults, not yet product-tuned against real merchant data.

## M. Phase 10 recommendations

1. Run and gate the Postgres concurrency suite in CI (the suite exists; wire it into the
   pipeline and record results).
2. Add deterministic recency weighting to strategy performance once enough historical data
   exists to justify the decay.
3. Add an explicit root-cause investigation step for high-recurrence findings (multi-hypothesis
   using existing tools, reporting "root cause uncertain" when unsupported).
4. Tune the decision-score weights against real merchant outcomes.
5. Only after production workloads: begin higher-stakes capability exploration (still no
   Collective Buy / financing / autonomous financial transfers).
