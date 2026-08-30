# NAZMOS Complete Data Flow

Trace data from entry to outcome. Only paths that actually exist in code are documented.

---

## 1. CSV Upload → Raw Data Ingestion

```
Customer CSV/XLSX File
         ↓
Frontend: PapaParse (CLIENT_ETL=true) OR multipart/form-data (CLIENT_ETL=false)
         ↓
POST /api/v1/upload/  [upload.py:63]
         ↓
FileValidator.validate()
  - Extension allowlist: .csv, .xlsx, .xls
  - Size limit: 15 MB
  - MIME type check
  - SHA256 hash computed
  - Encoding detection (UTF-8, fallback)
         ↓
UploadService.parse_file_with_report() [upload_service.py:16]
  - CSV: pandas.read_csv(on_bad_lines='error') + malformed row detection
  - Excel: pandas.read_excel(engine='openpyxl'/'xlrd')
  - Row limit: 100,000 (MAX_ROWS)
         ↓
SchemaDetector().detect() [schema_detector.py:158]
  - POS signature detection (Foodics/Salla markers)
  - Column scoring: name_hints (70%) + sample_validator (30%)
  - Levenshtein similarity for fuzzy matches
  - Context-aware: no sale date → "quantity" becomes "current_stock"
         ↓
INSERT uploaded_files (status='mapping_required')
  - detected_columns: {source_col: target_field}
  - confidence_scores: {source_col: 0.0-1.0}
  - sample_rows: first 5 rows
  - data_quality_report: {rows_received, rows_rejected, malformed_rows}
```

**Column Mapping Output** (detected_columns):
```json
{
  "Product Name": "item_name",
  "Qty": "quantity",
  "Sale Date": "transaction_at",
  "Unit Price": "unit_price",
  "Cost Price": "cost_price",
  "Current Stock": "current_stock",
  "SKU": "item_sku",
  "Barcode": "barcode",
  "Category": "category_name"
}
```

---

## 2. Mapping Confirmation → ETL Pipeline

```
POST /api/v1/upload/{upload_id}/map  [upload.py:183]
  Body: {business_id, column_mapping: {"Product Name": "item_name", ...}}
         ↓
UPDATE uploaded_files SET column_mapping, status='processing'
         ↓
ETLPipeline.run() [etl_pipeline.py:76]
         ↓
normalize_dataframe(df, column_mapping, strict=True) [data_normalizer.py]
  - Renames columns per mapping
  - Parses dates (multiple formats)
  - Parses currency (strips SAR symbols)
  - Parses quantities (numeric)
  - Validates required fields present
  - Returns normalized DataFrame + data_quality_report (rejected rows)
```

---

## 3. ETL: Item & Category Upsert

```
_upsert_items() [etl_pipeline.py:240]
  For each unique item_name (case-insensitive):
         ↓
_get_or_create_category(category_name) [etl_pipeline.py:223]
  INSERT INTO categories (business_id, name)
  ON CONFLICT (business_id, name) DO UPDATE
         ↓
audit_inventory_halal_status() [shariah_compliance.py]
  - Checks item name, category, SKU against haram patterns
  - Returns {flagged_violations: [], status: 'halal_guard_passed'|'flagged_haram'}
         ↓
INSERT/UPDATE items
  - business_id, name, sku, category_id
  - cost_price, sell_price (only updated if > 0)
  - barcode, brand, pack_size, storage_type
  - shariah_status, shariah_flags, shariah_checked_at
  - ON CONFLICT (business_id, LOWER(name)) DO UPDATE
         ↓
Returns item_map: {lowercase_name: item_id}
```

---

## 4. ETL: Inventory Initialization

```
_ensure_inventory() [etl_pipeline.py:343]
  For each item in item_map:
    INSERT INTO inventory (business_id, item_id, current_stock=0, reorder_level=10, max_stock=100)
    WHERE NOT EXISTS (business_id, item_id)
```

---

## 5. ETL: Inventory Snapshot Application (if current_stock column present)

