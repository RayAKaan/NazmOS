# NazmOS — Agentic Architecture (Phase 1)

This document describes the agentic foundation added in Phase 1 and how it composes
with the systems that already existed. It is the reference for the Agent Runtime,
audit/finding lifecycles, policy engine, and security boundaries.

> Principle carried through Phase 1: **extend, don't rewrite.** Money Audit, Recovery
> Match, the autonomy dial, the event engine, and the LLM orchestrator already worked;
> Phase 1 added the reusable umbrella (audit engine + canonical findings) and the shared
> agent runtime on top of them, without forking their logic.

## 1. The loop (North Star)

```
AUDIT → FINDING → ACTION → APPROVAL → EXECUTION → VERIFICATION → IMPACT → RE-AUDIT ↺
```

Money Recovery remains the first real agent. The architecture is domain-extensible so
inventory, procurement, margin, finance, compliance, and operations agents can be added
without reworking the runtime.

## 2. Audit Engine + canonical Findings

- **`AuditRun`** (new) — one execution of an audit domain, lifecycle
  `pending → running → completed | failed`, with a `trigger` of `manual | scheduled |
  event | agent` (§11 continuous-audit foundation).
- **`Finding`** (new) — the canonical, domain-agnostic representation of a discovered
  problem (§3): domain, category, severity, title, explanation, evidence, affected
  entities, estimated financial impact, confidence, recommended action, action risk,
  status, and verification result.
- **Domain registry** (`services/audit_engine.py`) — `money_audit`, `inventory`,
  `recovery_match`, `compliance`. Each domain is a thin adapter over an existing service
  (e.g. `money_audit` reuses `money_audit_service.generate_money_audit`). Adding a domain
  = register a name + a `run()` callable.

### Finding lifecycle (§4)

```
detected → analyzed → recommended → awaiting_approval ─┬→ approved → executing → completed → verified
                                                      └→ rejected
```

`verification_result` records `{verified, actual_impact_sar, note}` — the IMPACT leg (§10).

## 3. Agent Runtime

- **Contract** (`intelligence/agents/base.py`) — every agent now declares identity,
  objective, tools, read-only flag, execution budget (`max_tool_calls`), event triggers,
  and a `verify_outcome()` hook. Existing agents keep their `propose()` contract unchanged.
- **Runtime** (`services/runtime.py`) — one loop for every agent:
  `context → propose → policy gate → execute(auto | draft) → verify → record`.
- **Recovery Agent** (`intelligence/agents/recovery_agent.py`) — the first real agent:
  reads the latest Money Audit, ranks actions by impact × urgency, proposes recovery
  actions, and measures actual recovered value on verification. No autonomous purchasing —
  execution is gated by the policy engine.

## 4. Model provider abstraction

`services/llm_orchestrator.py` **already** abstracts Groq / Gemini / mock behind a
normalized OpenAI-shaped interface with `LLM_PROVIDER_ORDER`, a circuit breaker, and rate
limiting. Phase 1 did **not** add a second abstraction — agents call the orchestrator and
never know which provider is live (§6).

## 5. Tool layer

`services/tool_registry.py` — one registry of tools, each a wrapper over an existing
service, each explicitly read-only (Phase 1) and risk-tagged. Boundary enforced:

```
Agent → Tool → existing NazmOS service → Database / external API
```

Agents never receive direct DB access (§7). `get_supplier_prices` is deferred — there is
no supplier-prices data model yet.

## 6. Policy / permission boundary (§8)

`services/policy_engine.py` layers a **risk classification** over the existing autonomy
dial (`autonomy_service.py`):

| Risk | Disposition |
|---|---|
| low | automatic (subject to autonomy dial + guardrails) |
| medium | draft → owner one-tap approval (web or WhatsApp) |
| high | mandatory human approval |

Financial-impact escalation thresholds (SAR 5,000 → medium, SAR 20,000 → high) are
conservative defaults, **not** product-verified limits — flagged for product review.

## 7. Approval lifecycle (human-in-the-loop, §9)

Every action is representable as WHAT / WHY / EVIDENCE / EXPECTED IMPACT / RISK /
REQUESTED ACTION. Approvals flow through the existing web (`agent.py`) **and** WhatsApp
paths — the `AgentAction` model already carries `whatsapp_message_id`/`whatsapp_status`.

## 8. Continuous auditing (§11)

