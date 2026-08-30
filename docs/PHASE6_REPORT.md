# NazmOS — Phase 6 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 5)

Re-audited the Phase-5 remaining issues. Verdicts:

1. **Finding→action linkage incomplete** — confirmed. `Finding.agent_action_id` existed but
   was never populated, and `AgentAction` had **no** `finding_id` column, so multiple-actions-
   per-finding was unrepresentable. Fixed with a normalized column.
2. **Two learning systems separate** — confirmed. `LearnedOutcome` (business memory) and
   `OutcomeFeedback`+`learning_engine` (model performance) had no shared write path.
3. **Learning only in Recovery Agent** — confirmed; Inventory/Procurement did not consume it.
4. **`approve_agent_action` used Postgres-only `NOW()`** — confirmed; broke SQLite.
5. **Deadline trajectory** — the "miss by N days" projection was unimplemented.
6. Supplier-price webhooks — still genuinely unsupported (no purchase-cost source); left as
   ETL+PO, documented.

## B. Exact implementation

Backend new files:
- `alembic/versions/f6a7b8c9d0e1_add_finding_link_and_dq_note.py`.
- `tests/test_phase6_foundation.py` (5 unit tests).
- `tests/test_phase6_loop.py` (5 SQLite integration tests — the definitive loop proof).

Backend modified:
- `models.py` — `AgentAction.finding_id`; `LearnedOutcome.data_quality_note`.
- `runtime.py` — `_materialize_action` stores `finding_id` + back-links `Finding.agent_action_id`;
  uses dialect-safe datetimes + `record_unified_outcome`.
- `agent_action_executor.py` — `NOW()` → Python datetimes; terminal hook calls
  `record_unified_outcome`.
- `outcome_learning.py` — `confidence_tier`, `record_unified_outcome` (LearnedOutcome +
  OutcomeFeedback bridge), `intervention_effectiveness` gains `effectiveness` ratio,
  dialect-safe `_iso`.
- `inventory_agent.py` / `procurement_agent.py` — consume learning + rejection history.
- `goal_service.py` — `estimate_miss_days`, `goal_alignment_chain`.
- `routers/audits.py` — `/goals/{id}/trajectory`, `/goals/{id}/chain`.
- `docs/openapi.json` — regenerated (206 paths).

Frontend:
- `useActionCenter.ts` — `compare` + `learning` data.
- `ActionCenter.tsx` — "This week" comparison strip + "What NazmOS learned".

## C. Finding → Action linkage (final model)

Normalized: **one Finding → many AgentActions**, via `AgentAction.finding_id` (nullable FK).
`Finding.agent_action_id` is a convenience back-pointer to the most recent action. The
relationship is deterministic (carried in the candidate payload, never inferred from titles
or timestamps). The canonical chain is Finding → AgentAction → Outcome.

## D. Unified learning architecture

```
Action (terminal state)
  → record_unified_outcome()
      ├── LearnedOutcome        (business intervention memory → future agent behaviour)
      └── OutcomeFeedback       (model/action performance → learning_engine/Thompson sampling)
```

One action → one canonical outcome → two consumers. No third system; the semantic
distinction (business learning vs performance signal) is preserved and documented.

## E. Agent learning

- **Recovery** (Phase 5) — `learning_adjusted_action` (discount→transfer on repeated failure).
- **Inventory** (§7) — restock/discount proposals pass through `learning_adjusted_action`;
  repeatedly-failed restocks become transfers.
- **Procurement** (§8) — consumes `learning_adjusted_action` + rejection history (surfaces
  "owner previously rejected restocking (reason)" and lowers confidence).

## F. Goal intelligence

`estimate_miss_days` projects "N days late" from ≥2 measured snapshots (else "insufficient
data"; never fabricated). `goal_alignment_chain` returns the full goal→findings→actions→
impact→progress chain.

## G. Audit 2.0

Unchanged classification (Phase 5); now surfaced in the Action Center "This week" strip
with per-finding status links.

## H. Knowledge Graph

No new edges this phase (the operational graph was completed in Phase 5); the finding→action
`RECOMMENDS` edge now fires reliably because `finding_id` flows through materialization.

## I. End-to-end proof

`tests/test_phase6_loop.py` proves, with real SQLite round-trips:
1. finding → action (finding_id) → terminal outcome → LearnedOutcome + OutcomeFeedback +
   PRODUCES edge, all linked.
2. Replayed action → no duplicate outcome.
3. Two rejections → `learning_adjusted_action` flips discount → transfer (deterministic).
4. Cross-tenant: business A's outcomes invisible to business B.
5. finding_id flows through `_materialize_action` + back-links `Finding.agent_action_id`.

## J. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **439 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1–6 tests | ✅ 11+8+8+11+10+6 (loop) + 5 (unit) |
| OpenAPI contract | ✅ golden regenerated (206 paths) |
| SQLite smoke | ✅ `finding_id`, `data_quality_note` columns created |
| Frontend build | ✅ 38 routes, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## K. Remaining issues

1. **`_execute_transfer` / `_execute_pricing_update` / `_execute_restock_po` still use `NOW()`**
   — Postgres-intended execution paths (works in prod; dev uses `create_all`, not these executors).
2. **Recovery Agent still derives proposals from MoneyAudit actions, not Findings** — its
   `finding_id` is only set when context provides one; the RECOMMENDS graph edge is complete
   for the inventory/procurement path but not yet for recovery.
3. **Supplier-price webhooks** remain genuinely unavailable (no purchase-cost source).
4. **Cost rates are documented estimates**, not billed amounts.
5. **OutcomeFeedback bridge is best-effort** — if it fails, business learning still succeeds
   (intentional), but the two stores could theoretically drift; no reconciliation job.
6. Goal→finding mapping uses metric-name heuristics (`GOAL_ACTION_ALIGNMENT`); a merchant
   could define a metric outside the table and get an empty chain.

## L. Phase 7 recommendations

1. Route Recovery Agent proposals through Findings (so the RECOMMENDS edge is complete for
   the money-audit path too).
2. Add a reconciliation job for the LearnedOutcome↔OutcomeFeedback bridge.
3. Add a real goal→finding domain mapping (replace metric-name heuristics with a curated
   goal→domain table).
4. Surface the goal→finding→action→impact chain in the Finding detail UI (timeline 2.0).
5. Add supplier-price ingestion from any future POS purchase-document export (not webhook).
6. Only after the loop is proven end-to-end in production: begin higher-stakes capability
   exploration (still no Collective Buy / financing / autonomous financial transfers).