```
_apply_inventory_snapshot() [etl_pipeline.py:357]
  For each row with current_stock:
    item_id = item_map[item_name.lower()]
    current_stock = max(0, parsed_value)
    reorder_level = parsed_or_null
    max_stock = parsed_or_null OR max(current_stock, 100)
         ↓
UPSERT inventory
  ON CONFLICT (business_id, item_id) DO UPDATE
    current_stock = EXCLUDED.current_stock
    reorder_level = COALESCE(EXCLUDED.reorder_level, inventory.reorder_level)
    max_stock = COALESCE(EXCLUDED.max_stock, inventory.max_stock)
    last_restocked = CASE WHEN EXCLUDED.current_stock > inventory.current_stock THEN NOW()
    updated_at = NOW()
```

---

## 6. ETL: Sales Transaction Import (if transaction_at column present)

```
_bulk_insert_transactions() [etl_pipeline.py:410]
  For each row:
    item_id = item_map[item_name.lower()]
    transaction_at = parsed datetime
    quantity = abs(parsed)
    unit_price = parsed
    cost_price = parsed OR 0
    total_amount = parsed OR quantity × unit_price
    transaction_type = normalized (sale/return/refund/waste/adjustment/transfer)
    profit = total_amount - (quantity × cost_price)
         ↓
ROW HASH (deduplication key):
  SHA256(JSON: {business_id, item_id, transaction_at, quantity, total_amount})
         ↓
INSERT INTO transactions
  (business_id, item_id, quantity, unit_price, cost_price, total_amount, profit,
   transaction_at, transaction_type, row_hash)
  ON CONFLICT (business_id, row_hash) WHERE row_hash IS NOT NULL DO NOTHING
         ↓
Chunked commit every 1000 rows
         ↓
Returns: {imported, skipped (dupes), failed, date_range}
```

**Dedup Logic**: Partial unique index on `(business_id, row_hash) WHERE row_hash IS NOT NULL` (models.py:350)

---

## 7. ETL: Daily Summaries Rebuild

```
_rebuild_summaries() [etl_pipeline.py:511]
  WITH daily_totals AS (
    SELECT business_id, DATE(transaction_at) AS d,
           SUM(total_amount) AS total_sales,
           SUM(profit) AS total_profit,
           COUNT(*) AS total_transactions
    FROM transactions
    WHERE business_id = :bid AND DATE(transaction_at) BETWEEN :start AND :end
    GROUP BY business_id, DATE(transaction_at)
  ),
  item_totals AS (
    SELECT business_id, DATE(transaction_at) AS d, item_id, SUM(quantity) AS qty,
           ROW_NUMBER() OVER (PARTITION BY DATE(transaction_at) ORDER BY SUM(quantity) DESC) AS rn
    FROM transactions
    WHERE ...
    GROUP BY business_id, DATE(transaction_at), item_id
  )
  INSERT INTO daily_summaries (business_id, date, total_sales, total_profit, total_transactions, top_item_id, top_item_qty)
  SELECT dt.business_id, dt.d, dt.total_sales, dt.total_profit, dt.total_transactions, it.item_id, it.qty
  FROM daily_totals dt LEFT JOIN item_totals it ON dt.d = it.d AND it.rn = 1
  ON CONFLICT (business_id, date) DO UPDATE SET ...
```

---

## 8. ETL: Forecast Invalidation

```
_invalidate_forecasts() [etl_pipeline.py:580]
  DELETE FROM forecast_cache WHERE business_id = :bid AND item_id = ANY(:item_ids)
```

---

## 9. Events → Business Memory (Continuous)

```
Event ingested (webhook, API, manual, ETL)
         ↓
EventIngest schema [schemas/events.py]
         ↓
event_engine.ingest_event() [event_engine.py]
  → INSERT events (business_id, event_type, payload, checksum, occurred_at)
  → checksum = SHA256(business_id + event_type + source + source_id + payload)
  → Dedup: partial unique index on (business_id, source, source_id, checksum)
         ↓
route_event_to_projectors() [business_memory.py:347]
  _PROJECTOR_MAP = {
    'inventory.changed': _project_inventory_changed,
    'sale.completed': _project_sale_completed,
    'supplier.delivered': _project_supplier_delivered,
    'price.updated': _project_price_updated,
  }
         ↓
Projector updates BusinessMemory (JSONB documents)
  - CURRENT_STATE: inventory.{item}.stock, sales.daily.{date}.total, reorder_flag
  - PATTERNS: top_products.{item}.quantity_30d, pricing.{item}.history[]
  - RELATIONSHIPS: suppliers.{id}.delivery_count_90d, last_delivery_at
  - GOALS: merchant-set targets
  - FORECASTS, SEASONALITY, FAILURES: (stubs)
         ↓
MemoryUpdate audit record for every path mutation
  (path, old_value, new_value, event_id, occurred_at)
```

