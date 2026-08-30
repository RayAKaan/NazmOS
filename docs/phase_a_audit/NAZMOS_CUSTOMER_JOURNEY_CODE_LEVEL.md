# NAZMOS Customer Journey — Code Level

For every major customer action, the actual call chain with filenames, classes, functions, and endpoints.

---

## UPLOAD CSV (Server ETL Path)

```
FRONTEND: UploadPage.handleFile() [frontend/src/app/(dashboard)/upload/page.tsx:367]
    ↓
API: POST /api/v1/upload/ [backend/app/routers/upload.py:63]
    ↓
MIDDLEWARE: assert_business_access() [middleware/business_access.py]
    ↓
MIDDLEWARE: enforce_upload_limit() [middleware/feature_gate.py]
    ↓
SERVICE: FileValidator.validate() [backend/app/services/file_validator.py]
    ↓
SERVICE: UploadService.parse_file_with_report() [backend/app/services/upload_service.py:16]
    ↓
SERVICE: SchemaDetector().detect() [backend/app/services/schema_detector.py:158]
    ↓
DB: INSERT uploaded_files (status='mapping_required') [upload.py:119]
    ↓
RETURN: upload_id, detected_columns, confidence_scores, sample_rows
```

### Mapping Confirmation
```
FRONTEND: handleMappingConfirm() [upload/page.tsx:121]
    ↓
API: POST /api/v1/upload/{upload_id}/map [backend/app/routers/upload.py:183]
    ↓
DB: UPDATE uploaded_files SET column_mapping, status='processing' [upload.py:225]
    ↓
IF USE_CELERY:
    Celery: process_upload_task.apply_async() [ingestion_tasks.py:160]
    → TASK: run_process_upload() [ingestion_tasks.py:16]
    → ETLPipeline.run() [etl_pipeline.py:76]
ELSE:
    Inline: ETLPipeline.run() [upload.py:258]
```

---

## ETL PIPELINE (Core Ingestion)

```
ETLPipeline.run() [etl_pipeline.py:76]
    ↓
_push_progress(0%) → Redis pubsub + DB status update
    ↓
_upsert_items() [etl_pipeline.py:240]
    → For each unique item_name:
        → _get_or_create_category() [etl_pipeline.py:223]
        → audit_inventory_halal_status() [shariah_compliance.py]
        → INSERT/UPDATE items (cost_price, sell_price, barcode, brand, pack_size, storage_type, shariah_*)
    ↓
_ensure_inventory() [etl_pipeline.py:343]
    → INSERT inventory WHERE NOT EXISTS (business_id, item_id)
    ↓
IF has_inventory_snapshot (current_stock column):
    _apply_inventory_snapshot() [etl_pipeline.py:357]
    → UPSERT inventory (current_stock, reorder_level, max_stock, last_restocked)
    ↓
IF has_sales_history (transaction_at column):
    _bulk_insert_transactions() [etl_pipeline.py:410]
    → For each row:
        → row_hash = SHA256(business_id, item_id, transaction_at, quantity, total_amount)
        → INSERT transactions ON CONFLICT (business_id, row_hash) DO NOTHING
        → Chunked commit every 1000 rows
    → Returns {imported, skipped, failed, date_range}
    ↓
_rebuild_summaries() [etl_pipeline.py:511]
    → Daily aggregates from transactions → daily_summaries UPSERT
    ↓
_invalidate_forecasts() [etl_pipeline.py:580]
    → DELETE FROM forecast_cache WHERE business_id AND item_id IN (...)
    ↓
_push_progress(100%)
    ↓
UPDATE uploaded_files (row_count_imported, row_count_failed, status='completed')
```

---

## MONEY AUDIT GENERATION

