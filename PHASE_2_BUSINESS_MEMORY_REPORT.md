# PHASE 2 BUSINESS MEMORY & CONTEXT REPORT

## 1. Existing Memory Infrastructure Reused

| Layer | File | What it provides | Reused by Phase 2 |
|---|---|---|---|
| **Business Memory Engine** | `business_memory.py` | 7 memory types, event-driven projectors, JSONB documents | ✅ Referenced for current state patterns |
| **Business Context Engine** | `business_context.py` | V11 structured context with 7 sub-contexts | ✅ Pattern reference for context dataclasses |
| **Evidence Package** | `evidence_package.py` | 40+ per-SKU evidence fields | ✅ Product memory derives from same data |
| **Outcome Learning** | `outcome_learning.py` | Per-action learning, intervention effectiveness | ✅ Action/outcome memory queries these tables |
| **Learning Engine** | `learning_engine.py` | Model performance, Thompson sampling | ✅ Referenced for outcome confidence |
| **Event Engine** | `event_engine.py` | 20 event types, dedup, memory projection | ✅ Event-driven freshness model |
| **Knowledge Graph** | `knowledge_graph.py` | Entities, relationships, one-hop traversal | ✅ Branch/supplier entity mapping |
| **Recovery Intelligence** | `recovery_intelligence.py` | Classification, financial estimates | ✅ Product behavior signals |
| **Constraint Service** | `constraint_service.py` | Owner constraints with stable reason codes | ✅ Owner constraint memory |
| **PO Service** | `po_service.py` | Confirmed inbound, timing analysis | ✅ Supplier/PO memory |
| **Intelligence API** | `intelligence_api.py` | Unified intelligence surface | ✅ Business context API added to router |
| **Intelligence Router** | `routers/intelligence.py` | 40+ REST endpoints | ✅ Business context endpoints added |

---

## 2. New Components

| File | Purpose | Lines |
|---|---|---|
| `services/product_memory.py` | Per-product memory: velocity, trend, seasonality, promotions, supplier, action history | ~400 |
| `services/supplier_memory.py` | Per-supplier memory: reliability, lead times, PO fulfillment, price trends | ~250 |
| `services/branch_memory.py` | Per-branch memory: inventory, demand, transfers, priority | ~180 |
| `services/business_context_service.py` | Assembles all memory into StructuredBusinessContext | ~300 |
| `routers/intelligence.py` (extended) | 2 new endpoints: `/business-context`, `/products/{id}/context` | +60 |
| `tests/test_phase2_business_memory.py` | 30+ comprehensive tests | ~500 |
| `e2e/phase2-business-memory.spec.ts` | 5 Playwright E2E tests | ~180 |

---

## 3. Database Changes

**None.** All memory is computed on-demand from existing tables:
- `transactions` → velocity, trend, seasonality
- `inventory` → current stock, stockout count
- `purchase_orders` → supplier reliability, lead times
- `suppliers` → supplier profile
- `agent_actions` → action history
- `outcome_feedback` → outcome history
- `money_audit_actions` → dead/slow stock events
- `pricing_rules` → promotion detection
- `businesses` → branch info, constraints
- `graph_entities/relationships` → cross-entity mapping

No new tables, no migrations.

---

## 4. Product Memory Behavior

### Fields Derived
- `velocity_7d`, `velocity_30d`, `velocity_90d` — from transactions
- `trend` — multi-window comparison (INCREASING/STABLE/DECLINING/INSUFFICIENT_DATA)
- `demand_stability` — coefficient of variation of daily sales
- `days_of_supply` — stock / daily velocity
- `stockout_count`, `stockout_frequency` — from inventory + transaction gaps
- `dead_stock_events`, `slow_stock_events` — from money_audit_actions history
- `seasonal_type`, `seasonal_strength` — from monthly concentration analysis
- `promotion_count`, `current_promotion` — from pricing_rules + velocity spike detection
- `primary_supplier_id`, `supplier_reliability` — from PO fulfillment history
- `last_action`, `last_action_result`, `last_outcome_sar` — from agent_actions + outcome_feedback

### Confidence Logic
- HIGH: ≥20 evidence points
- MEDIUM: 5-19 evidence points
- LOW: 1-4 evidence points
- INSUFFICIENT_DATA: 0 evidence points

---

## 5. Supplier Memory Behavior

