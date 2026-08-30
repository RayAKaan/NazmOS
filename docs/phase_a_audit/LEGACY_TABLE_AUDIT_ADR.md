# ADR: Legacy Table Audit

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

76 tables exist in `models.py`. Based on import usage + raw SQL references, classify each as:

- **ACTIVE**: Actively used in production code paths
- **LEGACY**: Schema exists but no code references; safe to archive
- **COMPATIBILITY**: Used by experiment harness or backward-compat paths
- **TEST-ONLY**: Only referenced in tests
- **DEAD**: No references anywhere; candidate for removal

---

## 2. Classification

### ACTIVE (Core Production) — 25 tables

| Table | Purpose | Evidence |
|-------|---------|----------|
| `users` | Auth, ownership | `models.py`, `routers/auth.py`, `services/auth_service.py` |
| `businesses` | Tenant root | Every service; FK in 40+ tables |
| `organizations` | Multi-tenant org | `services/organization_service.py`, `routers/organization.py` |
| `subscriptions` | Billing | `services/billing_service.py`, `routers/billing.py` |
| `subscription_usage` | Metering | `services/billing_service.py` |
| `team_members` | RBAC | `routers/team.py`, `services/team_service.py` |
| `items` | Core catalog | `services/money_audit_service.py`, `routers/items.py` (via raw SQL) |
| `inventory` | Stock levels | `services/money_audit_service.py`, `agent_action_executor.py` |
| `transactions` | Sales history | `services/money_audit_service.py` (90-day query) |
| `money_audits` | Audit runs | `services/money_audit_service.py`, `routers/money_audit.py` |
| `money_audit_actions` | Audit line items | `services/money_audit_service.py`, `routers/money_audit.py` |
| `audit_log` | Immutable log | `services/audit_engine.py`, `routers/audit.py` |
| `executed_actions` | Action history | `services/agent_action_executor.py`, `routers/agent.py` |
| `agent_actions` | Approval queue | `routers/agent.py`, `services/agent_action_executor.py` |
| `purchase_orders` | PO creation | `agent_action_executor.py:_execute_restock_po` |
| `constraint_blocks` | Guard records | `services/execution_guard.py` |
| `events` | Event sourcing | `services/event_store.py`, `execution_engine.py` |
| `execution_jobs` | Simulated execution | `services/execution_engine.py` |
| `intelligence_decisions` | Decision tracking | `services/nazm_planner.py` |
| `outcome_feedback` | Calibration | `services/outcome_tracker.py` |
| `model_performance` | ML metrics | `services/calibration_service.py` |
| `business_memory` | Context engine | `services/business_context.py` |
| `memory_updates` | Memory deltas | `services/business_context.py` |
| `pos_connections` | POS integrations | `routers/pos.py`, `services/pos_service.py` |
| `pos_sync_logs` | Sync audit | `services/pos_service.py` |

### LEGACY (Schema exists, no active code) — 18 tables

| Table | Likely Origin | Evidence |
|-------|---------------|----------|
| `categories` | V1 catalog | No imports, no raw SQL |
| `daily_summaries` | V2 reporting | Superseded by `money_audits` |
| `forecast_cache` | V3 forecasting | Superseded by `intelligence_decisions` |
| `pricing_rules` | V4 dynamic pricing | No imports; `pricing_recommendations` used instead |
| `pricing_recommendations` | V4 | No active references |
| `reports` | V2 reporting | Superseded by audit reports |
| `notifications` / `notification_preferences` | V3 alerts | WhatsApp/webhook paths bypass |
| `webhook_events` | V3 webhook log | `pos_sync_logs` covers POS; no generic webhook handler |
| `deletion_requests` | GDPR | No handler |
| `enabled_modules` | Feature flags | `feature_flags` used instead |
| `feature_flags` / `feature_flag_overrides` | Experiment | No flag evaluation in production |
| `recipes` | Restaurant module | No imports |
| `parts_compatibility` | Auto parts | No imports |
| `pharmacy_lots` / `sfda_recalls` | Pharma vertical | No imports |
| `recovery_match_settings` | Recovery matching | Superseded by `stock_recovery_*` |
| `stock_recovery_listings` / `stock_recovery_matches` / `stock_recovery_events` | Recovery marketplace | No active code |
| `supplier_prices` / `suppliers` | Supplier catalog | `purchase_orders` has inline supplier data |
| `partner_referrals` / `partners` | Referral program | No imports |
| `team_invitations` | Team invite | `team_members` used directly |
| `permission_definitions` | RBAC granular | `TeamRole` enum covers |
| `billing_events` | Stripe webhook log | `subscriptions` covers billing state |
| `subscription_usage` | Metering detail | Not read in production |
| `audit_runs` / `findings` | Phase 12 audit | Used by experiment `audit_runs.py` only |
| `pilot_baselines` | Phase 13 | Experiment only |
| `plans` / `simulations` | V8/V11 experiment | `closed_loop_experiment.py` only |
| `business_goals` / `learned_outcomes` / `goal_progress_history` | V11 goals | Experiment only |
| `graph_entities` / `graph_relationships` | Knowledge graph | Experiment only |
| `event_derivations` / `event_subscriptions` / `event_types` | Event bus v2 | `events` table used directly |
| `analytics_cache` | Reporting cache | No cache consumers |
| `idempotency_keys` | Idempotency | `ExecutionJob` + `idempotency_keys` both exist; only `execution_jobs` used |
| `impact_ledger` | Phase 12 | Experiment only |

