# NAZMOS Customer Journey — High Level

Trace of the customer experience from registration through outcomes, mapped to actual code.

---

## Stage 1: Registration & Business Setup

### What the customer does
- Visits landing page → clicks "Get Started"
- Registers with email/password
- Completes onboarding: business name, type, city, currency (SAR), timezone (Asia/Riyadh)

### What NazmOS does
- Creates `User` record (backend/app/database/models.py:155)
- Creates `Business` record linked to owner (models.py:183)
- Creates default `Subscription` (FREE plan, trialing) (models.py:546)
- Seeds `FeatureFlagOverride` for enabled modules
- Creates `TeamMember` with OWNER role

### Data flow
```
POST /api/v1/auth/register → auth_router.py
  → creates User + Business + Subscription
  → returns JWT access/refresh tokens
```

### Stored
- `users`, `businesses`, `subscriptions`, `team_members`

### Can fail
- Email already exists → 409
- Weak password → 422
- Database error → 500

### On failure
- User sees error message, can retry

---

## Stage 2: Data Connection / Upload

### What the customer does
- Navigates to `/upload` page (frontend/src/app/(dashboard)/upload/page.tsx)
- Drags/drops or selects CSV/XLSX file (sales history or inventory snapshot)
- File scanned client-side (PapaParse) or server-side (pandas)
- Reviews auto-detected column mappings
- Confirms mappings → triggers import

### What NazmOS does

**Upload & Scan** (`backend/app/routers/upload.py:63`):
```
POST /api/v1/upload/
  → FileValidator.validate() (file_validator.py)
  → UploadService.parse_file_with_report() (upload_service.py)
  → SchemaDetector().detect() (schema_detector.py)
  → Stores UploadedFile record with status='mapping_required'
  → Returns detected_columns, confidence_scores, sample_rows
```

**Mapping Confirmation** (`upload.py:183`):
```
POST /api/v1/upload/{upload_id}/map
  → Saves column_mapping to UploadedFile
  → Starts ETL: Celery task (if USE_CELERY=true) or inline BackgroundTasks
```

**ETL Pipeline** (`backend/app/services/etl_pipeline.py:76`):
```
ETLPipeline.run()
  → normalize_dataframe() (data_normalizer.py)
  → _upsert_items() → creates/updates Items + Categories
  → _ensure_inventory() → creates Inventory records
  → _apply_inventory_snapshot() → updates current_stock
  → _bulk_insert_transactions() → inserts Transactions with row_hash dedup
  → _rebuild_summaries() → updates DailySummaries
  → _invalidate_forecasts() → clears ForecastCache
  → Updates UploadedFile with row counts, status='completed'
```

### Data enters
- Customer columns → detected meaning → normalized fields → DB columns

| Customer Column | Detection | Internal Field | Type | DB Column | Used By |
|-----------------|-----------|----------------|------|-----------|---------|
| Product Name / Item / Name | name_hints + is_text | item_name | str | items.name | All downstream |
| SKU / Code / Item Code | sku hints | item_sku | str | items.sku | Matching |
| Barcode / EAN / GTIN | barcode hints | barcode | str | items.barcode | Recovery Match |
| Qty / Quantity / Sold Qty | qty hints + is_positive_numeric | quantity | Decimal | transactions.quantity | Velocity, forecasts |
| Current Stock / Stock / On Hand | stock hints | current_stock | Decimal | inventory.current_stock | Stockout, dead stock |
| Sale Date / Date / Transaction Date | date hints + is_date_like | transaction_at | datetime | transactions.transaction_at | Daily summaries, velocity |
| Unit Price / Price / Sell Price | price hints | unit_price / sell_price | Decimal | items.sell_price, transactions.unit_price | Margin, revenue |
| Cost Price / Cost / Purchase Price | cost hints | cost_price | Decimal | items.cost_price | Capital at risk |
| Total Amount / Amount / Net | total hints | total_amount | Decimal | transactions.total_amount | Revenue |
| Category / Dept / Group | category hints | category_name | str | categories.name | Grouping |

### Parsing details
- **Currency**: SAR symbols (SAR, ر.س, ريال, ﷼) stripped in `is_positive_numeric` (schema_detector.py:32)
- **Dates**: Multiple formats supported (YYYY-MM-DD, DD/MM/YYYY, DD-MMM-YYYY, Arabic)
- **Missing values**: Rows with malformed columns rejected (FileValidationError)
- **Duplicates**: `row_hash` on (business_id, item_id, transaction_at, quantity, total_amount) prevents double-count
- **Unknown columns**: Ignored, logged in `unmapped_columns`