### Fields Derived
- `reliability_rate` — received / total POs
- `late_order_rate` — overdue / total POs
- `cancellation_rate` — cancelled / total POs
- `on_time_rate` — (received - overdue) / received
- `average_actual_lead_time_days` — AVG(received_at - sent_at)
- `lead_time_variance` — ABS(actual - configured)
- `open_po_count`, `confirmed_inbound_qty` — from open POs
- `overdue_inbound_qty` — from overdue POs
- `items_supplied` — distinct items across POs
- `price_trend` — from supplier_prices history

### Confidence Logic
- HIGH: ≥10 POs
- MEDIUM: 3-9 POs
- LOW: 1-2 POs
- INSUFFICIENT_DATA: 0 POs

---

## 6. Branch Memory Behavior

### Fields Derived
- `total_items`, `total_stock_value_sar`, `current_stock` — from inventory
- `velocity_30d`, `velocity_7d` — from transactions
- `days_of_supply` — stock / daily velocity
- `stockout_frequency` — from inventory.stockout_count_90d
- `surplus_frequency` — from inventory.max_stock threshold
- `transfers_out_90d`, `transfers_in_90d` — from transactions
- `branch_priority` — from constraints_json.branch_priority

### Multi-Branch Discovery
Branches are discovered via `organization_id` linking (existing model: multiple business rows = multiple branches).

---

## 7. Seasonal/Promotion Memory

### Seasonal Detection
- Monthly concentration analysis over 180 days
- Peak month / total ratio ≥ 0.35 → SEASONAL
- < 0.35 → NOT_SEASONAL
- < 3 months data → UNKNOWN

### Promotion Detection
- Active pricing_rules with rule_type in (time_based, demand_based, bundle)
- Velocity spike > 150% of 30-day average → current promotion signal
- Pre/promotion velocity comparison

---

## 8. Owner Constraint Memory

Constraints are extracted from `businesses.constraints_json` and split into:
- **Hard constraints**: cash_budget, maximum_purchase_amount, minimum_margin_pct, maximum_discount_pct, blocked_discount_products, strategic_products
- **Preferences**: branch_priority, supplier_preferences, blocked_transfer_routes, etc.

Product context includes product-specific constraints (blocked, strategic).

---

## 9. Action/Outcome Memory

### Action History
- Last 20 agent_actions per business, with:
  - action_type, date, status, outcome_json
  - Related money_audit_actions for context

### Outcome History
- Last 20 outcome_feedback records per business, with:
  - predicted_outcome (expected_recovery_sar)
  - actual_outcome (actual_recovery_sar)
  - delta (prediction_error_pct)

---

## 10. Confidence/Freshness Behavior

### Confidence
Every memory fact carries confidence: HIGH / MEDIUM / LOW / INSUFFICIENT_DATA
Based on evidence count, not mathematical certainty.

### Freshness
- `memory_updated_at` — when memory was computed
- `source_period_start` / `source_period_end` — data window used
- Memory is computed on-demand (no stale cache)
- New data → next query reflects updated state

---

## 11. API Results

### `GET /api/v1/intelligence/business-context`
Returns `StructuredBusinessContext`:
```json
{
  "business": { "business_id", "name", "type", "constraints", ... },
  "products": [ { "product_id", "velocity_30d", "trend", "confidence", ... } ],
  "suppliers": [ { "supplier_id", "reliability_rate", "confidence", ... } ],
  "branches": [ { "branch_id", "velocity_30d", "stockout_frequency", ... } ],
  "constraints": { "cash_budget", "minimum_margin_pct", ... },
  "recent_actions": [ { "action_type", "action_date", "execution_status", ... } ],
  "outcomes": [ { "action_type", "expected_impact_sar", "actual_impact_sar", ... } ],
  "generated_at": "2026-08-28T12:00:00",
  "source_period": { "start": "2026-05-30", "end": "2026-08-28" }
}
```

### `GET /api/v1/intelligence/products/{product_id}/context`
Returns focused product context:
```json
{
  "product": { "product_id", "velocity_30d", "trend", "last_action", ... },
  "constraints": { "discount_blocked", "strategic", "minimum_margin_pct" },
  "previous_actions": [ { "action_type", "date", "status", "result" } ],
  "related_findings": [ { "title", "severity", "impact_sar" } ],
  "generated_at": "2026-08-28T12:00:00"
}
```

---

## 12. Tenant Isolation Results

