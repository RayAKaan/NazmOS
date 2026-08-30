# NAZMOS Database Forensics

Complete audit of database models, relationships, constraints, and migration history.

---

## Core Entity Relationship Diagram (Verified from Models)

```
User (1) ──< Business >── (1) Organization
    │                    │
    │                    ├─< TeamMember >── User
    │                    ├─< TeamInvitation
    │                    ├─< Subscription >── Stripe
    │                    │
    ├─< Business (owner_id)
    │
    └─< ChatSession >─< ChatMessage
```

```
Business (1) ──< Category
    │
    ├─< Item >──< Inventory (1:1 per business+item)
    │     │
    │     ├─< Transaction (sales, returns, waste, etc.)
    │     ├─< ForecastCache
    │     ├─< PharmacyLot (FEFO)
    │     ├─< Recipe (BOM)
    │     └─< PartCompatibility
    │
    ├─< Supplier (network-level, not tenant-scoped)
    │     ├─< PurchaseOrder
    │     └─< SupplierPrice
    │
    ├─< UploadedFile
    │
    ├─< DailySummary
    ├─< DecisionLog
    ├─< MoneyAudit >──< MoneyAuditAction
    ├─< AgentAction
    │     └─< AgentRun
    │
    ├─< IntelligenceDecision
    ├─< ExecutionJob
    │
    ├─< Event (append-only stream)
    │     ├─< EventDerivation
    │     └─< EventSubscription
    │
    ├─< BusinessMemory (7 doc types per business)
    │     └─< MemoryUpdate (audit)
    │
    ├─< GraphEntity >──< GraphRelationship
    │
    ├─< BusinessContext (external: weather, holidays, etc.)
    ├─< BusinessGoal >──< GoalProgressHistory
    ├─< LearnedOutcome
    ├─< OutcomeFeedback
    ├─< ModelPerformance
    │
    ├─< Plan >──< Simulation
    ├─< AuditRun >──< Finding
    ├─< ImpactLedger
    │
    ├─< RecoveryMatchSettings
    │     ├─< StockRecoveryListing >──< StockRecoveryMatch >──< StockRecoveryEvent
    │
    ├─< POSConnection >──< POSSyncLog >──< WebhookEvent
    │
    ├─< EnabledModule
    ├─< PricingRule >──< PricingRecommendation
    ├─< Notification >──< NotificationPreference
    ├─< Report
    ├─< ExecutedAction
    ├─< ConstraintBlock
    ├─< DeletionRequest
    ├─< AuditLog
    ├─< AnalyticsCache
    ├─< IdempotencyKey
    ├─< FeatureFlagOverride
    ├─< PilotBaseline
    ├─< AutonomyPolicy
    ├─< Partner (platform-level)
    │     └─< PartnerReferral
```

---

## Table Inventory (from models.py — 70+ tables)

### Core Tables (Initial Schema Migration 748e4f2a4e7b)