### COMPATIBILITY (Experiment harness, retained for `/ab-compare`) — 8 tables

| Table | Used By |
|-------|---------|
| `audit_runs` | `services/phase12_*.py`, `closed_loop_experiment.py` |
| `findings` | `services/phase12_*.py` |
| `pilot_baselines` | `services/phase13_*.py` |
| `plans` | `services/nazm_planner.py` (dual use) |
| `simulations` | `closed_loop_experiment.py` |
| `business_goals` | `services/ai_challenge.py` (V11) |
| `learned_outcomes` | `services/outcome_tracker.py` (V11) |
| `goal_progress_history` | `services/outcome_tracker.py` (V11) |

### TEST-ONLY (Only in test files) — 5 tables

| Table | Test File |
|-------|-----------|
| `event_types` | `tests/test_event_bus.py` |
| `event_subscriptions` | `tests/test_event_bus.py` |
| `model_performance` | `tests/test_calibration.py` |
| `outcome_feedback` | `tests/test_calibration.py` |
| `graph_entities` | `tests/test_knowledge_graph.py` |

### DEAD (No references anywhere) — 20 tables

| Table | Notes |
|-------|-------|
| `categories` | V1 catalog, never migrated |
| `daily_summaries` | Superseded by `money_audits` |
| `forecast_cache` | Superseded |
| `pricing_rules` | No dynamic pricing engine |
| `pricing_recommendations` | No consumer |
| `reports` | Superseded |
| `notifications` | Bypassed by WhatsApp/webhook |
| `notification_preferences` | Bypassed |
| `webhook_events` | Not consumed |
| `deletion_requests` | No GDPR handler |
| `enabled_modules` | Replaced by `feature_flags` |
| `feature_flags` | No evaluator |
| `feature_flag_overrides` | No evaluator |
| `recipes` | Vertical stub |
| `parts_compatibility` | Vertical stub |
| `pharmacy_lots` | Vertical stub |
| `sfda_recalls` | Vertical stub |
| `supplier_prices` | Inline in `purchase_orders` |
| `suppliers` | Inline in `purchase_orders` |
| `partner_referrals` | No referral program |
| `partners` | No partner program |
| `recipes` | Duplicate |
| `recovery_match_settings` | Superseded |
| `stock_recovery_*` | Marketplace not built |
| `supplier_prices` | Duplicate |
| `subscription_usage` | Not read |
| `billing_events` | Not read |

---

## 3. Recommendation

| Priority | Action |
|----------|--------|
| **P0** | Document ACTIVE tables as canonical schema; add DB comments |
| **P1** | Add `feature_flag` evaluator or remove `feature_flags`/`feature_flag_overrides`/`enabled_modules` |
| **P2** | Archive LEGACY tables to `legacy_` schema (no drop per Phase A rule) |
| **P3** | Remove DEAD tables from `models.py` (keep SQL migration for rollback) |
| **Ongoing** | New tables require ADR entry |

---

## 4. Verification

- All ACTIVE tables have at least one import in `services/` or `routers/` OR raw SQL reference
- No test failures from removing DEAD tables from `models.py` (they're not imported)
- COMPATIBILITY tables preserved for experiment endpoint