---

## 10. Scheduled Intelligence Runs

### 10.1 Forecast Generation (Daily 03:00)
```
forecast_tasks.refresh_all_forecasts [forecast_tasks.py]
  → Prophet per item with ≥14 days sales history
  → forecast_7d, forecast_30d, weekly_pattern, trend_direction, trend_strength
  → UPSERT forecast_cache (expires_at = trained_at + 24h)
```

### 10.2 Nazm Planner / Agent Scan (Every 15 min or Manual)
```
nazm_planner.NazmPlanner.scan_business() [nazm_planner.py:25]
  → _agent_restock: stock_days < 3, time-aware inbound
  → _agent_pricing: margin < floor, recipe BOM costing
  → _agent_cash: restock_liability > 1.5× 14-day profit
  → _agent_expiry: pharmacy_lots expiring < 90 days
         ↓
_create_action() → INSERT agent_actions
  - autonomy_dial from autonomy_policies (default 50 for restock)
  - confidence gates auto-execution (dial≥95 + conf≥0.90)
  - WhatsApp approval sent if status='pending_approval'
```

### 10.3 Money Audit (Daily 06:00)
```
audit_tasks.daily_full_audit [audit_tasks.py]
  → money_audit_service.compute_money_audit() [money_audit_service.py:163]
  → Complex CTE query with sales_30, sales_prior, sales_90, monthly_concentration
  → classify_inventory() per item [recovery_intelligence.py:88]
  → estimate_recovery() [recovery_intelligence.py:151]
  → stockout_financials() [recovery_intelligence.py:249]
  → margin leakage check
  → Calibration from completed money_audit_actions
  → INSERT money_audit + money_audit_actions
```

### 10.4 Learning Engine Refresh (Daily 05:00)
```
learning_tasks.refresh_model_performance [learning_tasks.py]
  → learning_engine.refresh_learning() [learning_engine.py]
  → For each business/decision_type/window:
      accuracy = correct / total from outcome_feedback
      roi_error = AVG(|predicted - actual|)
      → INSERT/UPDATE model_performance
```

---

## 11. Decision Generation Paths

### Path A: Deterministic (Phase 4 Decision Engine)
```
POST /api/v1/intelligence/decisions/generate
  → decision_engine.generate_decision() [decision_engine.py:492]
    → Loads memory, events, graph, context
    → Generates candidates (restock, pricing, discount, supplier_switch)
    → _score_candidate(): 0.35×ROI + 0.25×conf + 0.25×urgency - 0.15×risk
    → Context: holidays↑urgency, inflation↑risk
    → Stores IntelligenceDecision with full explanation
```

### Path B: Nazm Agent (Deterministic Rules)
```
POST /api/v1/agent/scan
  → NazmPlanner.scan_business() → agent_actions table
  → Feed: GET /api/v1/agent/feed → ordered by status, confidence, created_at
```

### Path C: AI Reasoning (OpenCode Brain)
```
POST /api/v1/intelligence/reason
  → intelligence_api.reason() → ai_gateway.reason()
    → GLOBAL_AI_BUDGET.can_call()
    → opencode_brain.reason(evidence, deterministic_decision)
      → Builds evidence prompt (items + business context)
      → Invokes OpenCode CLI subprocess (30s timeout)
      → Parses JSON from stdout
      → validate_ai_response() → strict schema + safety checks
      → Returns BrainDecision or deterministic fallback
```

---

## 12. Approval → Execution → Outcome

