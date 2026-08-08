# NazmOS Intelligence Architecture — Implementation Plan

**Vision:** Evolve NazmOS from a retail recovery API into an intelligence operating system built on a universal event stream, a living business memory, a knowledge graph, and autonomous business agents.

**Current stack:** FastAPI 0.119, Pydantic 2.9, SQLAlchemy 2.0 async, PostgreSQL, Redis, Celery, OpenTelemetry, Sentry.

**Approach:** Implement the architecture incrementally. Each phase ships real, testable functionality and preserves backward compatibility with existing merchants and POS integrations.

---

## Guiding Principles

1. **Event-first, not table-first.** Every change in the outside world becomes an immutable event.
2. **Postgres remains the source of truth.** Use extensions (TimescaleDB, Apache AGE) before introducing new databases.
3. **Agents collaborate through events, not direct RPC.** This keeps them decoupled and observable.
4. **Human approval by default.** Autonomy dials already exist; the new engines respect them.
5. **Explainability is required, not optional.** Every decision leaves evidence.
6. **No hardcoded RL/ML.** Start with rules and feedback loops; plug in advanced learning when data supports it.

---

## Component Map

```text
External Systems (POS, ERP, WhatsApp, CSV, …)
                    │
                    ▼
        ┌───────────────────────┐
        │  Universal Event Engine│  ← Phase 0
        └───────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   Business      Knowledge    Business
   Memory        Graph        Context
   Engine        Engine       Engine
   Phase 1       Phase 2      Phase 3
        │           │           │
        └───────────┴───────────┘
                    │
        ┌───────────────────────┐
        │ Temporal Reasoning    │  ← Phase 3
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ Decision Engine       │  ← Phase 4
        │ Explainability Engine │
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ Specialized Agents    │  ← Phase 5
        │ Planning Engine       │
        │ Simulation Engine     │
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ Learning Engine       │  ← Phase 6
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ Execution Engine      │  ← Phase 5/7
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ Intelligence API      │  ← Phase 7
        └───────────────────────┘
                    │
        ┌───────────────────────┐
        │ NazmOS Applications   │  ← Phase 7
        └───────────────────────┘
```

---

## Phase 0 — Universal Event Engine (Weeks 1–2)

**Goal:** Ingest, normalize, persist, and route every business event.

### Data model

- `events` table (append-only, partitioned by time, optionally TimescaleDB hypertable)
  - `id`, `business_id`, `occurred_at`, `received_at`, `source`, `source_id`, `event_type`, `version`, `payload` (JSONB), `actor_id`, `actor_type`, `correlation_id`, `causation_id`, `checksum`, `processed` boolean, `processed_at`.
- `event_types` registry table: `name`, `version`, `schema` (JSON Schema), `description`, `example`.
- `event_subscriptions` table: which consumers care about which event patterns.

### API endpoints

- `POST /api/v1/events` — authenticated event ingestion (single or batch).
- `GET /api/v1/events` — query stream with filters (business, type, time range, correlation).
- `GET /api/v1/events/types` — registry of supported event types and schemas.
- `POST /api/v1/events/replay/{correlation_id}` — replay a correlated stream for debugging.

### Async processing

- Celery task `process_event(event_id)`:
  1. Validate event against registry schema.
  2. Compute `checksum` (SHA-256 of canonical payload).
  3. Dedupe by `(business_id, source, source_id, checksum)`.
  4. Publish to Redis Pub/Sub channel `nazmos:events:{business_id}`.
  5. Mark `processed = true`.
- Add `process_unprocessed_events` beat task every minute.

### Adapters

- Refactor existing POS webhooks (`pos_webhooks.py`) to emit standardized events (`inventory.changed`, `sale.completed`, `payment.failed`, etc.) instead of writing directly to `transactions`.
- Keep backward compatibility: legacy tables become read projections of the event stream.

### Migrations

- `alembic/versions/xxx_add_events_and_event_types.py`
- Optional TimescaleDB setup migration if extension is enabled.