```
API: GET /money-audit/current?auto_generate=true [backend/app/routers/money_audit.py]
    ↓
SERVICE: generate_money_audit() [backend/app/services/money_audit_service.py:580]
    ↓
SERVICE: compute_money_audit() [money_audit_service.py:163]
    ↓
DB: _period() → MIN/MAX transaction_at
    ↓
DB: _quality() → Coverage metrics (cost, price, stock, barcode, sales period)
    ↓
DB: Complex CTE query [money_audit_service.py:188]
    → sales_30 (last 30 days qty, revenue, profit, last_sold_at)
    → sales_prior (prior 30 days qty)
    → sales_90 (90-day transaction count, last_activity)
    → monthly_sales (monthly buckets for concentration)
    → JOIN items, inventory, categories, suppliers
    ↓
FOR EACH ROW:
    → classify_inventory() [recovery_intelligence.py:88]
    → estimate_recovery() [recovery_intelligence.py:151]
    → stockout_financials() [recovery_intelligence.py:249] (if daily_velocity > 0)
    → margin leakage check (vs TARGET_MARGIN_PCT=22%)
    ↓
AGGREGATE: capital_at_risk, revenue_at_risk, gross_profit_at_risk, recoverable_low/high
    ↓
CALIBRATION: Query completed money_audit_actions for median actual/expected ratios
    ↓
BUILD actions list (max 12, sorted by priority + recoverable_high)
    ↓
DB: INSERT money_audit [money_audit_service.py:593]
    ↓
DB: INSERT money_audit_actions [money_audit_service.py:638]
    ↓
RETURN: Full audit object with actions
```

---

## DETERMINISTIC DECISION (Nazm Planner)

```
CELERY BEAT: daily 06:00 → audit_tasks.daily_full_audit
    OR MANUAL: POST /api/v1/agent/scan [backend/app/routers/agent.py:244]
    ↓
SERVICE: NazmPlanner.scan_business() [backend/app/services/nazm_planner.py:25]
    ↓
_agent_restock() [nazm_planner.py:183]
    → Query items + inventory + forecast_cache
    → get_confirmed_inbound_map() [po_service.py]
    → usable_confirmed_inbound() [po_service.py] (time-aware!)
    → projected_stockout_date() [po_service.py]
    → IF effective_stock_days < 3 AND stock < reorder_level*1.5:
        → _create_action(action_type='restock', confidence=0.85-0.92)
_agent_pricing() [nazm_planner.py:263]
    → Margin check (floor 20%, target 35%)
    → Recipe BOM costing (cafe/food)
    → IF margin_pct < floor:
        → _create_action(action_type='pricing_increase', confidence=0.65-0.88)
_agent_cash() [nazm_planner.py:448]
    → Daily profit vs restock liability
    → IF liability > 1.5× 14-day profit:
        → _create_action(action_type='cash_alert', confidence=0.82)
_agent_expiry() [nazm_planner.py:511] (Pharmacy only)
    → Query pharmacy_lots expiring < 90 days
    → _create_action(action_type='expiry_alert', confidence=0.95)
```

### _create_action() Autonomy Logic [nazm_planner.py:51]
```
dial = _get_autonomy(business_id, action_type)  # 0-100 from autonomy_policies
IF confidence < 0.75: dial = min(dial, 50)
IF dial == 0: status = 'info_only'
ELIF dial >= 95 AND confidence >= 0.9: status = 'auto_executed'
ELSE: status = 'pending_approval'
→ INSERT agent_actions (payload, estimated_value_sar, autonomy_dial_at_creation, expires_at)
→ IF status='pending_approval': send_approval_request() [whatsapp_bridge.py]
```

---

## PHASE 4 DECISION ENGINE (Intelligence API)