```
Owner Action: Approve/Reject/Complete
         ↓
Money Audit: POST /money-audit/actions/{id}/approve|reject|complete
  → update_action_status() [money_audit_service.py:831]
  → Validates lifecycle: suggested→approved→completed
  → Recalculates money_approved_sar, money_recovered_sar
         ↓
Agent Action: POST /api/v1/agent/actions/{id}/approve
  → approve_agent_action() [agent_action_executor.py]
  → Checks autonomy dial, confidence ≥ 0.90, risk escalation
  → Executes payload action (restock, pricing, etc.)
         ↓
Execution Engine: POST /api/v1/intelligence/execute
  → execution_engine.execute_from_request()
  → Creates ExecutionJob
  → Internal: UPDATE items/inventory
  → External: WhatsApp, POS adapters
```

---

## 13. Outcome Recording

### Money Audit Outcome
```
Completed action with completed_value_sar:
  → money_audit_actions.completed_value_sar, completed_at
  → prediction_error_pct = ((actual - expected) / expected) × 100
  → outcome_feedback INSERT (decision_id, predicted, actual, delta)
  → impact_ledger INSERT (impact_type, amount_sar, verification='observed')
```

### Agent Action Outcome
```
agent_actions.outcome_json = {executed: true, result: {...}}
  → outcome_feedback (agent_action_id lineage, unique constraint)
  → impact_ledger (money_recovered, revenue_protected, cost_reduced, etc.)
  → learned_outcome (kind='fact', confidence=1.0, evidence_count++)
```

---

## 14. Learning → Future Decisions

```
ModelPerformance (per business/decision_type/window)
  → suggest_best_action() uses Thompson sampling on historical performance
         ↓
Calibration Rates (from completed money_audit_actions)
  → estimate_recovery() uses median(calibration_rates) for expected_recovery
         ↓
Business Memory (CURRENT_STATE, PATTERNS, RELATIONSHIPS)
  → Decision engine loads memory_snapshot for context
         ↓
Knowledge Graph (GraphRelationship strength)
  → Supplier reliability, product affinity learned from events
```

---

## 15. POS Webhook → Real-time Sync

```
Foodics/Salla webhook → /api/v1/pos/{provider}/webhook
  → HMAC verification
  → WebhookEvent audit record
  → Idempotency: check existing transaction by reference_id
  → handle_{provider}_order_created() [adapters/foodics.py, salla.py]
    → resolve_item(sku/barcode/name) [item_resolver.py]
    → UPDATE inventory current_stock -= qty
    → INSERT transactions (with fallback_cost = 70% sell_price)
  → EventIngest('pos.order.received') → Universal Event Engine
```

---

## Complete Transformation Chain

```
CSV Columns
    ↓ (SchemaDetector)
Normalized Fields (item_name, quantity, transaction_at, unit_price, cost_price, current_stock, item_sku, barcode, category_name)
    ↓ (ETLPipeline)
Items + Categories (cost_price, sell_price, shariah_status)
    ↓
Inventory (current_stock, reorder_level, max_stock, supplier_id, lead_time_days)
    ↓
Transactions (quantity, unit_price, cost_price, total_amount, profit, row_hash)
    ↓
DailySummaries (date, total_sales, total_profit, top_item)
    ↓
Events (sale.completed, inventory.changed, price.updated)
    ↓ (Projectors)
BusinessMemory:
  CURRENT_STATE: {inventory: {item: {stock, reorder_flag}}, sales: {daily: {date: {total}}}}
  PATTERNS: {top_products: {item: {quantity_30d}}, pricing: {item: {history: [{price, updated_at}]}}}
  RELATIONSHIPS: {suppliers: {id: {delivery_count_90d, last_delivery_at}}}
    ↓
ForecastCache (prophet_7d, prophet_30d, weekly_pattern, trend)
    ↓
MoneyAudit (classifications, financial_measures, actions)
    ↓
AgentActions (restock, pricing, cash, expiry) + WhatsApp approvals
    ↓
IntelligenceDecisions (ranked, explained, stored)
    ↓
ExecutionJobs (internal/external state changes)
    ↓
OutcomeFeedback + ImpactLedger (measured actuals)
    ↓
ModelPerformance + CalibrationRates
    ↓
Future Decisions (weighted by performance)
```