### Stored
- `uploaded_files`, `items`, `categories`, `inventory`, `transactions`, `daily_summaries`

### Can fail
- File too large (>15MB) → 413
- Invalid file type → 422
- Malformed CSV → 422 (MALFORMED_CSV)
- Max rows exceeded (100k) → 422
- Mapping required but not provided → 422
- ETL errors → status='failed' with error_summary

### On failure
- Upload stays in 'mapping_required' or 'failed'
- Customer can retry with corrected file
- Rejected rows visible in `/upload/{id}/result`

---

## Stage 3: Data Ingestion & Business Understanding

### What happens automatically
After upload completes:
1. **Forecast generation** (Celery beat: `forecast_tasks.refresh_all_forecasts` daily 03:00)
   - Prophet models per item → `forecast_cache`
2. **Daily summary rebuild** (Celery beat: `analytics_tasks.rebuild_summaries_yesterday` daily 01:00)
3. **Event processing** (every minute: `event_tasks.process_unprocessed_events`)
   - Routes events to memory projectors (`business_memory.py:347`)
   - Updates `business_memory` documents: CURRENT_STATE, PATTERNS, RELATIONSHIPS
4. **Scheduled audit** (daily 06:00: `audit_tasks.daily_full_audit`)
   - Runs Money Audit engine → generates `money_audits` + `money_audit_actions`

### What NazmOS calculates
**Per Item** (`recovery_intelligence.py:88`):
- Classification: NEW, DEAD, SLOW MOVING, FAST, SEASONAL, HEALTHY, UNKNOWN
- Daily velocity (30-day qty / 30)
- Days of supply (stock / daily_velocity)
- Days since last sale
- Monthly concentration (seasonality detection)

**Business-level** (`money_audit_service.py:163`):
- Inventory value (Σ stock × cost_price)
- Capital at risk (dead stock + overstock value)
- Revenue at risk (stockout projection × sell_price)
- Gross profit at risk (margin leakage)
- Recoverable range (low/high, evidence-bounded)
- Expected recovery (only with calibration from completed actions)

### Data stored
- `forecast_cache`, `daily_summaries`, `business_memory` (7 document types), `events`

---

## Stage 4: Money Audit Generation

### What the customer does
- Navigates to `/money-audit` page
- Sees auto-generated audit (or clicks "Regenerate")
- Reviews KPIs: Capital at Risk, Potentially Recoverable, Money Recovered
- Views Money Recovery Map (visual breakdown)
- Reviews Top 3 Decisions (action cards)

### What NazmOS does
```
GET /money-audit/current?auto_generate=true → money_audit_router.py
  → generate_money_audit() (money_audit_service.py:580)
    → compute_money_audit() (money_audit_service.py:163)
      → Complex SQL with CTEs: sales_30, sales_prior, sales_90, monthly_sales
      → classify_inventory() per item
      → estimate_recovery() per classification
      → stockout_financials() for fast movers
      → margin leakage detection
      → Creates MoneyAudit + MoneyAuditAction records
```

### Financial Measures (Critical Distinctions)
| Measure | Meaning | Formula | Stored |
|---------|---------|---------|--------|
| **Inventory Value** | Total stock at cost | Σ current_stock × cost_price | money_audits.inventory_value_sar |
| **Capital at Risk** | Capital tied in dead/overstock | dead_stock_value + overstock_value | money_audits.capital_at_risk_sar |
| **Revenue at Risk** | Projected lost sales from stockouts | Σ stockout_financials.revenue_at_risk | money_audits.revenue_at_risk_sar |
| **Gross Profit at Risk** | Margin leakage + stockout margin | margin_leakage + stockout_gross_profit | money_audits.gross_profit_at_risk_sar |
| **Recoverable Low** | Conservative bound (cost basis) | Σ min(inventory_value, gross_proceeds) | money_audits.recoverable_value_low_sar |
| **Recoverable High** | Optimistic bound (observed prices) | Calibrated or min(cost, gross) | money_audits.recoverable_value_high_sar |
| **Expected Recovery** | Calibrated from completed actions | Median(actual/estimated) × current_estimate | money_audits.expected_recovery_sar |
| **Money Approved** | Sum of approved action estimates | Σ action.expected_recovery (approved) | money_audits.money_approved_sar |
| **Money Recovered** | Sum of completed measured outcomes | Σ action.completed_value_sar | money_audits.money_recovered_sar |

**KEY**: Revenue/Profit at Risk ≠ Recoverable ≠ Expected Recovery ≠ Actual Recovery. These are intentionally separated in v2 financial model.