### Verification

- `pytest tests/test_event_engine.py`
- Contract test updated after event endpoints added.

---

## Phase 1 — Business Memory Engine (Weeks 3–4)

**Goal:** Maintain a queryable, living model of the business state.

### Data model

- `business_memory` table: one JSONB document per `business_id` + `memory_type`.
  - Types: `current_state`, `forecasts`, `goals`, `patterns`, `seasonality`, `failures`, `relationships`.
- `memory_updates` table: audit log of every mutation to memory (event id, path, old value, new value).

### Memory update pipeline

- Celery task `update_business_memory(event_id)` listens to the event stream.
- For each event, route to a memory projector:
  - `inventory.changed` → update current stock, reorder flags.
  - `sale.completed` → update sales trend, top products.
  - `supplier.delivered` → update supplier reliability pattern.
  - `price.updated` → update pricing history and elasticity.
- Projectors are idempotent and order-independent where possible; use `occurred_at` and event sequence for conflict resolution.

### API endpoints

- `GET /api/v1/intelligence/memory/{memory_type}?business_id=...`
- `PATCH /api/v1/intelligence/memory/goals` — set merchant goals (e.g., “increase profit by SAR 50,000 next month”).
- `GET /api/v1/intelligence/memory/changes` — recent memory mutations.

### Verification

- Property tests: replaying events yields deterministic memory state.
- `pytest tests/test_business_memory.py`

---

## Phase 2 — Knowledge Graph (Weeks 5–6)

**Goal:** Model the business as a connected graph of entities and relationships.

### Technology choice

- **Initial:** Relational graph tables (`graph_entities`, `graph_relationships`, `graph_entity_attributes`) backed by PostgreSQL GIN indexes and recursive CTEs.
- **Scale path:** Add Apache AGE extension or a dedicated Neo4j instance when query complexity/scale demands it. Keep the entity/relationship abstraction so the storage can be swapped.

### Data model

- `graph_entities`: `id`, `business_id`, `entity_type` (supplier, product, branch, employee, customer, …), `external_id`, `name`, `attributes` (JSONB), `vector` (optional pgvector).
- `graph_relationships`: `id`, `business_id`, `source_id`, `target_id`, `relation_type`, `strength` (0–1), `evidence_event_ids` (JSONB array), `valid_from`, `valid_until`.

### Population

- Graph projector consumes events:
  - `supplier.delivered` → `(Supplier)-[:SUPPLIES]->(Product)` with strength updated by frequency.
  - `sale.completed` → `(Product)-[:SOLD_MOSTLY_AT]->(Branch)`.
  - `employee.clock_in` → `(Employee)-[:MANAGES|WORKS_AT]->(Branch)`.

### API endpoints

- `POST /api/v1/intelligence/graph/entities`
- `POST /api/v1/intelligence/graph/relationships`
- `GET /api/v1/intelligence/graph/expand?entity_id=...&depth=2`
- `GET /api/v1/intelligence/graph/shortest-path?from=...&to=...`

### Verification

- Graph round-trip tests.
- `pytest tests/test_knowledge_graph.py`

---

## Phase 3 — Context & Temporal Reasoning (Weeks 7–8)

**Goal:** Enrich events with external context and answer time-based questions.

### Context Engine

- `business_context` table: `business_id`, `context_type` (weather, holiday, prayer_time, inflation, regulation, competitor, …), `effective_from`, `effective_until`, `payload`.
- Adapters fetch context:
  - Saudi holiday API / Hijri calendar.
  - Weather API per branch location.
  - SAGIA/MoC RSS for regulation alerts.
  - Inflation index (Saudi Central Bank or open data).
- Context is attached to events at ingestion time via `context_snapshot`.

### Temporal Reasoning

- Use TimescaleDB hypertable for `events` (if available) for fast time-range and gap-filling queries.
- Add `event_derivations` table: causal links between events (e.g., event B caused by event A with confidence).
- API endpoints:
  - `GET /api/v1/intelligence/timeline?business_id=...`
  - `GET /api/v1/intelligence/what-changed?business_id=...&since=...`
  - `GET /api/v1/intelligence/why?event_id=...` — returns causal chain.