| Table | PK | Key FKs | Unique Constraints | Indexes | Purpose |
|---|---|---|---|---|---|
| users | id (UUID) | — | email | email, idx_user_role_check | Authentication |
| businesses | id (UUID) | owner_id→users, org_id→organizations | (owner_id) WHERE is_active | owner_id, organization_id | Tenant root |
| organizations | id (UUID) | owner_id→users | slug | slug | Multi-business grouping |
| team_members | id (UUID) | business_id, org_id, user_id | — | business_id, org_id, user_id | RBAC |
| subscriptions | id (UUID) | business_id | business_id, stripe_customer_id, stripe_subscription_id | business_id | Billing |
| categories | id (UUID) | business_id | (business_id, name) | business_id | Product categorization |
| items | id (UUID) | business_id, category_id | — | business_id, category_id, business_id+name, sku | Product catalog |
| inventory | id (UUID) | business_id, item_id | (business_id, item_id) | business_id, item_id | Stock levels |
| transactions | id (UUID) | business_id, item_id | (business_id, row_hash) WHERE row_hash IS NOT NULL | business_id, item_id, business_id+date, date | Sales ledger |
| daily_summaries | id (UUID) | business_id, top_item_id→items | (business_id, date) | business_id+date | Pre-aggregated dashboard |
| forecast_cache | id (UUID) | business_id, item_id | (business_id, item_id) | business_id, expires_at | Prophet forecasts |
| decision_log | id (UUID) | business_id, user_id, chat_message_id, item_id | — | business_id, created_at, action_type | Legacy decisions |
| uploaded_files | id (UUID) | business_id, uploaded_by→users | — | business_id, status, created_at | Upload tracking |
| chat_sessions | id (UUID) | business_id, user_id | — | user_id, business_id, last_message_at | Chat history |
| chat_messages | id (UUID) | session_id | — | session_id, session_id+created_at | Chat messages |
| suppliers | id (UUID) | — | — | city+category | Supplier network (global) |
| purchase_orders | id (UUID) | business_id, supplier_id, agent_action_id | po_number | business_id+created_at, supplier_id | Procurement |
| pos_connections | id (UUID) | business_id | — | business_id | POS integration config |
| pos_sync_logs | id (UUID) | connection_id | — | connection_id+started_at | Sync history |
| webhook_events | id (UUID) | business_id | (provider, external_event_id) | business_id+created_at, status | Webhook audit |
| money_audits | id (UUID) | business_id, generated_by→users | — | business_id+created_at, status | Money Audit reports |
| money_audit_actions | id (UUID) | audit_id, business_id, item_id | — | audit_id, business_id+status, item_id | Recovery actions |
| agent_actions | id (UUID) | business_id, decided_by→users, finding_id | — | business_id+status, created_at | Nazm Agent feed |
| autonomy_policies | id (UUID) | business_id, updated_by→users | (business_id, action_type) | — | Autonomy dials |
| analytics_cache | id (UUID) | business_id | (business_id, analytics_type, period_start, period_end) | — | Cached analytics |
| enabled_modules | id (UUID) | business_id, enabled_by→users | (business_id, module_type) | — | Vertical modules |
| pricing_rules | id (UUID) | business_id, item_id, category_id, created_by→users | — | business_id, item_id | Dynamic pricing |
| pricing_recommendations | id (UUID) | business_id, item_id, applied_by→users | — | business_id | Price suggestions |
| notification_preferences | id (UUID) | user_id, business_id | (user_id, business_id) | business_id | Notification config |
| notifications | id (UUID) | user_id, business_id | — | user_id+created_at, business_id | Notifications |
| reports | id (UUID) | business_id, created_by→users | — | business_id | Generated reports |
| executed_actions | id (UUID) | business_id, decision_id→decision_log, executed_by→users | — | business_id, decision_id, entity_type+entity_id | Action audit |
| constraint_blocks | id (UUID) | business_id | — | business_id+created_at, reason_code | Guardrail violations |
| deletion_requests | id (UUID) | business_id, requested_by→users | — | status+scheduled_purge_at | GDPR |
| audit_log | id (UUID) | business_id, organization_id, user_id | — | business_id+created_at, user_id+created_at, action_type | System audit |
| sfda_recalls | id (UUID) | — | — | drug_code | Pharmacy recalls |
| permission_definitions | id (String) | — | — | — | RBAC definitions |
| team_invitations | id (UUID) | business_id, org_id, invited_by→users | token | token | Team invites |
| billing_events | id (UUID) | business_id | stripe_event_id | business_id | Stripe webhooks |
| subscription_usage | id (UUID) | subscription_id | (subscription_id, usage_date) | — | Usage tracking |