`services/audit_triggers.py` maps business events (already ingested by the event engine)
to audit domains and agent types — e.g. `sale.completed → money_audit + recovery`.
This is the seam the scheduler/orchestrator will later call; no background machinery was
added in Phase 1.

## 9. Security boundaries

- Tenant isolation: RLS + `assert_business_access` on every new endpoint.
- No LLM → direct execution: policy gate sits between every proposal and any mutation.
- Read-only tools only in Phase 1; mutating tools require an explicit policy path.
- Audit logging: `AuditLog` + `AuditRun`/`Finding` provide the auditable spine.
- Mock LLM mode preserved (dev/test), fail-closed in production.

## 10. What is intentionally deferred (Phase 2+)

- Scheduling (cron/Celery wiring for `scheduled`/`event` audit triggers).
- Mutating tools (purchase orders, transfers) beyond the existing restock executor.
- Orchestrator/CEO agent (the runtime is the seam for it).
- Supplier-price data model (blocks `get_supplier_prices`).

---

# Phase 2 additions

## 11. Impact Ledger (§10–11)

`impact_ledger` + `services/impact_ledger_service.py` — the canonical record of value
created. Every entry carries `verification ∈ {pending, estimated, observed}` and `verified`
flag, so **estimates are never represented as realized revenue**. Feeds Dashboard IMPACT,
finding detail, and merchant ROI. The Recovery Agent records observed recovered-value
deltas here.

## 12. Safe mutating tools (§6)

Two legitimate mutations, both policy-gated and executed ONLY by the deterministic
executor after the policy engine approves:

- `transfer_inventory` (low risk) — inter-branch stock move (`_execute_transfer`),
  fail-closed on insufficient source stock.
- `restock` (medium risk) — purchase-order creation (existing `_execute_restock_po`).

The tool registry exposes them (`read_only=False`) but `call_tool` refuses direct calls —
the boundary is `Agent → Tool → Policy → Executor`, never `LLM → DB` (§7).

## 13. Continuous auditing (§5)

`event_processor._maybe_run_event_triggered_audits` now runs debounced, domain-specific
audits on matching events (`sale.completed → money_audit`, etc.) — never a full audit per
trivial event, and a failed audit can never fail event processing. All SQL is dialect-safe
(Python datetimes, no `NOW()`/`INTERVAL`), so the SQLite dev/test path works.

## 14. Supplier price intelligence (§16)

`supplier_prices` model + `get_supplier_prices` tool. Returns only recorded observations
with their source; the summary explicitly states it is "not a market benchmark."

## 15. Agents (§17–19)

- **Recovery Agent** — upgraded to record observed recovered-value deltas to the ledger.
- **Inventory Agent** — memory + live-inventory scan; proposes `restock`/`discount`.
- **Procurement Agent** — read/plan only (`read_only=True`); never spends money, never
  communicates with suppliers; outputs `restock` proposals for owner review.

## 16. Finding detail + Audit report + Action Center (§3, §20, §21)

Backend: `/audits/findings/{id}` (trust layer), `/audits/report` (merchant audit report),
`/audits/impact` + `/audits/impact/entries` (ROI). Frontend: `ActionCenter` (health /
money-at-risk / approvals / impact) + `RunAuditButton` on the Dashboard, and a
`/findings/[id]` detail page — all on the existing v2/v3 design system.

## 17. Knowledge Graph responsibilities (PostgreSQL vs KG)

The KG already existed (Phase 1: `graph_entities` / `graph_relationships` with
`supplier.delivered`, `sale.completed`, `employee.clock_in` projectors). Phase 2 did **not**
rebuild it or introduce a separate graph store: **PostgreSQL remains the transactional
source of truth; the KG is a read-only projection** updated explicitly by the event
processor. No inventory was migrated into a graph.

---

# Phase 3 additions

## 18. Continuous scheduled auditing (§2)

`app/tasks/audit_tasks.py` + Celery Beat entry `daily-full-audit` (06:00 Asia/Riyadh).
`run_audits_for_business` re-runs the reusable engine per business; runs are idempotent
(fresh AuditRun per domain) and tenant-safe. Event-triggered runs (Phase 2) + manual +
scheduled + agent triggers now all flow through one engine.

## 19. Re-audit after actions (§3)

`services/reaudit.py` maps action_type → affected domain(s); after a successful execution
the runtime re-runs the domain audit so a finding is verified against real business state,
never just the API result.

