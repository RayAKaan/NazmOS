# NazmOS — Phase 2 Completion Report

Date: 2026-08-19

## A. Repository state discovered (vs Phase 1 report)

Re-audited before implementing. The Phase 1 code was intact and correct. New discoveries:

1. **The Knowledge Graph already existed** — `graph_entities` / `graph_relationships`
   models + `services/knowledge_graph.py` (upsert/expand/shortest_path) with three event
   projectors (`supplier.delivered`, `sale.completed`, `employee.clock_in`). The brief's
   §13–15 were already substantially satisfied; Phase 2 did **not** rebuild or migrate
   anything into a graph store (§14 "do not overbuild").
2. **The event processor already routed events** to memory + graph projectors. Phase 2
   added only the debounced continuous-audit hook.
3. **Supplier prices genuinely had no data model** — Phase 1's deferral was correct; Phase 2
   added a real `SupplierPrice` model (not a fake benchmark).
4. The test suite runs **SQLite** in-sandbox (Postgres integration is skipped); my first
   Phase 2 pass used Postgres-only SQL (`NOW()`, `INTERVAL`) and broke 3 tests — caught and
   fixed by making all new SQL dialect-safe (Python datetimes).

## B. Implementation (exact)

New files:
- `services/impact_ledger_service.py` — record/aggregate value created (§10–11).
- `services/audit_report_service.py` — merchant audit report aggregation (§21).
- `services/finding_approval_service.py` — WhatsApp finding approval (§9).
- `intelligence/agents/procurement_agent.py` — read/plan-first procurement agent (§19).
- `alembic/versions/b2c3d4e5f6a7_add_impact_ledger_and_supplier_prices.py`.
- `tests/test_phase2_foundation.py` (8 tests).
- Frontend: `hooks/useActionCenter.ts`, `components/dashboard/ActionCenter.tsx`,
  `components/dashboard/RunAuditButton.tsx`, `app/(dashboard)/findings/[id]/page.tsx`.

Modified:
- `models.py` — `ImpactLedger`, `ImpactType`, `ImpactVerification`, `SupplierPrice`.
- `agent_action_executor.py` — `_execute_transfer` (inter-branch, fail-closed) + `restock`
  executor wiring; removed the redundant `_execute_restock_request`.
- `policy_engine.py` — `transfer_inventory` (low) risk band; provisional 5k/20k thresholds
  retained but flagged (see §E).
- `tool_registry.py` — 3 new read-only tools (`suggest_inter_branch_transfers`,
  `get_supplier_prices`, `get_sales`) + 2 mutating tools (`transfer_inventory`, `restock`)
  registered read_only=False (never directly callable).
- `event_processor.py` — debounced, best-effort event-triggered audits.
- `inventory_agent.py` — rewritten to combine the original memory-based signals (SQLite-safe)
  with a live-inventory scan (best-effort); proposes `restock`/`discount`.
- `recovery_agent.py` — records observed recovered-value deltas to the ledger.
- `registry.py` — registered `procurement`.
- `finding_service.py` — `get_finding` (full detail) + dialect-safe SQL.
- `routers/audits.py` — +4 endpoints (`/findings/{id}`, `/report`, `/impact`,
  `/impact/entries`).
- `docs/openapi.json` — regenerated (185 paths).

## C. The audit loop (actual)

```
RunAuditButton → POST /audits/run (domain) → AuditRun(pending→running→completed|failed)
  → domain adapter (money_audit / inventory / recovery_match / compliance)
  → Finding(detected) with severity, evidence, impact, confidence, recommended action, risk
Finding → [Recovery/Inventory/Procurement agent propose()] → Agent Runtime
  → Policy Engine (classify_risk + autonomy dial) → AgentAction
  → auto (low risk) | draft/approval (medium) | mandatory approval (high)
  → executor (transfer / restock-PO) → verify_outcome → ImpactLedger(observed|estimated)
  → Action Center shows health / money-at-risk / approvals / impact
```

## D. Agent capabilities

| Agent | Reads | Tools | Mutates | Requires approval | Cannot do |
|---|---|---|---|---|---|
| Recovery | money audit, recovery match | generate_money_audit, find_recovery_matches, get_inventory, get_sales, forecast | — (proposes) | restock/PO via policy | autonomous purchasing |
| Inventory | memory + live inventory/transactions | get_inventory, get_sales, forecast, transfers | proposes restock/discount/transfer | transfer (low→auto within dial), restock (medium) | direct mutation |
| Procurement | demand/stock/supplier/price | get_inventory, get_supplier, get_supplier_prices, forecast, get_sales | **none** (read_only) | everything (proposes restock) | purchase, negotiation, supplier comms |
| Pricing / Finance / Supplier / Compliance | (unchanged from Phase 1) | (unchanged) | — | — | — |