### Phase 0-6 Intelligence Tables (Migrations bc68, 969, 357, efab, 7a3, d3e, etc.)

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| events | id (UUID) | business_id | Universal event stream |
| event_types | id (UUID) | — | Event registry |
| event_subscriptions | id (UUID) | business_id | Consumer subscriptions |
| event_derivations | id (UUID) | business_id, cause_event_id, effect_event_id | Causal links |
| business_context | id (UUID) | business_id | External context (weather, holidays) |
| business_memory | id (UUID) | business_id | 7 memory docs per business |
| memory_updates | id (UUID) | business_id, event_id | Mutation audit |
| graph_entities | id (UUID) | business_id | Knowledge graph nodes |
| graph_relationships | id (UUID) | business_id, source_id, target_id | Knowledge graph edges |
| intelligence_decisions | id (UUID) | business_id | Phase 4 decisions |
| simulations | id (UUID) | business_id | What-if simulations |
| plans | id (UUID) | business_id, simulation_id | Goal-driven plans |
| execution_jobs | id (UUID) | business_id, decision_id, plan_id | External execution tracking |
| outcome_feedback | id (UUID) | business_id, decision_id, execution_job_id, agent_action_id | Predicted vs actual |
| model_performance | id (UUID) | business_id | Learning aggregates |
| learned_outcomes | id (UUID) | business_id, agent_action_id, finding_id | Structured learning |
| business_goals | id (UUID) | business_id | Structured goals |
| goal_progress_history | id (UUID) | goal_id, business_id | Goal trajectory |
| audit_runs | id (UUID) | business_id | Audit execution log |
| findings | id (UUID) | business_id, audit_id, agent_action_id | Canonical findings |
| impact_ledger | id (UUID) | business_id, finding_id, agent_action_id | Value attribution |
| supplier_prices | id (UUID) | supplier_id, item_id, business_id | Real price observations |
| agent_runs | id (UUID) | business_id | AI agent observability |
| pilot_baselines | id (UUID) | business_id, owner_id | Pilot snapshots |
| feature_flags | id (UUID) | — | Feature toggles |
| feature_flag_overrides | id (UUID) | feature_flag_id, business_id | Per-business flags |
| idempotency_keys | id (UUID) | business_id | Idempotent request cache |

### Recovery Match Tables

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| recovery_match_settings | id (UUID) | business_id | Per-business config |
| stock_recovery_listings | id (UUID) | seller_business_id, seller_branch_id, item_id | Excess inventory listings |
| stock_recovery_matches | id (UUID) | listing_id, buyer_business_id, buyer_item_id | Match suggestions |
| stock_recovery_events | id (UUID) | match_id, listing_id, actor_business_id | Match lifecycle |

### Pharmacy Vertical Tables

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| pharmacy_lots | id (UUID) | business_id, item_id, supplier_id | FEFO lot tracking |
| sfda_recalls | id (UUID) | — | Drug recall feed |

### Food/Cafe Vertical Tables

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| recipes | id (UUID) | business_id, menu_item_id→items | Recipe BOM |

### Auto Parts Vertical Tables

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| parts_compatibility | id (UUID) | item_id | Vehicle compatibility |

### Partner Program Tables

| Table | PK | Key FKs | Purpose |
|---|---|---|---|
| partners | id (UUID) | owner_user_id→users | Partner registry |
| partner_referrals | id (UUID) | partner_id, business_id | Referral tracking |

---

## Critical Constraints & Data Integrity

### Financial Precision
- All monetary columns: `Numeric(12,2)` or `Numeric(14,2)` — **never float**
- Check constraints: `cost_price >= 0`, `sell_price >= 0`, `current_stock >= 0`, `quantity > 0`
- `money()` utility in Python enforces `Decimal('0.01')` quantization

### Tenant Isolation
- Every tenant table has `business_id UUID NOT NULL FK → businesses(id) ON DELETE CASCADE`
- Partial unique indexes for dedup: `transactions (business_id, row_hash) WHERE row_hash IS NOT NULL`
- RLS policies (migration a25a714a2de8): `CREATE POLICY ... USING (business_id = app.current_tenant_id())`
- Application role enforcement: `SET LOCAL ROLE app_tenant` after `SET LOCAL app.current_tenant_id`
- `enforce_tenant_filter()` in connection.py blocks cross-tenant even in SQLite dev