## 20. Supplier-price ingestion (§4–5)

`services/supplier_price_ingestion.py` writes real `SupplierPrice` records from (a) ETL
uploads that carry a `supplier` column and (b) received purchase orders. `supplier` was
added to the ETL normalizer's field targets. Every record keeps supplier, SKU, price,
currency, effective date, source, and business scope. `get_supplier_prices` now returns
real data (and still disclaims "not a market benchmark").

## 21. Knowledge Graph expansion (§6–7)

New event-driven projectors: `price.updated` (supplier → product SUPPLIES), `inventory.changed`
(branch → product STOCKS), `transfer.completed` (branch → branch TRADES_STOCK_WITH + STOCKS),
`finding.created` (finding → product/branch AFFECTS). New event types seeded:
`transfer.completed`, `finding.created`, `supplier_price.changed`, `action.completed`,
`action.verified`. PostgreSQL remains the source of truth; the KG stays a read-only projection.

## 22. Margin Agent (§10)

`intelligence/agents/margin_agent.py` — thin-margin detection over the live product ledger,
proposes `margin_fix` (medium risk → owner approval). Registered in the registry.

## 23. Orchestrator (§11–12)

`services/orchestrator.py` — collects structured proposals from a curated agent subset
(recovery/inventory/procurement/margin), each through the SAME runtime + policy engine,
then produces a ranked, unified action plan. It never bypasses domain policies and never
executes anything itself. Exposed at `/api/v1/audits/orchestrate`.

## 24. Business goals (§13)

Goals live in the `goals` Business Memory document (`business_memory.set_goals`); the
orchestrator reads them to frame delegation. No separate goals table was added — the
memory-based abstraction already existed.

## 25. Agent-run observability + cost control (§24–25)

`agent_runs` table + `services/agent_observability.py` record every agent execution
(agent, business, trigger, tools, decisions, latency, status) and estimate inference cost
via per-provider USD rates (mock/deterministic are free). The runtime captures runs in a
`finally` block so observability never breaks an agent run.

## 26. Weekly Money Report + explainable health (§17–18)

`services/weekly_report_service.py` + `/api/v1/audits/weekly-report` and
`/api/v1/audits/health`. Observed vs estimated impact are strictly separated; the health
score breaks down into 7 traceable dimensions (inventory/margins/procurement/cash/sales/
compliance/operations), each derived from findings.

## 27. Frontend (§15–17)

`ActionCenter` (Phase 2) is joined by `MobileActionCenter` (PWA quick-decision strip:
money at risk / impact / critical findings) and a `/weekly-report` page (impact breakdown,
health dimensions, top problems, completed actions). All on the v2/v3 design system.

---

# Phase 4 additions

## 28. Structured Business Goals (§2–3)

`business_goals` table + `services/goal_service.py` — a measurable goal (metric, direction,
baseline, target, deadline, source) that **coexists** with the free-form `goals` memory
document (not a replacement). Progress % / gap / trajectory are computed **deterministically**
from the Impact Ledger or business data via `compute_progress` — never LLM-generated.

## 29. Goal-aware Orchestrator 2.0 (§4, §19–20)

The orchestrator now reads structured goals and ranks its unified plan so goal-aligned
actions come first (`GOAL_ACTION_ALIGNMENT` maps metric → action types). Explainable: each
plan item carries `goal_aligned` and `approval_required`. It still delegates through the
same runtime/policy engine and never mutates or bypasses policy.

## 30. Structured outcome learning (§5–8)

`learned_outcomes` table + `services/outcome_learning.py` — distills every meaningful
AgentAction into a structured memory with provenance `kind` (`fact | inference | preference
| hypothesis`), approval, rejection reason (from `AgentAction.decision_note`), expected vs
actual impact, confidence, and evidence count. Idempotent per action (evidence_count grows).
No raw LLM context is stored; a single rejection never becomes a permanent rule.

## 31. Configurable audit + autonomy (§13–15)

`AUDIT_DEBOUNCE_MINUTES`, `RISK_ESCALATE_MEDIUM_SAR`, `RISK_ESCALATE_HIGH_SAR`,
`AGENT_AUTO_MIN_CONFIDENCE` moved to `config.py` — with **hard safety floors** (debounce ≥5m,
thresholds can only be raised, never lowered below the 5k/20k defaults). No frontend-only
security; the backend stays authoritative.