### Verification

- Temporal query performance tests (<500ms for 90-day window).
- `pytest tests/test_temporal_reasoning.py`, `tests/test_context_engine.py`

---

## Phase 4 — Decision & Explainability Engine (Weeks 9–10)

**Goal:** Generate ranked, auditable decisions.

### Decision model

- `intelligence_decisions` table: `id`, `business_id`, `decision_type`, `input_event_ids`, `rules_applied`, `memory_snapshot`, `graph_evidence`, `context_evidence`, `candidate_actions` (JSONB), `ranked_action`, `confidence`, `expected_roi`, `risk_score`, `urgency`, `status` (draft/approved/rejected/executed), `approved_by`, `explanation`.
- Reuses and extends existing `agent_actions` and `decision_log` tables.

### Scoring

- Combine rule-based guards (existing) with:
  - Memory state (stock level, cash position).
  - Graph signals (supplier reliability, branch similarity).
  - Context signals (Ramadan, weather, inflation).
  - Temporal signals (trend, seasonality).
- Output a normalized score across ROI, risk, confidence, urgency, and business impact.

### Explainability

- Every decision record contains `explanation` with:
  - Why: primary drivers.
  - Evidence: event ids, memory paths, graph relationships.
  - Confidence: numeric and textual.
  - Expected ROI/risk.
  - Alternative actions and why they were ranked lower.

### API endpoints

- `POST /api/v1/intelligence/decisions/generate`
- `GET /api/v1/intelligence/decisions/{id}`
- `GET /api/v1/intelligence/decisions/{id}/explain`

### Verification

- Decision correctness tests with seeded scenarios.
- Explainability schema contract tests.

---

## Phase 5 — Agents, Planning, Simulation, Execution (Weeks 11–14)

**Goal:** Autonomous, collaborative agents that plan, simulate, and execute.

### Specialized agents

Each agent is a Celery task + state machine in `app/intelligence/agents/`:

- `inventory_agent.py`
- `pricing_agent.py`
- `finance_agent.py`
- `supplier_agent.py`
- `compliance_agent.py`
- `expansion_agent.py`
- `employee_agent.py`
- `customer_agent.py`

Agents communicate via events (not direct imports). An agent:
1. Subscribes to relevant event patterns.
2. Reads memory and graph.
3. Emits `agent.proposal` events.
4. Waits for human approval or auto-executes based on autonomy dial.

### Planning Engine

- `plans` table: `id`, `business_id`, `goal`, `steps` (ordered JSONB), `estimated_roi`, `estimated_cost`, `estimated_duration`, `status`, `simulation_id`.
- Planner uses backward chaining from a goal to required actions, reading memory/graph to fill constraints.
- Initial planner: deterministic heuristic. Later: LLM-assisted plan generation with guardrails.

### Simulation Engine

- `simulations` table: `id`, `business_id`, `scenario` (JSONB), `assumptions`, `results`, `status`.
- Simulation worker runs Monte Carlo or deterministic what-if on a copy of business memory.
- API: `POST /api/v1/intelligence/simulate` with scenario payload.

### Execution Engine

- Reuses existing adapters (POS, WhatsApp, email, supplier APIs).
- New `execution_jobs` table tracks every action sent to an external system.
- Execution workers idempotently apply approved actions and emit `execution.completed` / `execution.failed` events.

### Verification

- Agent collaboration tests.
- Planning and simulation golden scenarios.
- Execution idempotency and rollback tests.

---

## Phase 6 — Learning Engine (Weeks 15–16)

**Goal:** Close the feedback loop.

### Data model

- `outcome_feedback` table: `decision_id`, `executed_action_id`, `predicted_outcome`, `actual_outcome`, `delta`, `feedback_source` (manual/system), `timestamp`.
- `model_performance` table: per-decision-type accuracy, ROI error, latency.

