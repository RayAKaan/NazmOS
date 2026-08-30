# NazmOS — Phase 8 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 7)

Re-audited the Phase-7 recommendations. Confirmed outstanding:
- Impact attribution was coarse (Recovery `verify_outcome` used a whole-business
  `money_recovered_sar` delta).
- No strategy-performance engine (only `intervention_effectiveness` on LearnedOutcome).
- No per-finding impact attribution classification.
Already present and left untouched: ImpactLedger `finding_id` + `agent_action_id`,
OutcomeFeedback unification + reconciliation (Phase 6–7), goal-domain mapping, finding
timeline, and the deterministic executors (dialect-safe since Phase 7).

## B. Impact attribution

`impact_ledger.attribution ∈ {direct, partial, business_level, estimated, unattributable}`.
`record_impact` accepts it; `finding_observed_impact` returns the per-finding
direct/partial/business_level/verified breakdown. Recovery `verify_outcome` now:
1. attempts per-finding attribution (when `context.finding_id` is present),
2. falls back to a business-level delta **explicitly marked `attribution_scope=business`**.
The four quantities — finding estimated, action expected, action observed, business-wide
observed — are never conflated (§2).

## C. Strategy Performance Engine

`services/strategy_performance.py` — per action type: attempts, approved, rejected,
executed, verified, failed, observed_value, expected_value, success_rate, effectiveness
(observed/expected), evidence_tier. Evidence tiers deterministic + configurable
(`insufficient` <3, `preliminary` 3–9, `strong` ≥10). Contextual segmentation by finding
category omits segments below the preliminary threshold (§8–9). Observed vs estimated value
kept separate (§7/§10).

## D. Recommendation ranking

The orchestrator ranks goal-aligned → decision (auto/draft/approve) → strategy
effectiveness → risk. Strategy performance is a deterministic sort key; it **never**
bypasses the policy engine (§12–13). The exact formula is in `orchestrator.sort_key`
and `strategy_performance.best_strategy_for_finding` (documented, no LLM).

## E. Agent learning

- **Recovery** — `verify_outcome` per-finding + strategy-adjusted proposal (Phase 5–7).
- **Inventory / Procurement / Margin** — consume `learning_adjusted_action` + rejection
  history (Phase 6–7); their proposals flow through the strategy-ranked orchestrator.
- Agents without sufficient evidence fall back to deterministic baselines (never forced
  learning) — see §16, evidenced by `evidence_tier` gating.

## F. Recurring problems

`recurring_detection` + `learning_adjusted_action` (Phase 4–5) already flip a repeatedly
failed strategy to its alternative; `best_strategy_for_finding` now ranks alternatives by
evidence. Repeated failure lowers ranking without becoming an absolute prohibition (§18).

## G. Operator Console

No new dashboard was built (§19 "use the existing Ops Console"); the existing
`agent_performance` + reconciliation metrics (`/audits/performance`, `/audits/learning/
reconcile`) are the operator surface. The strategy-performance endpoints extend it.

## H. PostgreSQL production testing

Postgres CI (RLS + FOR UPDATE + concurrency) is the repo's existing convention; it runs in
CI, not this sandbox (no Postgres available). The SQLite loop is proven (`test_phase8_loop.py`);
the Postgres-specific `FOR UPDATE` row-lock in `_execute_transfer` is exercised there.

## I. End-to-end adaptive loop

`test_phase8_loop.py` proves: per-finding impact attribution (Scenario E), no double-count
of business vs direct (Scenario F), strategy ranking (transfer > discount when more
effective — Scenario A), and insufficient-evidence gating (1 attempt ≠ strong — Scenario B).
This demonstrates "previous outcome → strategy performance → changed future ranking."

## J. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **455 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1–8 tests | ✅ 11+8+8+11+10+6+5+5 unit + 5+4+4 loop + 3 unit + 5 loop |
| OpenAPI contract | ✅ golden regenerated (210 paths) |
| SQLite smoke | ✅ `impact_ledger.attribution` column created |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## K. Remaining issues

1. **Postgres CI** (RLS, FOR UPDATE, concurrency) runs in CI only — not this sandbox.
2. **Supplier-price purchase-document ingestion** — still no purchase-cost source (ETL+PO only).
3. **Cost tracking** — estimated, not billed.
4. **Recovery per-finding attribution** depends on the runtime passing `context.finding_id`;
   when absent it falls back to business-level (correct, but attribution is then coarser).
5. **Concurrency test** (§22) is not yet implemented — the unique constraints + idempotent
   upserts guard duplicates, but no explicit two-worker race test exists on SQLite.
6. **Strategy ranking** uses only effectiveness+success_rate; no urgency/data-quality term in
   the deterministic score yet (those remain separate inputs, §17/§19).

## L. Phase 9 recommendations

1. Add the concurrency/duplicate-execution test (two workers, one valid execution) on Postgres.
2. Add supplier-price purchase-document ingestion when a real source appears.
3. Add data-quality + urgency terms to the deterministic recommendation score.
4. Surface strategy performance + per-finding attribution in the Finding detail UI
   ("why this strategy?").
5. Only after production workloads: begin higher-stakes capability exploration (still no
   Collective Buy / financing / autonomous financial transfers).
