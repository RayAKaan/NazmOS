# NazmOS — Phase 4 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 3)

Re-audited before implementing. Findings that shaped the work:

1. **The learning engine already existed** — `OutcomeFeedback`, `ModelPerformance`,
   `services/learning_engine.py` (`record_feedback`, `compute_model_performance`,
   `thompson_sample_action`, `suggest_best_action`) + `learning_engine_advanced.py`. But it
   was tied to `IntelligenceDecision`, **not** to the agentic `AgentAction`/`Finding` loop.
   Phase 4 bridged them rather than building a second learning system.
2. **Goals were free-form** — a `goals` dict in the `goals` memory document (via
   `set_goals` / `GoalSetRequest`). Phase 4 added a structured `BusinessGoal` model that
   *coexists* with it.
3. **`AgentAction.decision_note` already existed** — the rejection-reason store; no new
   column was needed for §6.
4. **Data quality already existed** — `money_audit` carries `data_quality_score` +
   `missing_data` warnings (e.g. "cost price missing for many products").
5. **Config thresholds were hard-coded** (15-min debounce in `event_processor`, SAR 5k/20k
   in `policy_engine`, 0.90 confidence in `autonomy_service`) — moved to `config.py` with
   safety floors.
6. The KG, Celery Beat, orchestrator, and Impact Ledger were all as Phase 3 reported.

## B. Exact implementation

Backend new files:
- `services/goal_service.py` — structured goals + deterministic progress.
- `services/outcome_learning.py` — action→learned-outcome bridge (provenance kinds).
- `services/agent_performance.py` — per-agent metrics + cost-vs-value.
- `services/recurring_detection.py` — recurring-problem detection.
- `services/graph_context.py` — bounded graph context for agents.
- `alembic/versions/d4e5f6a7b8c9_add_goals_and_learned_outcomes.py`.
- `tests/test_phase4_foundation.py` (11 tests).

Backend modified:
- `models.py` — `BusinessGoal`, `LearnedOutcome`, `GoalDirection/Status`, `MemoryKind`.
- `config.py` — 4 configurable audit/autonomy settings.
- `policy_engine.py` — thresholds from config (floored at 5k/20k).
- `autonomy_service.py` — min-confidence from config (floor 0.90).
- `event_processor.py` — debounce from config (floored at 5m).
- `knowledge_graph.py` — `action.completed` + `supplier_price.changed` projectors.
- `orchestrator.py` — goal-aware ranking + `goal_aligned`/`approval_required`/`dependencies`.
- `weekly_report_service.py` — `health_trend` + recurring problems in the report.
- `routers/audits.py` — 10 new endpoints (goals, learning, performance, recurring,
  health-trend, graph context).
- `docs/openapi.json` — regenerated (198 paths).

Frontend:
- `hooks/useActionCenter.ts` — goals + health-trend data.
- `components/dashboard/ActionCenter.tsx` — Business goals panel + Health trend panel.

## C. Goals

Schema: `business_goals` (title, metric, direction decrease/increase/maintain, baseline,
target, current_value, deadline, priority, status, source, source_key). Measurement sources:
`impact_ledger` (sum observed impact by type), `inventory` (dead-stock value),
`margin` (avg gross margin %), or manual. Progress is computed deterministically by
`compute_progress` (baseline/current/target/direction → progress %, gap, trajectory) — never
LLM-derived. The orchestrator reads goals and ranks its plan so goal-aligned actions come
first (`GOAL_ACTION_ALIGNMENT`), with explainable `goal_aligned` flags.

## D. Learning loop

```
AgentAction (approved/rejected/executed)
  → learn_from_action()  (idempotent per action)
  → LearnedOutcome{kind: fact|inference|preference|hypothesis, approval, rejection_reason,
      expected vs actual impact, confidence, evidence_count}
  → rejections_for()/list_learned_outcomes()  → informs future agents (structured, not raw chat)
```

Rejections are stored with their reason; a single rejection is low-confidence evidence
(0.6), repeated evidence raises confidence — never a hard rule. No raw LLM context is stored.

## E. Knowledge Graph

Entities: supplier, product, branch, employee, finding, action, price. Relationships:
`SUPPLIES`, `SOLD_MOSTLY_AT`, `WORKS_AT`, `STOCKS`, `TRADES_STOCK_WITH`, `AFFECTS`,
`RECOMMENDS`, `TARGETS`, `HAS_PRICE`. Projectors: 9 (Phase 1–4), all event-driven and
idempotent. Agent usage: `finding_graph_context`/`product_graph_context` return bounded,
tenant-scoped one-hop neighborhoods with evidence (never causal claims).

## F. Agent performance

`/audits/performance` returns per-agent runs, recommendations, auto/queued counts, failures,
avg latency, observed value, and estimated inference cost. ROI is informational (a note
states it is not used to relax safety limits).

## G. Orchestrator

Reads structured goals + delegates to a curated subset (recovery/inventory/procurement/
margin) through the same runtime/policy engine, then produces a goal-ranked, unified plan
with `goal_aligned`, `approval_required`, and `dependencies` fields. It cannot bypass tools,
policies, approvals, or mutate state directly.

## H. Autonomy

Configurable: debounce, risk thresholds, min-confidence — all **floored** (debounce ≥5m,
thresholds ≥5k/20k, confidence ≤0.90 can't be weakened). Backend remains authoritative;
no frontend-only security. No "unrestricted mode" exists or was added.

## I. Data quality

Findings already carry `data_quality_score` + `missing_data` warnings from money_audit.
Phase 4 did not re-invent this; the goal/agent context surfaces it where relevant (a
finding with low data quality flows through with its evidence, which agents/merchant can
inspect). No new data-quality subsystem was needed.

## J. Frontend

Action Center now shows **Business goals** (progress bars + trajectory) and **Health trend**
(current vs previous + direction). Mobile Action Center + weekly report (Phase 3) remain.
All on the v2/v3 design system.

## K. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **412 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1–4 tests | ✅ 11 + 8 + 8 + 11 passed |
| OpenAPI contract | ✅ golden regenerated (198 paths) |
| SQLite smoke | ✅ boot healthy; `business_goals`, `learned_outcomes` + all prior tables create |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## L. Remaining issues

1. **No goal-progress scheduler** — `current_value` is measured on read, not on a cron.
2. **Learning loop is pull-based** — `learn_from_action` must be called after execution;
   the runtime does not yet auto-write outcomes on every action (only the recovery agent's
   impact path does). Wiring it into `runtime._materialize_action` is a small, safe follow-up.
3. **Goal→metric measurement is limited** to impact_ledger/inventory/margin; sales/cash/
   compliance goals need their own deterministic queries.
4. **Thresholds floored but not exposed in a UI** — config lives in env, not the autonomy
   settings screen.
5. **Cost rates remain documented estimates**, not billed amounts.
6. **KG still lacks product→category projection** (categories exist in the ledger; not
   projected yet).
7. Postgres-only integration paths run in CI, not this sandbox.

## M. Phase 5 recommendations

1. Auto-write learned outcomes in the runtime (close the pull-based gap in §L.2).
2. Add a goals scheduler + goal-progress history (trend over time, not just current).
3. Project product→category and finding↔action↔outcome chains into the KG from real data.
4. Expose autonomy configuration in the settings UI (with the same server-side floors).
5. Supplier-price webhook ingestion (Foodics/Salla purchase-cost events → SupplierPrice).
6. Begin the self-improving loop end-to-end: verify that recurring-problem escalation
   actually changes the next recommendation (structured outcome → suggestion).
7. Full business-audit 2.0 report distinguishing new/persistent/improving/resolved/recurring.
