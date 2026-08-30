# Phase 12 Audit

Date: 2026-08-19. Re-audit against the Phase 11 report before implementation.

## Already implemented (verified)

- Regime detection: `regime_detection.detect_regime()` + `regime_relevance_multiplier()` exist.
- Recency weighting: `strategy_performance.recency_weight()` + `strategy_summary_recency()`.
- Root cause: stockout/dead-stock/margin + `ROOT_CAUSE_STRATEGIES` + quality gates.
- Freshness: four-state `freshness_state()`.
- Stability: `apply_stability()` with safety override.
- Agent least-privilege test (`test_phase11_agents.py`).
- Non-destructive Postgres concurrency matrix (`test_phase11_postgres.py`).
- Postgres CI (`.github/workflows/ci.yml` runs `pytest -q` vs Postgres 17).

## Partially implemented / incorrect assumptions

1. **Regime relevance is NOT wired into ranking** (Part 2 gap). `best_strategy_for_finding`
   uses `strategy_summary` (raw), not `strategy_summary_recency`, and never consults
   `regime_relevance_multiplier`. Confirmed by reading the function.
2. **No shared prioritization service** — Action Center and Weekly Report use different,
   ad-hoc ordering (Part 9/11 gap).
3. **Weekly report has no top-N prioritization** (Part 9 deferred in Phase 11, still absent).

## Genuinely missing

- Synthetic merchant fixture framework + scenario engine (Part 5–6).
- Day 1 → Day 14 closed-loop test (Part 7).
- Recency/regime test matrix (Part 4).
- Root-cause → strategy differential tests (Part 15).
- Weekly Report UI prioritization (Part 10).
- `docs/` Phase 12 docs.

## What will be changed

1. `strategy_performance.best_strategy_for_finding` → incorporate recency + regime relevance
   (deterministic, documented; historical evidence remains visible).
2. New `services/prioritization.py` — shared deterministic top-N problem ranking.
3. `weekly_report_service` → add `priorities` (top 3–5).
4. New `tests/fixtures/merchants.py` + `tests/scenarios.py` + `test_phase12_closed_loop.py`.
5. Docs.

## What remains deferred

Supplier purchase-cost webhooks (no source), actual billing, cross-merchant learning,
cash/compliance root-cause, full production simulation engine.