### Can fail
- No data uploaded → error page redirects to `/upload`
- Insufficient sales history → confidence = "INSUFFICIENT DATA"
- Missing cost prices → warnings in missing_data

---

## Stage 5: Intelligence & Recommendations

### What the customer sees
**Dashboard** (`/dashboard`):
- Action Center (health score, risk alerts, pending approvals)
- KPI Grid (today/week/month sales, profit, transactions)
- Sales trend chart
- Top products / Dead stock tables
- Intelligence Card (Nazm's top recommendation)

**Money Audit** (`/money-audit`):
- Money Recovery Map (visual)
- Top Decisions (approve/reject/complete)
- "One Thing I Would Not Do" (anti-recommendation)
- Time Machine (what if I do nothing?)
- AI Reasoning Panel (V9: deterministic vs AI comparison)
- Recommendation Inbox (Phase 5 pilot workflow)
- Business Constraints (autonomy dials)

### How recommendations are produced

**Deterministic (Nazm Planner)** (`nazm_planner.py:25`):
- Runs every 15 min via Celery beat or manual `/agent/scan`
- Agents: Restock, Pricing, Cash, Expiry (Pharmacy)
- Creates `agent_actions` with status based on autonomy_dial
- WhatsApp approval sent if dial ≥ 50

**Phase 4 Decision Engine** (`decision_engine.py:492`):
```
generate_decision()
  → Loads memory, events, graph, context
  → Generates candidates: restock, pricing, discount, supplier_switch
  → Scores: 0.35×ROI + 0.25×confidence + 0.25×urgency - 0.15×risk
  → Context adjusts: holidays ↑urgency, inflation ↑risk
  → Stores IntelligenceDecision with full explanation
```

**AI Reasoning** (OpenCode Brain) (`opencode_brain.py:402`):
```
reason(evidence, deterministic_decision)
  → Builds evidence prompt (items + business context)
  → Invokes OpenCode CLI subprocess (timeout 30s)
  → Parses JSON response
  → Validates: allowed decisions, confidence range, evidence IDs, risk flags
  → Checks financial hallucination patterns + prompt injection
  → Returns BrainDecision or deterministic fallback
```

### AI Integration Points
1. `/api/v1/intelligence/analyze` → `intelligence_api.analyze()` → `decision_engine.generate_decision()` (deterministic)
2. `/api/v1/intelligence/reason` → `intelligence_api.reason()` → `ai_gateway.reason()` → `opencode_brain.reason()`
3. Money Audit AI Summary → `money_audit_service.generate_money_audit()` includes intelligence_actions
4. Nazm Agent `/agent/reason` → `IntelligenceAPIClient.reason()`

### AI Failure Handling
- Budget exhausted → deterministic fallback
- OpenCode CLI not found → deterministic fallback
- Timeout (30s) → deterministic fallback
- Invalid JSON → deterministic fallback
- Validation failure → deterministic fallback
- Unregistered decision → deterministic fallback
- **NazmOS remains authority**: AI never executes, only recommends

---

## Stage 6: Owner Decision & Approval

### What the customer does
- Reviews action cards on Money Audit or Agent Feed
- Clicks **Approve** / **Reject** / **Record Measured Outcome**
- For WhatsApp: receives message, taps Approve/Reject deep link

### What NazmOS does

**Dashboard Approve** (`money_audit_router.py` → `money_audit_service.update_action_status`):
```
POST /money-audit/actions/{action_id}/approve
  → Validates transition: suggested → approved
  → Sets approved_at, approval_channel='dashboard'
  → Recalculates audit totals (money_approved_sar)
```

**WhatsApp Approve** (`whatsapp_router.py` + `agent_action_executor.py`):
```
GET /api/v1/whatsapp/webhook?action=approve&id=...
  → verify_pos_webhook_auth (HMAC)
  → approve_agent_action() / reject_agent_action()
  → Updates agent_actions status, whatsapp_message_id
```

**Complete with Measured Outcome** (`money_audit_service.py:831`):
```
POST /money-audit/actions/{action_id}/complete
  → Requires completed_value_sar (measured actual recovery)
  → Validates: approved → completed only
  → Sets completed_at, completed_value_sar
  → Calculates prediction_error_pct
  → Records OutcomeFeedback (learning_engine)
  → Recalculates money_recovered_sar
```

### Approval Lifecycle (Enforced)
```
suggested → approved → completed
     ↘ rejected (from suggested or approved)
```
Invalid transitions blocked (e.g., approve twice, complete unapproved)

### Can fail
- Not owner → 403
- Invalid transition → 400 with allowed transitions listed
- Missing completed_value_sar → 400
- WhatsApp token invalid → 401

---

## Stage 7: Action Execution

### What executes
**Internal actions** (no external integration):
- Price changes → UPDATE items.sell_price
- Discount tags → business logic only
- Inventory transfers → UPDATE inventory.current_stock (multi-branch)
- Reorder → Creates PurchaseOrder (draft)

**External actions** (require integration):
- Purchase Order send → WhatsApp to supplier (mock/live)
- Recovery Match → Creates StockRecoveryListing + Match

### Execution Engine (`execution_engine.py`):
```
execute_from_request()
  → Creates ExecutionJob record
  → For POS sync: calls adapter (Foodics/Salla)
  → For WhatsApp: sends template message
  → Updates job status, result, external_reference
```

### Can fail
- Supplier not configured → action stays 'pending_approval'
- WhatsApp API error → logged, action not blocked
- POS sync error → POSSyncLog records failure

---

## Stage 8: Outcome Generation & Learning

### What creates an outcome
1. **Money Audit Action completed** → `update_action_status(status='complete', completed_value_sar=X)`
2. **Agent Action executed** → `approve_agent_action()` with `was_auto_executed=true`
3. **Execution Job completes** → `ExecutionJob.status='completed', result={...}`

### Outcome recorded in
- `money_audit_actions.completed_value_sar` + `completed_at`
- `agent_actions.outcome_json` + `applied_at`
- `outcome_feedback` table (decision_id + actual_outcome)
- `impact_ledger` (money_recovered, revenue_protected, etc.)
- `learned_outcomes` (structured memory with provenance)

### Learning Flow (`learning_engine.py`):
```
refresh_learning() (daily 05:00 Celery beat)
  → Queries outcome_feedback per decision_type
  → Computes accuracy, roi_error, latency
  → Stores ModelPerformance per business/decision_type/window
  → Used by suggest_best_action() (Thompson sampling)
```

### Feedback Loop
```
Action → Approval → Execution → Measured Outcome
    → OutcomeFeedback (predicted vs actual)
    → ModelPerformance (accuracy, ROI error)
    → Future suggestions weighted by performance
```

---

## Stage 9: Future Recommendations Influenced

### How learning affects future
1. **Calibration** (`money_audit_service.py:288`):
   - Completed actions with measured outcomes → calibration_rates per action_type
   - `estimate_recovery()` uses median(calibration_rates) for expected_recovery

2. **Model Performance** (`learning_engine.py`):
   - Per business, per decision_type, rolling window
   - `suggest_best_action()` uses Thompson sampling on historical performance

3. **Business Memory** (`business_memory.py`):
   - Projectors update CURRENT_STATE, PATTERNS, RELATIONSHIPS from events
   - Decision engine loads memory_snapshot for context

4. **Knowledge Graph** (`knowledge_graph.py`):
   - GraphRelationship strength updated from events
   - Supplier reliability, product affinity learned

---

## Complete Data Flow Summary

```
CSV Upload
    ↓
Column Detection (SchemaDetector)
    ↓
ETL Pipeline (normalize → upsert items → inventory → transactions → summaries)
    ↓
Events emitted (sale.completed, inventory.changed, etc.)
    ↓
Event Engine → Memory Projectors → Business Memory (7 doc types)
    ↓
Scheduled/Cron:
  - Forecast (Prophet) → forecast_cache
  - Daily Summaries → daily_summaries
  - Full Audit → money_audits + money_audit_actions
  - Nazm Planner → agent_actions
    ↓
Owner Review (Dashboard / Money Audit / WhatsApp)
    ↓
Approval → Action Execution (internal or external)
    ↓
Measured Outcome → OutcomeFeedback → ImpactLedger
    ↓
Learning Engine → ModelPerformance → Calibration → Future Decisions
```

---

## Failure Modes Summary

| Stage | Failure | User Visible | System Recovery |
|-------|---------|--------------|-----------------|
| Upload | Malformed CSV | Error modal with row details | Re-upload corrected file |
| Upload | Max rows | Error message | Split file |
| ETL | Duplicate row_hash | Silently skipped (dedup) | N/A |
| ETL | Missing item match | Unresolved items logged | Manual mapping or re-upload |
| Audit | No sales data | "Insufficient data" warnings | Upload sales file |
| AI | OpenCode timeout | Silent fallback to deterministic | Logged, budget recorded |
| AI | Validation fail | Silent fallback | Logged with error details |
| Approval | Invalid transition | Error toast with allowed transitions | User retries correct action |
| WhatsApp | Delivery fail | Action still created, status logged | Retry or manual dashboard approve |
| Execution | POS sync fail | POSSyncLog error, webhook retry | Manual retry via admin |