# Phase 11 Audit

Date: 2026-08-19. This records the re-audit against the Phase 10 report before any Phase 11
implementation. It is a reconciliation of the brief's claims vs the actual code.

## 1. What already exists (do NOT rebuild)

| Capability | Location | Status |
|---|---|---|
| Business Audit Engine + domain registry | `services/audit_engine.py` | full |
| Canonical Finding + lifecycle + urgency + data_quality_score | `models.py`, `finding_service.py` | full |
| Agent Runtime + policy-gated materialization (finding_id lineage) | `runtime.py` | full |
| Policy engine (dial + guardrails + risk floors) | `policy_engine.py`, `autonomy_service.py` | full |
| Deterministic executors (pricing / restock-PO / transfer, dialect-safe) | `agent_action_executor.py` | full |
| Unified learning (LearnedOutcome + OutcomeFeedback bridge, idempotent) | `outcome_learning.py` | full |
| Learning reconciliation (hourly Celery + endpoint) | `learning_reconciliation.py` | full |
| Strategy performance + attribution weighting + evidence tiers | `strategy_performance.py` | full |
| Recency weighting (half-life) + recency summary | `strategy_performance.py` | full |
| Decision scoring (deterministic weighted score + explanation) | `decision_scoring.py` | full |
| Recommendation stability (hysteresis) | `decision_scoring.apply_stability` | full |
| Root-cause (stockout_risk, dead_stock) | `root_cause.py` | partial (margin missing) |
| Recurring detection | `recurring_detection.py` | full |
| Operational health + freshness (fresh/stale bool) | `operational_health.py` | partial (no aging/unknown states) |
| Knowledge Graph projection + context | `knowledge_graph.py`, `graph_context.py` | full |
| Goal system + curated goal→domain mapping + history/trajectory | `goal_service.py`, `goal_domains.py` | full |
| Impact ledger + per-finding attribution | `impact_ledger_service.py` | full |
| Agent observability + cost estimation | `agent_observability.py` | full |
| Celery + Beat (audit, snapshot, reconciliation) | `celery_app.py`, `tasks/` | full |
| Postgres CI (runs pytest -q against PG 17) | `.github/workflows/ci.yml` | full |
| Frontend Action Center / Finding Detail / Weekly Report / autonomy | `frontend/src` | full |
| Arabic + English translations (363 keys each) | `lib/translations/*.ts` | full |

## 2. What is partially implemented

- **Root cause** — only `stockout_risk` and `dead_stock`; no margin leakage (Part 3).
- **Freshness** — only `fresh`/`stale` booleans; brief requires `fresh/aging/stale/unknown`
  states (Part 7).
- **Recommendation stability** — hysteresis exists but has no explicit "safety overrides
  stability" guard/test (Part 11).
- **Finding Detail** — has "why this strategy" + timeline but no root-cause section (Part 13).

## 3. What is genuinely missing

1. Margin root-cause engine + root-cause → recommendation connection + quality gates (§Part 3–5).
2. Regime-change detection (deterministic, conservative) (§Part 9).
3. Strategy performance with regime awareness (contextual relevance, not erasure) (§Part 10).
4. Data-freshness state model (`fresh/aging/stale/unknown`) (§Part 7).
5. Agent least-privilege test (§Part 19).
6. Non-destructive Postgres concurrency matrix (`test_phase11_postgres.py`) (§Part 2).
7. `docs/SUPPLIER_PRICE_SOURCES.md` + ROOT_CAUSE / RECOMMENDATION_ENGINE / OPERATIONAL_HEALTH /
   PRODUCTION_READINESS docs (§Part 23, 35).
8. Merchant-facing operational status in the Action Center (§Part 12).

## 4. What should NOT be rebuilt

All of §1. Specifically do NOT add: a second learning system, a second policy engine, a
second agent runtime, a graph database, supplier-price webhooks, or billing.

## 5. Discrepancies vs prior reports

- Phase 10 report's claim "Postgres CI results run in CI" is accurate; the sandbox has no
  Postgres, so Postgres-gated tests skip locally and are exercised only by CI.
- Phase 10 report listed root-cause for "margin/cash" as a *future improvement* — correct,
  it is not yet implemented.
- `test_phase9_postgres.py` previously contained a destructive `DROP SCHEMA` fixture; that
  was already corrected in Phase 10 (now idempotent `create_all`). No re-introduction.

## 6. Implementation plan (this phase)

1. Extend `root_cause.py` with margin-leakage hypotheses + a root-cause→candidate-strategy
   mapping + quality gates (supported/plausible/insufficient_evidence → recommendation
   eligibility).
2. Add `regime_detection.py` (deterministic, conservative) + integrate a regime signal into
   strategy relevance (without erasing history).
3. Extend `operational_health.py` freshness to `fresh/aging/stale/unknown` + config thresholds.
4. Add safety override to `apply_stability` (safety always wins) + tests.
5. Add agent least-privilege test + non-destructive `test_phase11_postgres.py`.
6. Docs + merchant operational-status UI + i18n.
