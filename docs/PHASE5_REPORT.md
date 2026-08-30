# NazmOS — Phase 5 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 4)

Re-audited the 8 Phase-4 gaps. Verdicts:

| Gap | Status | Notes |
|---|---|---|
| 1. Learning pull-based | **CONFIRMED** | `learn_from_action` existed but nothing called it in the runtime. |
| 2. Goal progress history | **CONFIRMED** | No history model/scheduler. |
| 3. Product→category projection | **CONFIRMED** | `Item.category_id → Category` exists; no BELONGS_TO edge. |
| 4. Finding→action→outcome chain | **PARTIAL** | `RECOMMENDS`/`TARGETS` projectors existed but nothing emitted the events; no `PRODUCES`. |
| 5. Supplier price webhooks | **NOT FILLABLE** | Foodics/Salla webhooks only carry sales orders (`pos.order.received`), never purchase costs. Fabricating a webhook would violate "don't fabricate". Left as ETL+PO, documented. |
| 6. Autonomy thresholds not in UI | **CONFIRMED** | `settings/autonomy` only exposed the 0–100 dial, not floors. |
| 7. Recurrence doesn't change recommendations | **CONFIRMED** | Detection existed; no consumption. |
| 8. Audit 2.0 classification | **CONFIRMED** | Report had no NEW/PERSISTENT/IMPROVING/WORSENING/RESOLVED/RECURRING. |

Also discovered: `approve_agent_action` uses Postgres-only `NOW()` (fine in prod, but my
integration tests exercise `_record_terminal_outcome` directly on SQLite).

## B. Exact implementation

Backend new files:
- `services/audit_comparison.py` — deterministic finding classification.
- `alembic/versions/e5f6a7b8c9d0_add_goal_history_and_learning_uc.py`.
- `tests/test_phase5_foundation.py` (10 unit tests).
- `tests/test_phase5_learning_loop.py` (6 SQLite integration tests — the loop proof).

Backend modified:
- `agent_action_executor.py` — `_record_terminal_outcome` (learning + graph projection)
  wired into approve/reject; rejection returns `business_id`.
- `runtime.py` — auto-execute path also records learned outcomes.
- `outcome_learning.py` — idempotent `ON CONFLICT` upsert; `intervention_effectiveness`,
  `repeated_failures`, `learning_adjusted_action`, `ALTERNATIVE_ACTIONS`.
- `models.py` — `GoalProgressHistory`; unique constraint on `learned_outcomes.agent_action_id`.
- `goal_service.py` — `snapshot_goal_progress`, `goal_history`, `enrich_trajectory`, `sales` metric.
- `knowledge_graph.py` — `project_finding_to_graph`, `project_action_to_graph`,
  `PRODUCES` edge, `BELONGS_TO` category projection.
- `audit_engine.py` — projects findings into the KG at creation.
- `recovery_agent.py` — consumes `learning_adjusted_action`.
- `agent.py` — `/autonomy/explanation` endpoint.
- `routers/audits.py` — 5 new endpoints (goal history, snapshot, compare, effectiveness).
- `tasks/audit_tasks.py` + `celery_app.py` — `goal-progress-snapshot` daily task.
- `docs/openapi.json` — regenerated (204 paths).

Frontend:
- `settings/autonomy/page.tsx` — "What Nazm can do" (mode badges) + safety-floors panel.

## C. Closed learning loop

```
AgentAction → approve/reject/auto-execute → _record_terminal_outcome()
  → learn_from_action()  [ON CONFLICT upsert, one record per action]
  → LearnedOutcome{kind, approval, rejection_reason, expected vs actual impact}
  → learning_adjusted_action() / intervention_effectiveness()
  → RecoveryAgent (and future agents) change the next recommendation
  → project_action_to_graph() → PRODUCES/RECOMMENDS/TARGETS edges
```

This is now automatic at the runtime — no agent has to remember to call learning (§2), and
it is idempotent under retry/replay/worker restart (§3).

## D. Goal system