```
API: POST /api/v1/intelligence/decisions/generate [backend/app/routers/intelligence.py:473]
    ↓
SERVICE: generate_decision() [backend/app/services/decision_engine.py:492]
    ↓
_load_memory() → SELECT * FROM business_memory WHERE business_id
_load_recent_events() → SELECT * FROM events WHERE business_id AND occurred_at > NOW()-24h
_load_graph_signals() → SELECT * FROM graph_relationships ORDER BY strength DESC LIMIT 50
_load_context_signals() → get_active_context() [context_engine.py]
    ↓
GENERATE CANDIDATES:
    _generate_restock_candidates() → from memory.current_state.inventory
    _generate_pricing_candidates() → from memory.patterns.pricing
    _generate_discount_candidates() → from pricing history decreases
    _generate_supplier_switch_candidates() → from graph SUPPLIES strength < 0.4
    ↓
_score_candidate() [decision_engine.py:428]
    → composite = 0.35×norm_ROI + 0.25×confidence + 0.25×urgency - 0.15×risk
    → Context adjustments: holidays, inflation
    ↓
SORT by score DESC
    ↓
_build_explanation() → summary, primary_drivers, evidence, alternatives
    ↓
INSERT IntelligenceDecision [decision_engine.py:548]
    → decision_type, rules_applied, memory_snapshot, graph_evidence, context_evidence
    → candidate_actions, ranked_action, confidence, expected_roi, risk_score, urgency
    ↓
RETURN IntelligenceDecision
```

---

## AI REASONING (OpenCode Brain)

```
API: POST /api/v1/intelligence/reason [intelligence.py:872] → intelligence_api.reason()
    OR POST /api/v1/agent/reason [agent.py:274] → IntelligenceAPIClient.reason()
    ↓
SERVICE: ai_gateway.reason() [backend/app/services/ai_gateway.py:8]
    ↓
BUDGET: GLOBAL_AI_BUDGET.can_call() [ai_budget.py]
    ↓
SERVICE: opencode_brain.reason() [backend/app/services/opencode_brain.py:402]
    ↓
build_reasoning_prompt(evidence) [opencode_brain.py:49]
    → Structured JSON: business context + items (sku, classification, stock, velocity, days_supply, trend, seasonal, supplier_reliability, margin, candidate_actions, recoverable range, historical_outcomes)
    ↓
SYSTEM_PROMPT + evidence → full_prompt
    ↓
_invoke_opencode() [opencode_brain.py:224]
    → _find_opencode_bin() → PATH lookup or %APPDATA%\npm\opencode.cmd
    → asyncio.create_subprocess_exec(opencode_bin, "run", "--format", "json", "--model", model, prompt)
    → timeout=30s, env={PATH, HOME, NODE_ENV, OPENAI_API_KEY (if model=openai/)}
    ↓
_parse_opencode_json_output() [opencode_brain.py:296]
    → Scans stdout lines for assistant message with JSON content
    ↓
validate_ai_response() [ai_response_validator.py:89]
    → JSON syntax, required fields, ALLOWED_DECISIONS enum, confidence [0,1]
    → reasoning non-empty, evidence_ids ⊆ known_evidence_ids
    → risk_flags ⊆ ALLOWED_RISK_FLAGS
    → Financial hallucination regex scan
    → Prompt injection regex scan
    → Decision vs deterministic compatibility
    → Owner constraint compatibility (max_discount_pct)
    ↓
validate_decision_in_registry() [ai_response_validator.py:252]
    → decision ∈ REGISTERED_ACTIONS (restock, discount, transfer, raise_price, lower_price, bundle, return_to_supplier, write_off, manual_intervention)
    ↓
ON SUCCESS: BrainDecision(source='opencode', latency_ms, validation=ValidationResult)
ON FAILURE: _deterministic_fallback() [opencode_brain.py:353]
    → Uses deterministic_decision or first candidate_action
    → confidence=0.5, source='fallback', risk_flags=['INSUFFICIENT_EVIDENCE']
```

---

## APPROVAL FLOW (Money Audit Action)

```
FRONTEND: MoneyAuditPage.updateAction() [money-audit/page.tsx:140]
    ↓
API: POST /money-audit/actions/{action_id}/approve [money_audit_router.py]
    ↓
SERVICE: update_action_status() [money_audit_service.py:831]
    ↓
VALIDATE TRANSITION: suggested → approved (VALID_TRANSITIONS dict)
    ↓
DB: UPDATE money_audit_actions SET status='approved', approved_at=NOW(), approval_channel='dashboard'
    ↓
_recalculate_audit_totals() [money_audit_service.py:801]
    → money_approved_sar = SUM(expected_recovery_sar) WHERE status IN ('approved','completed')
    → money_recovered_sar = SUM(completed_value_sar) WHERE status='completed'
    → UPDATE money_audits SET money_approved_sar, money_recovered_sar, summary JSONB
```