## 32. Agent performance + cost-vs-value (§16–17)

`services/agent_performance.py` + `/api/v1/audits/performance` — per-agent runs,
recommendations, auto/queued counts, failures, latency, observed value, and estimated
inference cost. ROI is informational only (never used to relax safety limits).

## 33. Recurring problems + health trend (§22–24)

`services/recurring_detection.py` flags findings recurring ≥3× in 60 days (escalation, not
repeat recommendation). `weekly_report_service.health_trend` computes current vs previous
7-day health with direction — every score traceable to findings.

## 34. Knowledge Graph expansion + agent context (§9–10)

New projectors: `action.completed` (finding → action RECOMMENDS, action → product TARGETS),
`supplier_price.changed` (supplier → price HAS_PRICE). `services/graph_context.py` builds
bounded, tenant-scoped graph context for a finding/product — never a full-graph dump, and
correlation is never labeled causality (§11).

## 35. Frontend (§15–17, §26)

Action Center gains a **Business goals** panel (progress bars + trajectory) and a
**Health trend** panel (current vs previous + direction), fed by `/audits/goals` and
`/audits/health-trend`. All on the existing v2/v3 design system.

---

# Phase 5 additions — closing the learning loop

## 36. Runtime-driven learning (§2–3)

`agent_action_executor._record_terminal_outcome` is the **canonical integration point**:
`approve_agent_action`, `reject_agent_action`, and the runtime's auto-execute path all call
it, so a `LearnedOutcome` is written automatically at every terminal state — agents never
remember to call learning themselves. Idempotency is DB-enforced via
`uq_learned_outcome_action UNIQUE (agent_action_id)` + `ON CONFLICT DO UPDATE` (a
retry/replay can never duplicate or inflate evidence).

## 37. Learning changes recommendations (§5–7)

`outcome_learning.learning_adjusted_action` + `ALTERNATIVE_ACTIONS` map a repeatedly-failed
action type to a deterministic alternative (e.g. discount → transfer_inventory), consumed
by the Recovery Agent with an evidence-based reason. `intervention_effectiveness` aggregates
success rate / rejection count / actual impact. Rejections are stored with their reason
(`AgentAction.decision_note`); a single rejection never becomes a rule (threshold ≥2).

## 38. Goal progress history + trajectory (§8–11)

`goal_progress_history` + `goal_service.snapshot_goal_progress` (idempotent per goal+hour)
record deterministic snapshots; a Celery Beat task (`goal-progress-snapshot`, daily 07:00)
drives it. `enrich_trajectory` computes ON_TRACK / AT_RISK / OFF_TRACK / ACHIEVED /
REGRESSING from measured history. New deterministic metrics: `sales` (revenue/units, 30d).

## 39. Audit 2.0 comparison (§12–14)

`audit_comparison.compare_audits` classifies each finding as NEW / PERSISTENT / IMPROVING /
WORSENING / RESOLVED / RECURRING by deterministic key comparison (domain|category|title)
against the previous window, with impact deltas for improving/worsening.

## 40. Knowledge Graph completion (§15–16)

`project_finding_to_graph` + `project_action_to_graph` project findings and actions directly
at creation (AFFECTS, RECOMMENDS, TARGETS, PRODUCES); `_project_inventory_changed` adds
product → category `BELONGS_TO` (only when the ledger has a real category).

## 41. Autonomy explanation (§18–19)

`/api/v1/agent/autonomy/explanation` returns per-action mode (automatic / automatic-conditional
/ approval / human) + the immutable safety floors; the autonomy settings page renders it.

## 42. Supplier prices (§17)

No fabrication: Foodics/Salla webhooks only carry sales orders (`pos.order.received`), not
purchase costs, so supplier-price ingestion remains ETL + received-PO only. Documented
limitation — no webhook path was invented.

---

# Phase 6 additions — the complete lineage

## 43. Finding → Action linkage (§2–3)

`AgentAction.finding_id` (normalized: many actions per finding) is populated
deterministically by `runtime._materialize_action` from the candidate's `finding_id` —
never inferred from titles. `Finding.agent_action_id` is retained as a back-pointer to the
most recent action. The canonical chain is Finding → AgentAction → Outcome.

## 44. Unified learning architecture (§5–6)