### Deduplication
- `transactions.row_hash`: SHA256 of business_id, item_id, transaction_at, quantity, total_amount
- `webhook_events`: Unique on (provider, external_event_id)
- `uploaded_files.sha256_hash`: File-level dedup
- `idempotency_keys`: Unique on (business_id, idempotency_key, scope_method, scope_path)
- `agent_actions`: 6-hour dedup window per item+action_type in `_create_action()`

### Soft Deletes / Archival
- `is_active` boolean on: businesses, categories, items, suppliers, pos_connections, team_members, enabled_modules, pricing_rules, sfda_recalls
- `chat_sessions.is_archived`
- `deletion_requests` for GDPR with grace period

---

## Migration History Analysis (40+ Migrations)

### Key Migration Phases

| Migration | Date | Phase | Major Changes |
|---|---|---|---|
| 748e4f2a4e7b | 2026-07-30 | Initial | Core schema (37 tables) |
| a5b6c7d8e901 | — | — | business.is_active |
| 7598266ca47b | — | — | deletion_requests (GDPR) |
| 7599266ca47c | — | — | webhook_events |
| 969ef7949298 | — | Phase 0 | events, event_types, event_subscriptions |
| bc6893878598 | — | Phase 1 | business_memory, memory_updates (7 memory types) |
| efab679a4d16 | — | Phase 2 | graph_entities, graph_relationships |
| 357f3cbca428 | — | Phase 3 | business_context, event_derivations |
| 7a38b41efb11 | — | Phase 4 | intelligence_decisions |
| c6a487f9ec1e | — | Phase 5 | plans, simulations, execution_jobs, agents |
| d3e7a8c9b10e | — | Phase 6 | outcome_feedback, model_performance, learned_outcomes, business_goals, goal_progress_history |
| a1b2c3d4e5f6 | — | Phase 1 | audit_runs, findings |
| b2c3d4e5f6a7 | — | Phase 2 | impact_ledger, supplier_prices |
| c3d4e5f6a7b8 | — | — | finding decision quality fields |
| c9d0e1f2a3b4 | — | — | finding link + data_quality_note |
| f6a7b8c9d0e1 | — | — | finding decision quality |
| d4e5f6a7b8c9 | — | Phase 4 | goals + learned_outcomes |
| e5f6a7b8c9d0 | — | Phase 5 | goal_history + learning unique constraints |
| f1a2b3c4d5e6 | — | Phase 1 | Merge heads |
| 7a0871d948f8 | — | — | Merge compliance + RLS |
| a25a714a2de8 | — | — | RLS policies |
| e01776a29060 | — | — | RLS for compliance + webhooks |
| b7c8d9e0f1a2 | — | — | RLS for intelligence + recovery |
| c4d6e8f0a2b1 | — | — | RLS predicate indexes |
| 20260824 | — | — | Recovery intelligence upgrade |
| ff01 | — | — | Owner constraints |
| ff02 | — | — | Constraint blocks |
| ff03 | — | — | PO received_items_json |
| 5f0a1b2c3d4e | — | — | One active business per owner |
| 33dd43e565ed | — | — | App role for RLS |
| 9f8e7d6c5b4a | — | — | Platform operator flag |
| 8b3f5c2a1d94 | — | — | Scope idempotency per tenant |
| e8a1b2c3d4e5 | — | — | Partner program |

### Obsolete / Superseded Structures