### WhatsApp Approval
```
WEBHOOK: GET /api/v1/whatsapp/webhook?action=approve&id=... [whatsapp_router.py]
    ↓
verify_pos_webhook_auth() → HMAC validation
    ↓
approve_agent_action() [agent_action_executor.py]
    → Validates ownership, autonomy dial, confidence ≥ AGENT_AUTO_MIN_CONFIDENCE (0.90)
    → Updates agent_actions: status='approved', decided_at, decided_by
    → IF auto_executed: calls action executor
```

---

## ACTION EXECUTION

```
API: POST /api/v1/intelligence/execute [intelligence.py:613] → execution_engine.execute_from_request()
    ↓
SERVICE: execute_from_request() [execution_engine.py]
    ↓
Creates ExecutionJob record
    ↓
Routes by action_type:
    - restock: Creates PurchaseOrder (draft) → WhatsApp to supplier
    - pricing_increase/decrease: UPDATE items.sell_price
    - discount: Business logic only (no external call)
    - transfer: UPDATE inventory.current_stock (multi-branch)
    - expiry_alert: Notification only
    - cash_alert: Notification only
    ↓
Updates ExecutionJob: status, result, external_reference, executed_at
    ↓
IF completed: Creates OutcomeFeedback + ImpactLedger entries
```

---

## OUTCOME GENERATION & LEARNING

### Money Audit Action Complete
```
FRONTEND: updateAction(actionId, 'complete') [money-audit/page.tsx:140]
    ↓
API: POST /money-audit/actions/{action_id}/complete [money_audit_router.py]
    ↓
SERVICE: update_action_status(status='complete', completed_value_sar=X) [money_audit_service.py:831]
    ↓
VALIDATE: approved → completed only
    ↓
DB: UPDATE money_audit_actions SET completed_value_sar=X, completed_at=NOW(),
       prediction_error_pct = ((X - expected) / expected) * 100,
       measurement_window_days = 30
    ↓
_recalculate_audit_totals() → money_recovered_sar += X
    ↓
Learning: record_feedback() [learning_engine.py] → INSERT outcome_feedback
    → decision_id, actual_outcome, feedback_source='manual'
    → LearningEngine refresh picks this up
```

### Agent Action Execution
```
approve_agent_action() [agent_action_executor.py]
    → Executes payload action (restock, pricing, etc.)
    → Creates agent_actions.outcome_json
    → Creates outcome_feedback (agent_action_id lineage)
    → Creates impact_ledger entry
    → Creates learned_outcome (kind='fact')
```

### Learning Engine Refresh (Daily 05:00)
```
CELERY BEAT: learning_tasks.refresh_model_performance [backend/app/tasks/learning_tasks.py]
    ↓
SERVICE: refresh_learning() [learning_engine.py]
    ↓
FOR EACH business, decision_type:
    → Queries outcome_feedback in window
    → Computes accuracy = correct_predictions / total
    → Computes roi_error = AVG(|predicted - actual|)
    → INSERT/UPDATE model_performance
    ↓
suggest_best_action() [learning_engine.py] uses Thompson sampling on model_performance
```

---

## POS WEBHOOK (Foodics/Salla)

