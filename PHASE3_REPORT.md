# NazmOS — Phase 3 Completion Report

Date: 2026-08-19

## A. Repository discoveries (vs Phase 2)

Re-audited before implementing. Key findings that shaped the work:

1. **Celery + Celery Beat already existed** with a `beat_schedule` (forecast refresh,
   summaries, stale-upload cleanup, deletions, event reprocessing, learning refresh) and a
   sync-task pattern (`get_sync_session` + `asyncio.run`). Phase 3 added audit tasks to the
   *same* scheduler — no second background system.
2. **Business goals already existed** as a `goals` Business Memory document
   (`business_memory.set_goals`, `MemoryType.GOALS`). No separate goals table was needed.
3. **ContextBuilder already existed** (`services/context_builder.py`) with a `build()` that
   assembles a KSA-aware snapshot. Phase 3 did not fork it.
4. **The ETL already detected supplier + cost columns** (`schema_detector` maps
   `purchase_price`/`cost_price`; `normalize_dataframe` had a `supplier` passthrough gap).
   Phase 3 closed that gap to feed supplier-price ingestion.
5. **`ReportType.WEEKLY_SUMMARY` already existed** as a report enum; the weekly money report
   is a new computed endpoint over the Impact Ledger, not a new report pipeline.
6. The KG was (correctly) a PostgreSQL projection — Phase 3 expanded projectors, not the store.

## B. Exact implementation

Backend new files:
- `services/agent_observability.py` — run recording + per-provider cost estimation.
- `services/reaudit.py` — action_type → domain re-audit mapping + runner.
- `services/supplier_price_ingestion.py` — SupplierPrice ingestion (ETL + PO paths).
- `services/orchestrator.py` — CEO/orchestrator coordination loop.
- `services/weekly_report_service.py` — weekly report + explainable health score.
- `tasks/audit_tasks.py` — scheduled audit Celery tasks.
- `intelligence/agents/margin_agent.py` — Margin Agent.
- `alembic/versions/c3d4e5f6a7b8_add_agent_runs.py`.
- `tests/test_phase3_foundation.py` (8 tests).

Backend modified:
- `models.py` — `AgentRun` model.
- `runtime.py` — observability capture (in `finally`), re-audit-after-execution hook.
- `celery_app.py` — `audit_tasks` include + `daily-full-audit` beat entry.
- `data_normalizer.py` — `supplier` added to `FIELD_TARGETS`.
- `etl_pipeline.py` — supplier-price ingestion hook.
- `knowledge_graph.py` — 4 new projectors.
- `event_registry_seed.py` — 5 new event types.
- `agents/registry.py` — `margin` registered.
- `routers/audits.py` — +3 endpoints (`/weekly-report`, `/health`, `/orchestrate`).
- `docs/openapi.json` — regenerated (188 paths).

Frontend:
- `components/dashboard/MobileActionCenter.tsx` (new) — PWA quick-decision strip.
- `app/(dashboard)/weekly-report/page.tsx` (new) — weekly report UI.
- `app/mobile/page.tsx` — mounted MobileActionCenter.
- `components/layout/Sidebar.tsx` — "Weekly Report" nav item.

## C. Continuous audit (scheduled + event + re-audit)

- **Manual** — `POST /audits/run` (Phase 2, unchanged).
- **Scheduled** — Celery Beat `daily-full-audit` (06:00 Riyadh) iterates active businesses
  and runs all domains; idempotent (fresh AuditRun per domain), tenant-safe.
- **Event** — Phase 2 debounced hook (15-min) still applies.
- **Re-audit after action** — after a successful execution, `reaudit_after_execution` re-runs
  the affected domain(s) so findings are verified against real state.

## D. Knowledge Graph

Technology: PostgreSQL projection (`graph_entities` / `graph_relationships`), event-driven.
Entities: supplier, product, branch, employee, **finding** (new). Relationships:
`SUPPLIES`, `SOLD_MOSTLY_AT`, `WORKS_AT`, **`STOCKS`, `TRADES_STOCK_WITH`, `AFFECTS`** (new).
Projectors: `supplier.delivered`, `sale.completed`, `employee.clock_in` (existing) +
`price.updated`, `inventory.changed`, `transfer.completed`, `finding.created` (new).
Synchronization: explicit event projector in `event_processor`. Source of truth: PostgreSQL.
Not represented: substitutes/complements/seasonality (no data).

## E. Agent system