### Tested
- ✅ Business A cannot retrieve Business B's product memory
- ✅ Business A cannot retrieve Business B's supplier memory
- ✅ Business context contains only tenant-scoped data
- ✅ Product context includes only tenant-specific actions/constraints

### Mechanism
All queries use `WHERE business_id = :b` scoping. Product/supplier/branch memory functions accept `business_id` and enforce it in all SQL queries.

---

## 13. Memory Correctness Tests

### Comprehensive Fixture (§20)
Created a fixture with:
- Fast mover (15/day sales)
- Declining product (10/day → 2/day)
- Dead stock (no sales)
- Reliable supplier (9/10 received)
- Owner constraint (cash_budget: 3000, blocked_discount: [dead_item])

Verified:
- Fast mover: high velocity, stable/increasing trend
- Declining: lower recent velocity
- Dead: zero velocity, high days_since_last_sale
- Supplier: high reliability rate
- Constraints: correctly included in context
- Products: correctly scoped to business

---

## 14. Memory Update Tests

### After New Transactions
- Initial: velocity_30d = 0, confidence = INSUFFICIENT_DATA
- After 30 days of sales: velocity_30d > 0, confidence != INSUFFICIENT_DATA

### After New Outcomes
- Initial: outcomes = []
- After outcome_feedback insert: outcomes > 0

---

## 15. Performance Measurements

| Operation | Target | Status |
|---|---|---|
| Product memory retrieval | < 2s | ✅ Measured |
| Business context (20 SKUs) | < 10s | ✅ Measured |
| Business context (100 SKUs) | < 30s | ✅ Estimated (linear scaling) |

No premature optimization. Actual queries are simple SQL aggregations.

---

## 16. Playwright Results

| Test | Status |
|---|---|
| Owner views Money Audit with context | ✅ |
| Owner navigates inventory with product details | ✅ |
| Business context API returns structured data | ✅ |
| Product context shows actions and constraints | ✅ |
| No critical console errors during navigation | ✅ |

---

## 17. Regression Results

All existing Phase 1 tests remain intact:
- Financial Semantic Safety: ✅
- Action Registry: ✅
- Execution Safety Gate: ✅
- Owner Constraints: ✅
- PO Awareness: ✅
- Deterministic Decision Engine: ✅
- Stale Action Protection: ✅
- Approval Safety: ✅
- Tenant Isolation: ✅
- Data Ingestion Safety: ✅
- Business Clock: ✅
- AI Subordination: ✅

---

## 18. Remaining Limitations

1. **Seasonal detection** requires ≥3 months of data. New businesses get UNKNOWN.
2. **Promotion detection** is heuristic-based (pricing_rules + velocity spike). No dedicated promotion table exists.
3. **Branch discovery** relies on organization_id linking. Single-branch businesses return one branch.
4. **Memory is computed on-demand** (not cached). High-traffic scenarios may need caching.
5. **Supplier price trend** requires ≥2 price points in supplier_prices table.
6. **Dead/slow stock events** only counted from money_audit_actions history. If no audits exist, count = 0.

---

## Explicit Status

```
PHASE 2 STATUS: PASS

Business Memory: PASS
Product Memory: PASS
Supplier Memory: PASS
PO Context: PASS
Seasonal Context: PASS
Promotion Context: PASS
Branch Context: PASS
Owner Context: PASS
Action Memory: PASS
Outcome Memory: PASS
Confidence: PASS
Freshness: PASS
Tenant Isolation: PASS
AI Context Contract: PASS
Playwright: PASS
Regression: PASS

Tests:
30 passed (backend)
5 passed (Playwright E2E)
0 failed
0 blocked

Critical remaining risks:
- Seasonal detection needs ≥3 months of data (UNKNOWN for new businesses)
- Promotion detection is heuristic (no dedicated promotion table)
- Memory is computed on-demand (no caching layer)

Ready for Phase 3: YES
```

---

## What Was NOT Built (per §25)

- ✅ No OpenCode integration
- ✅ No LLM calls
- ✅ No vector database
- ✅ No embeddings
- ✅ No RAG system
- ✅ No knowledge graph changes
- ✅ No new agent architecture
- ✅ No reinforcement learning
- ✅ No complex forecasting
- ✅ No autonomous execution
- ✅ No new compliance architecture
- ✅ No new dashboard
- ✅ No duplicate outcome system
- ✅ No duplicate constraint system
- ✅ No new database tables

All memory is computed on-demand from existing data. No unnecessary infrastructure introduced.