| Old Table/Column | Superseded By | Migration | Status |
|---|---|---|---|
| `money_audits.money_at_risk_sar` | `capital_at_risk_sar`, `revenue_at_risk_sar`, `gross_profit_at_risk_sar` | 20260824 | LEGACY (kept for compat) |
| `money_audit_actions.expected_recovery_sar` | `expected_recovery_sar_v2`, `recoverable_value_low/high_sar` | 20260824 | LEGACY |
| `decision_log` (legacy) | `intelligence_decisions` | 7a38b41efb11 | LEGACY |
| `agent_actions.finding_id` (new) | Links to `findings` | a1b2c3d4e5f6 | ACTIVE |
| `purchase_orders.received_items_json` | Added for partial receipt tracking | ff03 | ACTIVE |
| `items.shariah_*` columns | Added for halal guardrails | 748e4f2a4e7b | ACTIVE (Pharmacy) |

---

## JSON Columns Analysis

| Table | Column | Purpose | Duplicates Normalized Data? |
|---|---|---|---|
| businesses | operating_hours | Opening hours | No |
| businesses | constraints_json | Owner constraints (pre-recommendation) | No |
| items | shariah_flags | Halal violation details | No |
| uploaded_files | detected_columns, column_mapping, sample_rows, validation_errors, data_quality_report, rows_rejected | Upload metadata | No (transient) |
| forecast_cache | forecast_7d, forecast_30d, weekly_pattern | Prophet output | No (derived) |
| daily_summaries | — | — | No |
| transactions | — | — | No |
| business_memory | data | 7 living documents | **Yes** (projects from events) |
| memory_updates | old_value, new_value | Audit trail | No |
| graph_entities | attributes, vector | Entity metadata + embeddings | No |
| graph_relationships | evidence_event_ids | Supporting events | No |
| business_context | payload | External context | No |
| intelligence_decisions | memory_snapshot, graph_evidence, context_evidence, candidate_actions, ranked_action, explanation | Decision audit | **Yes** (snapshot at decision time) |
| simulations | scenario, assumptions, results | What-if | No |
| plans | steps | Plan steps | No |
| execution_jobs | payload, result, rollback_payload | Execution audit | No |
| outcome_feedback | predicted_outcome, actual_outcome, delta | Learning | No |
| learned_outcomes | execution_result, verification_result | Learning | No |
| money_audits | summary, evidence_summary, missing_data | Audit snapshot | **Yes** (snapshot) |
| money_audit_actions | financial_model, evidence | Action detail | No |
| agent_actions | payload, outcome_json | Agent action data | No |
| agent_runs | decisions, tools_requested, verification | Agent observability | No |
| audit_runs | summary | Audit run summary | No |
| findings | evidence, affected_entities, recommended_action | Finding detail | No |
| impact_ledger | evidence | Impact attribution | No |
| supplier_prices | — | — | No |
| webhook_events | payload | Webhook audit | No |
| pos_sync_logs | errors, raw_response_sample | Sync log | No |
| analytics_cache | results | Cached analytics | **Yes** (derived) |
| notifications | metadata, action_data | Notification extras | No |
| reports | parameters, shared_with | Report config | No |
| recipes | ingredients_json | BOM | No |
| pricing_rules | config | Rule config | No |
| pricing_recommendations | factors | Recommendation factors | No |
| enabled_modules | config, features_enabled | Module config | No |
| team_members | permissions | RBAC permissions | No |

**Concern**: `business_memory.data`, `intelligence_decisions.memory_snapshot`, `money_audits.summary`, `analytics_cache.results` duplicate normalized data. This is intentional for snapshotting but creates staleness risk.

---

## RLS Policy Coverage (Verified from Migration a25a714a2de8)

All tenant-scoped tables have RLS policies enforcing `business_id = app.current_tenant_id()`:

| Table | Policy Name | Using Clause |
|---|---|---|
| businesses | businesses_tenant_isolation | business_id = app.current_tenant_id() |
| categories | categories_tenant_isolation | business_id = app.current_tenant_id() |
| items | items_tenant_isolation | business_id = app.current_tenant_id() |
| inventory | inventory_tenant_isolation | business_id = app.current_tenant_id() |
| transactions | transactions_tenant_isolation | business_id = app.current_tenant_id() |
| daily_summaries | daily_summaries_tenant_isolation | business_id = app.current_tenant_id() |
| forecast_cache | forecast_cache_tenant_isolation | business_id = app.current_tenant_id() |
| uploaded_files | uploaded_files_tenant_isolation | business_id = app.current_tenant_id() |
| money_audits | money_audits_tenant_isolation | business_id = app.current_tenant_id() |
| money_audit_actions | money_audit_actions_tenant_isolation | business_id = app.current_tenant_id() |
| agent_actions | agent_actions_tenant_isolation | business_id = app.current_tenant_id() |
| ... | ... | ... |

**Application Role**: `DATABASE_APP_ROLE` (config) — connection switches via `SET LOCAL ROLE` after setting `app.current_tenant_id`.

**Enforcement Points**:
1. Middleware: `TenantContextMiddleware` sets `_rls_tenant_id` context var
2. DB Session: `get_session()` → `_set_rls_context()` → `SET LOCAL app.current_tenant_id`
3. Transaction: Event listener re-applies on every `BEGIN` (connection.py:65)
4. Sync Session: Celery tasks use `get_sync_session()` with same pattern
5. Guard: `enforce_tenant_filter(business_id)` blocks cross-tenant in code

---

## Indexes for Query Performance

### High-Value Indexes (from models.py)

| Table | Index | Columns | Purpose |
|---|---|---|---|
| transactions | idx_transaction_business_date | (business_id, transaction_at) | Time-series queries |
| transactions | idx_transaction_business | business_id | Tenant filter |
| transactions | uq_transactions_row_hash | (business_id, row_hash) WHERE row_hash IS NOT NULL | Dedup |
| inventory | idx_inventory_business | business_id | Tenant filter |
| inventory | uq_inventory_business_item | (business_id, item_id) | 1:1 guarantee |
| items | idx_item_business_name | (business_id, name) | Name lookup |
| daily_summaries | idx_daily_summary_business_date | (business_id, date) | Dashboard |
| forecast_cache | idx_forecast_cache_expires | expires_at | TTL cleanup |
| forecast_cache | uq_forecast_cache_business_item | (business_id, item_id) | 1:1 |
| uploaded_files | idx_uploaded_files_business | business_id | Tenant filter |
| uploaded_files | idx_uploaded_files_status | status | Processing queue |
| agent_actions | idx_agent_actions_business_status | (business_id, status) | Feed query |
| agent_actions | idx_agent_actions_created | created_at | Recency |
| events | idx_events_business_occurred | (business_id, occurred_at) | Event timeline |
| events | idx_events_business_type | (business_id, event_type) | Projector routing |
| events | idx_events_dedupe | (business_id, source, source_id, checksum) | Idempotency |
| business_memory | uq_business_memory_business_type | (business_id, memory_type) | 1 doc per type |
| business_memory | idx_business_memory_updated | (business_id, updated_at) | Freshness |
| graph_relationships | idx_graph_relationships_source | source_id | Graph traversal |
| graph_relationships | idx_graph_relationships_target | target_id | Graph traversal |
| webhook_events | idx_webhook_events_business_created | (business_id, created_at) | Audit |
| webhook_events | uq_webhook_events_provider_external_id | (provider, external_event_id) | Idempotency |
| audit_runs | idx_audit_runs_business_domain | (business_id, domain, created_at) | Audit history |
| findings | idx_findings_business_status | (business_id, status) | Finding feed |
| impact_ledger | idx_impact_ledger_business_type | (business_id, impact_type) | ROI reporting |
| supplier_prices | idx_supplier_prices_supplier_item | (supplier_id, item_id) | Price lookup |

---

## Dead / Unreferenced Tables (Code Search)

Tables defined in models.py but **no references found in services/routers/tasks**:

| Table | Defined In | Referenced By | Status |
|---|---|---|---|
| `recipes` | models.py:1546 | NOWHERE | **DEAD** (Food vertical, UI gated OFF) |
| `parts_compatibility` | models.py:1574 | NOWHERE | **DEAD** (Auto Parts vertical, UI gated OFF) |
| `sfda_recalls` | models.py:1522 | `shariah_compliance.py` (audit_inventory_halal_status) | ACTIVE (Pharmacy) |
| `enabled_modules` | models.py:741 | NOWHERE | **DEAD** (Superseded by feature_flags) |
| `pricing_rules` | models.py:758 | NOWHERE | **DEAD** (Superseded by intelligence_decisions) |
| `pricing_recommendations` | models.py:787 | NOWHERE | **DEAD** |
| `notification_preferences` | models.py:814 | NOWHERE | **DEAD** |
| `notifications` | models.py:844 | NOWHERE | **DEAD** |
| `reports` | models.py:874 | NOWHERE | **DEAD** |
| `executed_actions` | models.py:908 | NOWHERE | **DEAD** (Superseded by execution_jobs) |
| `constraint_blocks` | models.py:940 | NOWHERE | **DEAD** (Created but never queried) |
| `deletion_requests` | models.py:962 | `compliance_tasks.process_pending_deletions` | ACTIVE (GDPR) |
| `analytics_cache` | models.py:1010 | NOWHERE | **DEAD** |
| `partner_referrals` | models.py:2095 | `partner_service.py` | ACTIVE |
| `permission_definitions` | models.py:636 | NOWHERE | **DEAD** (Unused RBAC) |
| `team_invitations` | models.py:646 | NOWHERE | **DEAD** |
| `billing_events` | models.py:595 | `subscription_service.py` | ACTIVE (Stripe) |
| `subscription_usage` | models.py:575 | `subscription_service.py` | ACTIVE |
| `pilot_baselines` | models.py:1367 | `pilot_readiness.py` | ACTIVE (Pilot) |
| `feature_flags` | models.py:1380 | `feature_flags.py` service | ACTIVE |
| `feature_flag_overrides` | models.py:1400 | `feature_flags.py` service | ACTIVE |
| `idempotency_keys` | models.py:1417 | `IdempotencyMiddleware` | ACTIVE |

---

## Schema Drift Risks

1. **Vertical tables exist but unused**: `recipes`, `parts_compatibility` — created in initial migration, vertical modules gated OFF in config
2. **Legacy decision tables**: `decision_log`, `executed_actions` — superseded by `intelligence_decisions`, `execution_jobs` but not dropped
3. **Notification system**: `notifications`, `notification_preferences` — fully modeled but no service sends notifications
4. **Reports system**: `reports` — fully modeled but no report generation service
5. **Pricing rules**: `pricing_rules`, `pricing_recommendations` — modeled but no dynamic pricing engine consumes them
6. **Analytics cache**: `analytics_cache` — modeled but no cache invalidation/consumption logic
7. **Constraint blocks**: `constraint_blocks` — created by guard but never read for dashboard/alerting

---

## Recommendation: Cleanup Candidates

| Table | Reason | Risk |
|---|---|---|
| recipes, parts_compatibility | Vertical modules disabled, no code references | Low (no data) |
| enabled_modules | Superseded by feature_flags/overrides | Low |
| pricing_rules, pricing_recommendations | No consumer, superseded by intelligence | Low |
| notification_preferences, notifications | No notification service | Low |
| reports | No report generation service | Low |
| executed_actions | Superseded by execution_jobs | Low |
| constraint_blocks | Write-only, never read | Low |
| analytics_cache | No cache writer/reader | Low |
| permission_definitions, team_invitations | Unused RBAC | Low |

> **Note**: These are **DEAD** by code reference analysis. Do not drop without confirming no external dependencies (analytics, BI tools, partner integrations).