| Agent | Purpose | Context | Tools | Mutations | Approval | Memory |
|---|---|---|---|---|---|---|
| Recovery | recover trapped cash | latest Money Audit | money-audit, recovery-match, inventory, sales, forecast | proposes | restock/PO via policy | impact ledger |
| Inventory | stockout/overstock/dead stock | memory + live inventory | inventory, sales, forecast, transfers | proposes restock/discount/transfer | transfer low→auto, restock medium | — |
| Procurement | supplier pricing, alternatives | demand/stock/price | inventory, supplier, prices, forecast | **none** (read_only) | everything | — |
| Margin (new) | price/cost changes, thin margin | live product ledger | inventory, sales, prices | proposes margin_fix | medium → owner | — |
| Finance / Compliance / Pricing / Supplier | (Phase 1–2, read-only) | — | — | — | — | — |

Least privilege: agents only declare tools they need; the runtime gates every proposal.

## F. Orchestrator

`run_orchestrator` delegates to a curated subset (recovery/inventory/procurement/margin),
each running through the **same** runtime + policy engine, then ranks the resulting
pending/auto actions into a unified plan. It **cannot** mutate state directly, **cannot**
bypass policy, and does not include read-only informational agents (finance/compliance) in
its delegation set. Exposed at `/api/v1/audits/orchestrate`.

## G. Business goals

Goals live in the `goals` memory document (existing `set_goals`). The orchestrator reads
them to frame delegation. Goal-progress arithmetic (goal vs impact-ledger deltas) is not
yet computed — deferred to Phase 4 (needs a goal schema beyond free-form dicts).

## H. Autonomy

Unchanged from Phase 2/1: per-action-type dial (0–100) + guardrails (ceiling_sar, price %,
quiet hours, 2FA, confidence ≥0.90) + hard safety floors (pricing never >50, no
"unrestricted" mode). No new autonomy surface was added this phase — the existing controls
already satisfy §14's requirement, and the brief says don't invent new ones prematurely.

## I. Impact

Observed impact = Recovery-Agent measured `money_recovered` deltas (verified=true); estimated
impact = findings' estimated value / expected action value. The ledger + weekly report keep
observed vs estimated strictly separate with an explicit disclaimer.

## J. Cost

`agent_observability` records provider/model/tokens and estimates USD cost via documented
per-provider rates (groq ~$0.59/$0.79 per 1M in/out; google ~$0.10/$0.40; mock/deterministic
free). Current agents are deterministic (no LLM), so cost is ~$0; the tracking is the seam
for paid inference later. Deterministic logic still runs before any LLM (§25).

## K. Frontend

- **Action Center (desktop)** — Phase 2 (unchanged, still the primary surface).
- **Mobile Action Center** — new PWA strip: money at risk, impact, critical findings
  (quick decisions, not a shrunken desktop).
- **Weekly Report page** — impact breakdown (observed vs estimated), explainable health
  dimensions, top problems, completed actions, pending approvals.
- **Sidebar** — "Weekly Report" nav item.

## L. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **401 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS) |
| Phase 1 + 2 + 3 tests | ✅ 11 + 8 + 8 passed |
| OpenAPI contract | ✅ golden regenerated (188 paths) |
| SQLite smoke | ✅ boot healthy; `agent_runs` + all prior tables create |
| Frontend build | ✅ 38 routes incl. `/weekly-report`, `/findings/[id]`, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |

## M. Remaining issues

1. **Scheduled audits run in Celery only** — no in-process fallback when `USE_CELERY=False`
   (dev/sandbox); the task is registered but Beat doesn't run without a worker. Documented.
2. **Goal-progress not computed** — goals are free-form dicts; no delta vs impact ledger yet.
3. **Supplier prices have no POS/webhook ingestion** — only ETL uploads + received POs.
4. **Debounce window (15 min) and risk thresholds (SAR 5k/20k) are still hard-coded constants.**
5. **Cost rates are documented estimates**, not billed amounts (no billing integration).
6. **KG inventory domain is partial** — no product↔category projection yet (categories exist
   in the ledger but aren't projected).
7. **Orchestrator runs agents sequentially** — no parallelism; fine at current scale.
8. Postgres-only integration paths (money-audit domain, live-inventory scan) run in CI, not sandbox.

## N. Phase 4 recommendations

1. Wire the in-process (non-Celery) audit scheduler fallback + a management endpoint to
   trigger a scheduled audit manually.
2. Add a formal `goals` schema (or structured goal rows) so goal-progress vs the impact
   ledger can be computed and shown.
3. Add POS/webhook supplier-price ingestion (Foodics/Salla purchase events → SupplierPrice).
4. Project product↔category and finding↔action edges into the KG.
5. Product-validate the autonomy thresholds + make the debounce window configurable.
6. Add the Action Center + weekly report to the mobile PWA home as the default view.
7. Begin the self-improving loop: write structured outcome memories (approved/rejected
   patterns) from the impact ledger + verification results.