`outcome_learning.record_unified_outcome` is the single write path: one action → one
canonical outcome → two consumers:
- **LearnedOutcome** — business intervention memory (future agent behaviour).
- **OutcomeFeedback** — model/action performance signal (existing learning engine /
  Thompson sampling).
Semantically distinct, now connected; no third learning system.

## 45. Learning confidence + effectiveness (§9–10)

`confidence_tier(evidence_count)` → weak/moderate/strong/very_strong (deterministic, never
LLM-invented). `intervention_effectiveness` now returns `effectiveness` = actual/expected
impact (never estimated-as-actual).

## 46. Learning consumption across agents (§7–8)

Recovery (Phase 5), **Inventory**, and **Procurement** agents all consume
`learning_adjusted_action` (repeated failures → alternative) + rejection history.

## 47. Deadline trajectory + goal chain (§11–12)

`goal_service.estimate_miss_days` (projected "N days late" from measured history, or
"insufficient data"). `goal_alignment_chain` exposes goal → findings → actions → impact →
progress. Endpoints: `/goals/{id}/trajectory`, `/goals/{id}/chain`.

## 48. Postgres/SQLite compatibility (§27)

`approve_agent_action` / `reject_agent_action` now use Python datetimes instead of `NOW()`;
timestamp serialization uses a dialect-safe `_iso` helper.

## 49. Data quality in decision history (§20)

`learned_outcomes.data_quality_note` preserves "supplier costs missing for N% of SKUs" so
later re-audits can revisit stale conclusions.

## 50. Action Center 3.0 (§13–16)

"This week" audit-comparison strip (new/improving/worsening/resolved/recurring) + "What
NazmOS learned" (success rate, effectiveness, observed value), fed by `/audits/compare` and
`/audits/learning/effectiveness`.

---

# Phase 7 additions — unified, production-grade lineage

## 51. Recovery is now Finding-driven (§2–3)

The Recovery Agent consumes canonical `findings` (domain=money_audit) — never
`list_money_audit_actions` directly. Every proposal carries `finding_id`, which flows
through the runtime into `AgentAction.finding_id` and the graph RECOMMENDS edge. Money
Audit remains the domain-specific analytical engine; the audit engine's `money_audit`
adapter turns its results into Findings.

## 52. Learning reconciliation (§8–9)

`outcome_feedback.agent_action_id` (unique) closes the lineage gap; `record_unified_outcome`
uses `ON CONFLICT DO NOTHING`. `services/learning_reconciliation.py` enforces the invariant
"every terminal action has both a LearnedOutcome and an OutcomeFeedback", exposed at
`/audits/learning/reconcile` and run hourly via Celery Beat (`learning-reconciliation`).

## 53. Curated goal → domain mapping (§10–12)

`services/goal_domains.py` replaces metric-name heuristics with a curated catalogue
(`reduce_dead_stock`, `improve_margin`, `reduce_stockouts`, `reduce_purchase_cost`,
`increase_revenue`), each mapping to domains/categories/agents. The orchestrator now
returns `directly_aligned | indirectly_relevant | unrelated`.

## 54. Finding decision timeline (§7)

`services/finding_timeline.py` reconstructs the chronological decision chain
(found → approved/rejected → executed/failed → verified → impact → learned) from real
records; the finding-detail page renders it. Never exposes chain-of-thought.

## 55. Postgres/SQLite cleanup (§20)

`_execute_pricing_update`, `_execute_restock_po`, `_execute_transfer`, `approve`/`reject`
now use Python datetimes/uuid instead of `NOW()`/`gen_random_uuid()`.

---

# Phase 8 additions — per-finding impact + strategy intelligence

## 56. Per-finding impact attribution (§2–6)

`impact_ledger.attribution` (direct | partial | business_level | estimated | unattributable)
distinguishes per-action impact from coarse business deltas. `finding_observed_impact`
returns the per-finding breakdown (direct/partial/business_level/verified). Recovery
`verify_outcome` now attributes per-finding when a `finding_id` is available, and falls
back to a business-level delta **explicitly marked `attribution_scope = business`** —
never presented as per-action.

## 57. Strategy Performance Engine (§7–11)

`services/strategy_performance.py` aggregates, per action type, attempts / approved /
rejected / executed / verified / failed / observed vs expected value / success_rate /
effectiveness / evidence_tier — from the existing `LearnedOutcome` (no new learning DB).
Evidence tiers are deterministic and configurable (`insufficient` <3, `preliminary` 3–9,
`strong` ≥10). Contextual segmentation by finding category omits tiny samples.
`best_strategy_for_finding` ranks candidate strategies deterministically.