## E. Policy system (actual)

`classify_risk` assigns a floor band per action type, escalated by financial impact
(≥ SAR 5,000 → medium, ≥ SAR 20,000 → high). `classify_and_disposition` combines the band
with the existing autonomy dial → `auto | draft | approve`. **Defaults are conservative:
no action auto-executes unless low-risk AND dial ≥ 95 AND confidence ≥ 0.90.** The 5k/20k
thresholds remain **provisional** — flagged for product validation, per §8.

## F. Knowledge Graph

Technology: **PostgreSQL relational projection** (`graph_entities` / `graph_relationships`,
already present). Entities: supplier, product, branch, employee. Relationships: `SUPPLIES`,
`SOLD_MOSTLY_AT`, `WORKS_AT`. Synchronization: explicit, event-driven (projectors in
`event_processor`). Source of truth: PostgreSQL; the KG is a read-only projection. Not
represented: substitutes/complements/seasonality (no supporting data yet), any full
inventory migration.

## G. Action Center (UX)

`ActionCenter` on the Dashboard: Business Health (score + issue counts), Money at Risk
(headline SAR), NazmOS Actions (completed count), Needs Your Approval (count + approve/
reject list), What Needs Attention (ranked findings with severity), Impact (observed vs
estimated). `RunAuditButton` drives the loop. `/findings/[id]` shows problem → evidence →
impact → reasoning → action → approval → execution → verification → actual impact. All on
the v2/v3 design system (Card / FigureHeadline / BentoGrid / tokens).

## H. Impact calculation

Observed impact = `money_recovered` deltas the Recovery Agent measures against a baseline
(`verified=true`, `verification=observed`). Estimated impact = findings'
`estimated_financial_impact_sar` / expected action value. The ledger and report **always
label estimates** ("not realized revenue"). Nothing represents an estimate as realized.

## I. Tests

| Check | Result |
|---|---|
| Backend full suite | ✅ **393 passed**, 90 skipped, 2 errors (pre-existing Postgres-only RLS tests) |
| Phase 1 tests | ✅ 11 passed |
| Phase 2 tests (new) | ✅ 8 passed |
| OpenAPI contract | ✅ golden regenerated (185 paths) |
| Frontend build | ✅ 38 routes incl. `/findings/[id]`, 0 errors |
| Frontend lint | ✅ 0 errors (6 pre-existing warnings) |
| Frontend tests | ✅ 9 passed |
| SQLite smoke (boot + create_all) | ✅ healthy; `impact_ledger`, `supplier_prices`, `audit_runs`, `findings` created |
| Tenant isolation | ✅ all new endpoints call `assert_business_access` |
| Agent safety | ✅ mutating tools not directly callable; policy gate enforced in runtime |

## J. Remaining issues

1. **Provisional risk thresholds (SAR 5k/20k)** need product validation.
2. **Debounce window (15 min) is a constant**, not configurable.
3. **No scheduler yet** — `scheduled`/`agent` audit triggers exist in the mapping but only
   `manual` + `event` triggers fire; cron/Celery wiring is Phase 3.
4. **Supplier prices have no ingestion source** — the model exists but is only populated
   manually; the honest `get_supplier_prices` returns empty until data is loaded.
5. **KG inventory domain not projected** — product↔category↔substitutes remain unmapped
   (no supporting data in the current schema).
6. **Postgres-only integration paths** (money-audit domain, live-inventory scan) run in CI,
   not this sandbox (SQLite).
7. Frontend Action Center uses `Promise.allSettled` so a missing/403 endpoint degrades to
   empty sections rather than erroring — acceptable for now but should be surfaced.

## K. Phase 3 recommendations

1. Wire a scheduler (Celery beat) for `scheduled` daily audits + `agent`-triggered re-audits.
2. Add a supplier-price ingestion path (POS/invoice import) so the comparison tool has data.
3. Product-validate the risk thresholds and expose them per-business in the autonomy UI.
4. Add orchestrator/CEO agent (the runtime + registry are ready for it).
5. Extend the KG with product↔category/substitute projections once data exists.
6. Add the Action Center to the mobile PWA home and the weekly Money Report from the ledger.