```
WEBHOOK: POST /api/v1/pos/foodics/webhook?business_id=... [pos_webhooks.py:156]
    ↓
verify_pos_webhook_auth() → HMAC-SHA256 with FOODICS_WEBHOOK_SECRET
    ↓
record_webhook_event() → INSERT webhook_events (status='received', signature_valid=true)
    ↓
IDEMPOTENCY: IF event.status='processed' → return 200
    ↓
_process_webhook() → handle_foodics_order_created() [adapters/foodics.py:25]
    ↓
IDEMPOTENCY: SELECT transactions WHERE reference_id = order_ref
    ↓
FOR EACH product:
    → resolve_item() [item_resolver.py] (sku → barcode → name fuzzy)
    → UPDATE inventory SET current_stock = GREATEST(0, current_stock - qty)
    → INSERT transactions (quantity, unit_price, cost_price, total_amount, profit, reference_id)
    ↓
_emit_pos_event() → EventIngest(event_type='pos.order.received', source='foodics', ...)
    → event_engine.ingest_event() → INSERT events
    ↓
mark_webhook_processed(status='processed')
```

---

## DAILY CRON JOBS (Celery Beat Schedule)

| Time (Asia/Riyadh) | Task | Purpose |
|---|---|---|
| 01:00 | rebuild_summaries_yesterday | Rebuild daily_summaries from transactions |
| 02:00 | cleanup_stale_uploads | Delete uploads stuck >48h in mapping_required |
| 03:00 | refresh_all_forecasts | Prophet forecasts for all items |
| 04:00 | process_pending_deletions | GDPR deletion requests |
| 05:00 | refresh_model_performance | Learning engine aggregates |
| 06:00 | daily_full_audit | Money Audit generation |
| 07:00 | goal_progress_snapshot | GoalProgressHistory measurements |
| Every 60s | process_unprocessed_events | Event engine → memory projectors |
| Every 3600s | learning_reconciliation | Repair bridge drift |

---

## TENANT ISOLATION CHECKPOINTS

Every DB query path includes `business_id` filter:

1. **Middleware**: `TenantContextMiddleware` → sets `_rls_tenant_id` context var [middleware/rls_tenant.py]
2. **Database**: `get_session()` → `SET LOCAL app.current_tenant_id = '<business_id>'` [connection.py:113]
3. **RLS Policy**: PostgreSQL policies on all tenant tables (migration `a25a714a2de8_add_tenant_rls_policies.py`)
4. **Enforcement**: `enforce_tenant_filter(business_id)` [connection.py:28] — blocks cross-tenant in SQLite dev too
5. **Services**: All service methods accept `business_id` parameter, pass to queries
6. **Celery Tasks**: `get_sync_session()` → same RLS context via `_set_rls_context` in async scope

---

## KEY ENTRY POINTS SUMMARY

| Customer Action | HTTP Endpoint | Router | Primary Service |
|---|---|---|---|
| Register | POST /api/v1/auth/register | auth_router | auth_service |
| Login | POST /api/v1/auth/login | auth_router | auth_service |
| Upload file | POST /api/v1/upload/ | upload_router | upload_service, FileValidator, SchemaDetector |
| Confirm mapping | POST /api/v1/upload/{id}/map | upload_router | ETLPipeline |
| View dashboard | GET /api/v1/dashboard | dashboard_router | dashboard_service |
| View money audit | GET /money-audit/current | money_audit_router | money_audit_service |
| Generate audit | POST /money-audit/generate | money_audit_router | money_audit_service |
| Approve action | POST /money-audit/actions/{id}/approve | money_audit_router | money_audit_service |
| Complete action | POST /money-audit/actions/{id}/complete | money_audit_router | money_audit_service |
| Agent feed | GET /api/v1/agent/feed | agent_router | NazmPlanner (scan) |
| Agent approve | POST /api/v1/agent/actions/{id}/approve | agent_router | approve_agent_action |
| Intelligence analyze | POST /api/v1/intelligence/analyze | intelligence_router | intelligence_api.analyze |
| Intelligence reason | POST /api/v1/intelligence/reason | intelligence_router | ai_gateway → opencode_brain |
| POS webhook | POST /api/v1/pos/foodics/webhook | pos_webhooks_router | handle_foodics_order_created |
| WhatsApp webhook | POST /api/v1/whatsapp/webhook | whatsapp_router | WhatsApp webhook handler |