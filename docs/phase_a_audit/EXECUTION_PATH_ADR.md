# ADR: Execution Path Duality (Simulated vs Real)

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

Two execution paths coexist intentionally:

| Path | Module | Mode | Purpose | Entry Points |
|------|--------|------|---------|--------------|
| **Simulated** | `execution_engine.py` | Simulation + event emission | Plan tracking, idempotency, audit trail | `intelligence_api.py`, `routers/intelligence.py` |
| **Real** | `agent_action_executor.py` | Actual DB mutations | Human/auto-approval execution | `routers/agent.py`, `routers/whatsapp.py`, `autonomy_service.py`, `runtime.py` |

Both paths handle the same action types but serve different lifecycle stages.

---

## 2. Path A: `execution_engine` (SIMULATED)

### 2.1 Behavior
- Creates `ExecutionJob` records with idempotency keys (business_id + action_type + entity_type + entity_id)
- **Simulates** external calls: generates `EXT-<ACTION_TYPE>-<id>` reference, returns `{"simulated": true, ...}`
- Emits `execution.completed` / `execution.failed` events to the event stream
- Never mutates business data (items, inventory, POs)

### 2.2 Call Chain
```
POST /api/v1/intelligence/execute
    → intelligence_api.execute_plan()
    → execution_engine.execute_from_request()
    → create_execution_job() + execute_job()
    → event stream (execution.completed)
```

### 2.3 Use Case
Plan execution from the Intelligence API. The planner (`nazm_planner`) builds a plan; the intelligence API executes it via `execution_engine`. This is **simulation-only** — used for tracking what *would* happen, not actually executing.

---

## 3. Path B: `agent_action_executor` (REAL)

### 3.1 Behavior
- Validates constraints via `execution_guard.validate_action_for_execution()` (fail-closed)
- Actually mutates database:
  - `pricing_update` → `UPDATE items SET sell_price = ...`
  - `restock_po` → `INSERT INTO purchase_orders ...`
  - `transfer_inventory` → `UPDATE inventory SET current_stock = current_stock ± qty`
- Returns `{"executed": true, ...}` with real outcome data

### 3.2 Call Chain
```
POST /api/v1/agent-actions/{id}/approve (WhatsApp or web)
    → agent_action_executor.approve_agent_action()
    → execute_agent_action()
    → _execute_pricing_update / _execute_restock_po / _execute_transfer
    → DB mutations + agent_actions.applied_at + outcome_json
```
Also used by auto-approval in `autonomy_service.py` and agent runtime in `runtime.py`.

### 3.3 Use Case
**Actual execution** after human or automated approval. The `agent_actions` table tracks approval state; execution happens only on approval.

---

## 4. Action Type Coverage

| Action Type | execution_engine | agent_action_executor |
|-------------|------------------|----------------------|
| discount / pricing_increase / pricing_decrease | Simulated | Real (`_execute_pricing_update`) |
| reorder / restock | Simulated | Real (`_execute_restock_po`) |
| transfer / recovery_match | Simulated | Real (`_execute_transfer`) |
| expiry_alert | Simulated | Manual (returns executed=false) |
| Other | Simulated | Manual (returns executed=false) |

---

## 5. Architectural Intent

This is **not a bug** — it's a deliberate separation of concerns:

1. **Planning/Simulation Layer** (`execution_engine`): 
   - Safe to run repeatedly, idempotent
   - Feeds event stream for audit/reporting
   - No external side effects
   - Used by AI/planner to "try out" plans

2. **Execution Layer** (`agent_action_executor`):
   - Real side effects, constraint-guarded
   - Triggered only after approval (human or policy)
   - Audit trail via `agent_actions.applied_at` + `outcome_json`

The two paths could be unified in future (e.g., `execution_engine` delegates to `agent_action_executor` for real execution), but current separation is clean and serves distinct purposes.

---

## 6. Verification

- `test_execution_engine.py` (if exists): should test simulation + event emission
- `test_agent_action_executor.py` (if exists): should test real DB mutations + constraint guard
- No tests currently exercise both paths for the same action (gap)

---

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Drift between simulated and real behavior | Add integration test that compares outcomes |
| Double-execution if both paths used for same action | Idempotency keys + approval state prevent this |
| Missing action type in one path | Action registry (`can_execute`) is shared source of truth |