## 58. Adaptive ranking, policy-gated (§12–13)

The orchestrator now sorts within each goal/decision bucket by strategy effectiveness,
then risk. Strategy success **never** bypasses the policy engine — the order remains
ranking → policy → approval/auto → execution.

## 59. Read-only API (§11)

`/audits/strategy-performance`, `/audits/strategy-performance/{type}/categories`,
`/audits/findings/{id}/impact`. The Action Center renders a minimal strategy table
(strategy / success / effectiveness / evidence tier).

---

# Phase 9 additions — production hardening + decision quality

## 60. Concurrency + idempotency proof (§2–5, §30)

`tests/test_phase9_concurrency.py` (SQLite) proves application-level idempotency:
concurrent terminal-outcome writes converge to one LearnedOutcome + one OutcomeFeedback.
`tests/test_phase9_postgres.py` (Postgres-gated, runs in CI) proves real `FOR UPDATE`
semantics: two concurrent transfers cannot overdraw inventory (stock ≥ 0), and a second
approval of an already-approved action is a no-op.

## 61. Decision-quality scoring (§8–14)

`services/decision_scoring.py` — a deterministic, documented recommendation score:
`0.15·goal + 0.20·impact + 0.15·urgency + 0.10·confidence + 0.10·data_quality +
0.20·strategy − 0.10·risk`, every input log/percent-normalized to 0–1. Ranking is separate
from policy (§13); the score never grants execution permission.

## 62. Urgency + data quality on findings (§11–12)

`findings.urgency` (deterministic: severity + financial exposure + recurrence) and
`findings.data_quality_score` (propagated from money_audit's real data-quality score).
`audit_engine.compute_urgency` is the single deterministic urgency model.

## 63. Attribution-weighted strategy performance (§7)

`strategy_performance.ATTRIBUTION_WEIGHT` weights observed value: direct=1.0, partial=0.7,
business_level=0.3, estimated/unattributable=0. Weak attribution no longer inflates
strategy effectiveness.

## 64. Explainable recommendations (§14–15)

`/audits/findings/{id}/recommendation` returns the selected strategy, evidence-backed
alternatives, and a structured explanation (impact, urgency, confidence, data quality,
historical effectiveness, evidence tier, approval). The finding-detail page renders
"Why NazmOS recommends this".

---

# Phase 10 additions — production hardening, recency, root-cause

## 65. Postgres CI is a real gate (§3–4)

`.github/workflows/ci.yml` already runs `pytest -q` against Postgres (service `postgres:17`),
so the Postgres-gated concurrency suite executes in CI and fails the build. Fixed a
destructive fixture (`DROP SCHEMA public CASCADE`) in `test_phase9_postgres.py` that would
have clobbered the shared test DB — it now uses idempotent `create_all` + unique UUIDs.

## 66. Recency-weighted strategy performance (§11–13)

`strategy_performance.recency_weight` (exponential half-life, `RECENCY_HALF_LIFE_DAYS=90`,
deterministic/configurable) + `strategy_summary_recency` — recency shifts *relevance*, never
rewrites raw history (attempts/success_rate/evidence_tier stay raw, §12–13).

## 67. Root-cause investigation (§15–21)

`services/root_cause.py` — evidence-based hypothesis engine for recurring findings
(stockout_risk, dead_stock) using real fields (reorder level, lead time, velocity). Returns
SUPPORTED / PLAUSIBLE / INSUFFICIENT_EVIDENCE, and `uncertain` when data is absent — never
a fabricated cause. Exposed at `/audits/findings/{id}/root-cause`.

## 68. Recommendation stability (§23)

`decision_scoring.apply_stability` (hysteresis): scores within `RECOMMENDATION_MIN_DELTA`
(0.03) keep the previous selection; a meaningful change still flips. No thrashing.

## 69. Operational health + data freshness (§25–28)

`services/operational_health.py` — HEALTHY / DEGRADED / REQUIRES_RECONCILIATION plus
inventory/sales/supplier-price freshness (with explicit "unknown" when no timestamp).
Exposed at `/audits/operational-health`; a merchant-facing summary line is separate from
the operator detail.