---

## Data Type Handling (Financial Values)

| Layer | Type | Safety |
|---|---|---|
| CSV Input | String | Parsed by `decimal_value()` / `sar()` (utils/money.py) |
| Pandas | float64 | Converted to Decimal immediately |
| Python Services | `Decimal` | All financial math uses Decimal with `ROUND_HALF_UP` |
| SQLAlchemy | `Numeric(12,2)` or `Numeric(14,2)` | Fixed precision, no float |
| PostgreSQL | `NUMERIC(12,2)` / `NUMERIC(14,2)` | Exact storage |
| JSON/API | `float` (serialized) | Frontend formats with `toLocaleString()` |
| Redis/Celery | JSON string | Decimal → float → string |

**Critical**: No `float` used for financial calculations in services. `money()` utility ensures `Decimal('0.01')` quantization everywhere.

---

## Column Detection → Normalization → DB Mapping Table

| Customer Column (Aliases) | Detection Method | Internal Field | Python Type | DB Table.Column | Downstream Consumers |
|---|---|---|---|---|---|
| Product Name / Item / Name / Description / اسم الصنف / منتج | name_hints + is_text | item_name | str | items.name | All |
| Qty / Quantity / Sold Qty / Units / Pieces / كمية / الكمية | qty hints + is_positive_numeric | quantity | Decimal | transactions.quantity | Velocity, forecasts |
| Sale Date / Date / Transaction Date / Billing Date / التاريخ / وقت | date_hints + is_date_like | transaction_at | datetime | transactions.transaction_at | Daily summaries, velocity |
| Unit Price / Price / Rate / Selling Price / سعر / سعر البيع | price hints + is_positive_numeric | unit_price / sell_price | Decimal | items.sell_price, transactions.unit_price | Margin, revenue |
| Cost Price / Cost / Purchase Price / تكلفة / سعر الشراء | cost hints + is_positive_numeric | cost_price | Decimal | items.cost_price | Capital at risk, margin |
| Total Amount / Amount / Net / Gross / إجمالي / المبلغ | total hints + is_positive_numeric | total_amount | Decimal | transactions.total_amount | Revenue |
| Current Stock / Stock / On Hand / Balance / رصيد / مخزون | stock hints + is_positive_numeric | current_stock | Decimal | inventory.current_stock | Stockout, dead stock |
| SKU / Code / Item Code / كود / رمز | sku hints + is_text | item_sku | str | items.sku | Matching, POS sync |
| Barcode / EAN / GTIN / باركود | barcode hints + len≥6 | barcode | str | items.barcode | Recovery Match |
| Category / Dept / Group / قسم / فئة | category hints + is_text | category_name | str | categories.name | Grouping |
| Expiry Date / Expiration / Best Before / تاريخ الصلاحية | expiry hints + is_date_like | expiry_date | date | pharmacy_lots.expiry_date | FEFO alerts |
| Batch Number / Lot / تشغيلة / دفعة | batch hints | batch_number | str | pharmacy_lots.batch_number | Recall matching |
| Pack Size / UOM / Case Pack / عبوة / حجم | pack hints | pack_size | str | items.pack_size | Recovery Match |
| Storage Type / Temperature / تخزين / حرارة | storage hints | storage_type | str | items.storage_type | Recovery Match |
| Reorder Level / Min Stock / حد الطلب | reorder hints | reorder_level | Decimal | inventory.reorder_level | Restock agent |
| Supplier / Vendor / المورد | supplier hints | supplier | str | Resolved to suppliers.id | PO, lead time |

**Missing Values**: Rows with required fields (item_name, transaction_at for sales, current_stock for inventory) rejected in normalization.

**Malformed Values**: Currency parsing strips SAR/ر.س/ريال/﷼/commas. Date parsing tries multiple formats. Non-numeric quantities rejected.

**Duplicate Rows**: Transaction dedup via `row_hash` (business_id, item_id, transaction_at, quantity, total_amount).

**Unknown Columns**: Stored in `unmapped_columns`, ignored in ETL.