### Learning loop

1. After an action executes, compare predicted vs actual outcome.
2. Store feedback.
3. Periodically retrain/refresh heuristics:
   - Start with simple weighted averages and Thompson sampling (bandits).
   - Add Bayesian updates for pricing/restock confidence.
   - Add graph learning for supplier/branch similarity when data volume justifies it.
4. A/B test new models against a holdback group per business tier.

### Verification

- Feedback loop tests.
- Offline evaluation on historical decisions.

---

## Phase 7 — Intelligence API & Application Refactor (Weeks 17–18)

**Goal:** Expose the unified intelligence layer and migrate apps to consume it.

### Intelligence API router

`app/routers/intelligence.py` with endpoints:

- `POST /api/v1/intelligence/analyze`
- `POST /api/v1/intelligence/predict`
- `POST /api/v1/intelligence/explain`
- `POST /api/v1/intelligence/plan`
- `POST /api/v1/intelligence/simulate`
- `POST /api/v1/intelligence/execute`
- `POST /api/v1/intelligence/observe`
- `POST /api/v1/intelligence/remember`
- `POST /api/v1/intelligence/reason`

Each endpoint takes a typed Pydantic request, routes to the correct engine(s), and returns a structured response.

### Application refactor

- Money Audit, Recovery Match, Pricing, Inventory, Supplier Intelligence, etc., become thinner clients of the Intelligence API.
- Dashboard queries memory instead of raw SQL for summary metrics.
- Chat/Agent feed calls `/intelligence/reason` and `/intelligence/plan`.

### Verification

- End-to-end tests for each app through the Intelligence API.
- Contract tests updated.
- Load tests against Intelligence API endpoints.

---

## Data & Infrastructure Roadmap

| Milestone | Required Changes |
|-----------|------------------|
| Phase 0 | PostgreSQL `events` table, Redis Pub/Sub, Celery tasks, event registry |
| Phase 1 | `business_memory` JSONB store, memory projectors |
| Phase 2 | Graph tables or Apache AGE extension |
| Phase 3 | TimescaleDB extension (optional but recommended), context adapters |
| Phase 4 | `intelligence_decisions` table, scoring functions |
| Phase 5 | `plans`, `simulations`, `execution_jobs` tables, agent task modules |
| Phase 6 | `outcome_feedback`, `model_performance` tables |
| Phase 7 | New `intelligence` router, refactor existing routers to consume it |

### Recommended extensions

- `timescaledb` for event time-series.
- `apache-age` or `pgvector` for graph/vector work.
- Keep Redis for event bus and Celery broker.

---

## Testing & Quality Gates

1. **Unit tests** for every projector, agent, and scoring function.
2. **Property tests** for event replay determinism.
3. **Contract tests** for Intelligence API endpoints.
4. **Temporal query benchmarks** on 1M synthetic events.
5. **Chaos tests** for event ordering, duplicate events, and projector crashes.
6. **Human-in-the-loop tests** for approval flow and explainability.

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Existing merchants break | Legacy tables remain as read projections; webhooks still write to them during Phase 0. |
| Event ordering issues | Each event carries `occurred_at` and monotonic sequence; projectors are idempotent. |
| Graph becomes a bottleneck | Start relational; add Apache AGE/Neo4j only when profiling proves it. |
| LLM costs spiral | Keep deterministic planners; LLM is optional and gated by feature flag. |
| Explainability becomes inaccurate | Store evidence event ids and memory snapshots at decision time. |

---

## Suggested Immediate Next Steps

1. Review and approve this plan.
2. Start **Phase 0** implementation:
   - Create `events`, `event_types`, `event_subscriptions` models and migrations.
   - Build `POST /api/v1/events` and async `process_event` Celery task.
   - Convert Foodics/Salla webhooks to emit standardized events while preserving legacy writes.
3. Add `pytest tests/test_event_engine.py` and update the OpenAPI golden file.

Once Phase 0 is solid, the rest of the engines have a reliable event backbone to build on.