Schema: `business_goals` + `goal_progress_history`. Measurement: impact_ledger, inventory,
margin, sales (revenue/units, 30d), manual. History: `snapshot_goal_progress` (idempotent per
goal+hour) via daily Celery Beat. Trajectory: `enrich_trajectory` → on_track/at_risk/
off_track/achieved/regressing (deterministic). Orchestrator reads goals and ranks
goal-aligned actions first.

## E. Audit 2.0

`compare_audits` classifies findings (keyed domain|category|title) vs the previous 14-day
window: NEW (no prior), PERSISTENT (±10% impact), IMPROVING (impact fell), WORSENING
(impact rose), RESOLVED (prior no longer present), RECURRING (≥3× in 60d). Fully
deterministic; exposed at `/audits/compare`.

## F. Knowledge Graph

New edges: `BELONGS_TO` (product→category, only with real ledger category), `PRODUCES`
(action→outcome). Direct projection helpers `project_finding_to_graph` /
`project_action_to_graph` run at the canonical creation points (finding birth in the audit
engine; action terminal state in the executor). Agents get bounded context via
`finding_graph_context`/`product_graph_context`.

## G. Supplier prices

Sources remain: ETL uploads (with a `supplier` column) + received purchase orders. **No
webhook path** — Foodics/Salla only emit sales orders, not purchase costs, and fabricating
one would be wrong. Documented limitation.

## H. Autonomy

`/agent/autonomy/explanation` returns per-action mode (automatic / automatic-conditional /
approval / human) + immutable safety floors (min confidence, 5k/20k risk thresholds). The
settings page renders both. Backend stays authoritative; floors can't be weakened from the
frontend.

## I. Agent learning — concrete examples

- **Discounting failed repeatedly** → `learning_adjusted_action` returns `transfer_inventory`
  with the reason "Previous discount interventions repeatedly failed…", and the Recovery
  Agent emits that action with lower confidence + `learning_adjusted=true`.
- **Rejection stored** with reason ("seasonal product") → `rejections_for` surfaces it; a
  single rejection (confidence 0.6, threshold ≥2) does not flip future recommendations.

## J. End-to-end proof

`tests/test_phase5_learning_loop.py` proves (on SQLite, with real DB round-trips):
1. learned outcome auto-recorded and **idempotent** (replay → 1 record).
2. rejection stored as evidence with its reason.
3. `_record_terminal_outcome` writes learned outcome + `PRODUCES` graph edge.
4. finding → graph `AFFECTS` edge.
5. action → graph `TARGETS` + `PRODUCES` edges.
6. product → category `BELONGS_TO` (only with a real category row).

## K. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **428 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1–5 tests | ✅ 11 + 8 + 8 + 11 + 10 unit + 6 integration |
| OpenAPI contract | ✅ golden regenerated (204 paths) |
| SQLite smoke | ✅ `goal_progress_history`, unique constraint `uq_learned_outcome_action` confirmed |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## L. Remaining issues

1. **`approve_agent_action` still uses Postgres-only `NOW()`** — works in prod, but the
   full approve→learn path can't be exercised on SQLite (integration test targets
   `_record_terminal_outcome` directly).
2. **Finding→action linkage (`findings.agent_action_id`) is not populated end-to-end** —
   the RECOMMENDS edge only fires when a `finding_id` is available; the recovery agent
   doesn't yet back-link its actions to the originating finding.
3. **Goal trajectory "off_track"** is computed but the "miss by N days" estimate from §10
   is not yet implemented (needs deadline + per-day rate).
4. **Supplier-price webhooks** remain genuinely unavailable (no purchase-cost source).
5. **Cost rates are documented estimates**, not billed amounts.
6. Postgres-only integration paths run in CI, not this sandbox.

## M. Phase 6 recommendations

1. Populate `findings.agent_action_id` when the runtime materializes an action from a
   finding, completing the finding→action→outcome chain end-to-end.
2. Add the deadline-based "will miss target by N days" trajectory estimate.
3. Extend learning consumption to the Inventory + Procurement agents (rejection/effectiveness).
4. Expose the audit-2.0 comparison + goal history in the Action Center and weekly report.
5. Wire `OutcomeFeedback` (the pre-existing learning engine) to `LearnedOutcome` so the two
   AI-performance systems converge rather than coexist.
6. Supplier-price ingestion via any future POS purchase-document export (not webhook).
