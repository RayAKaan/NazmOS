"""Phase 3: Multi-tenancy, Billing, Teams, POS, Notifications

Revision ID: 003
Revises: 002
Create Date: 2025-03-28 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. SUBSCRIPTION & BILLING
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE subscription_plan AS ENUM ('free', 'basic', 'pro', 'enterprise')")
    op.execute("CREATE TYPE subscription_status AS ENUM ('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'paused')")
    
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('stripe_customer_id', sa.Text, unique=True),
        sa.Column('stripe_subscription_id', sa.Text, unique=True),
        sa.Column('stripe_price_id', sa.Text),
        sa.Column('plan', postgresql.ENUM('free', 'basic', 'pro', 'enterprise', name='subscription_plan', create_type=False), nullable=False, server_default='free'),
        sa.Column('status', postgresql.ENUM('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'paused', name='subscription_status', create_type=False), nullable=False, server_default='trialing'),
        sa.Column('current_period_start', sa.DateTime(timezone=True)),
        sa.Column('current_period_end', sa.DateTime(timezone=True)),
        sa.Column('trial_end', sa.DateTime(timezone=True)),
        sa.Column('cancel_at_period_end', sa.Boolean, server_default='false'),
        sa.Column('canceled_at', sa.DateTime(timezone=True)),
        sa.Column('cancellation_reason', sa.Text),
        sa.Column('ai_queries_limit', sa.Integer, nullable=False, server_default='50'),
        sa.Column('locations_limit', sa.Integer, nullable=False, server_default='1'),
        sa.Column('team_members_limit', sa.Integer, nullable=False, server_default='1'),
        sa.Column('pos_integrations_limit', sa.Integer, nullable=False, server_default='0'),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_subscriptions_business', 'subscriptions', ['business_id'], unique=True)
    op.create_index('idx_subscriptions_stripe_customer', 'subscriptions', ['stripe_customer_id'])
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'])
    
    op.create_table(
        'subscription_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('usage_date', sa.Date, nullable=False),
        sa.Column('ai_queries_used', sa.Integer, server_default='0'),
        sa.Column('decisions_applied', sa.Integer, server_default='0'),
        sa.Column('notifications_sent', sa.Integer, server_default='0'),
        sa.Column('llm_prompt_tokens', sa.Integer, server_default='0'),
        sa.Column('llm_completion_tokens', sa.Integer, server_default='0'),
        sa.Column('estimated_cost_cents', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('subscription_id', 'usage_date', name='uq_subscription_usage_date'),
    )
    op.create_index('idx_subscription_usage_date', 'subscription_usage', ['subscription_id', 'usage_date'])
    
    op.create_table(
        'billing_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('stripe_event_id', sa.Text, unique=True),
        sa.Column('amount_cents', sa.Integer),
        sa.Column('currency', sa.String(3), server_default='INR'),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_billing_events_business', 'billing_events', ['business_id'])
    op.create_index('idx_billing_events_type', 'billing_events', ['event_type'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. MULTI-BUSINESS / CHAIN MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('default_currency', sa.String(3), server_default='INR'),
        sa.Column('default_timezone', sa.String(50), server_default='Asia/Kolkata'),
        sa.Column('logo_url', sa.Text),
        sa.Column('primary_color', sa.String(7), server_default='#3b82f6'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_organizations_owner', 'organizations', ['owner_id'])
    op.create_index('idx_organizations_slug', 'organizations', ['slug'])
    
    # Extend businesses table for multi-location
    op.add_column('businesses', sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL')))
    op.add_column('businesses', sa.Column('location_code', sa.String(20)))
    op.add_column('businesses', sa.Column('location_name', sa.String(100)))
    op.add_column('businesses', sa.Column('latitude', sa.Numeric(10, 8)))
    op.add_column('businesses', sa.Column('longitude', sa.Numeric(11, 8)))
    op.add_column('businesses', sa.Column('is_headquarters', sa.Boolean, server_default='false'))
    op.create_index('idx_businesses_organization', 'businesses', ['organization_id'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. TEAM & PERMISSIONS
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE team_role AS ENUM ('owner', 'admin', 'manager', 'staff', 'accountant', 'viewer')")
    
    op.create_table(
        'team_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', postgresql.ENUM('owner', 'admin', 'manager', 'staff', 'accountant', 'viewer', name='team_role', create_type=False), nullable=False, server_default='staff'),
        sa.Column('permissions', postgresql.JSONB, server_default='[]'),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('invited_at', sa.DateTime(timezone=True)),
        sa.Column('accepted_at', sa.DateTime(timezone=True)),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_team_members_business', 'team_members', ['business_id'])
    op.create_index('idx_team_members_organization', 'team_members', ['organization_id'])
    op.create_index('idx_team_members_user', 'team_members', ['user_id'])
    
    op.create_table(
        'permission_definitions',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('requires_plan', sa.String(20), server_default='free'),
    )
    
    op.execute("""
        INSERT INTO permission_definitions (id, name, description, category) VALUES
        ('view_dashboard', 'View Dashboard', 'View KPIs, charts, and alerts', 'dashboard'),
        ('view_inventory', 'View Inventory', 'View stock levels and item details', 'inventory'),
        ('edit_inventory', 'Edit Inventory', 'Update stock levels manually', 'inventory'),
        ('view_decisions', 'View AI Decisions', 'See AI-generated recommendations', 'decisions'),
        ('apply_decisions', 'Apply Decisions', 'Execute AI decisions', 'decisions'),
        ('reverse_decisions', 'Reverse Decisions', 'Undo previously applied decisions', 'decisions'),
        ('view_reports', 'View Reports', 'Access analytics and reports', 'reports'),
        ('export_reports', 'Export Reports', 'Download reports as PDF/Excel', 'reports'),
        ('manage_team', 'Manage Team', 'Invite and manage team members', 'team'),
        ('manage_billing', 'Manage Billing', 'View and manage subscription', 'billing'),
        ('manage_integrations', 'Manage Integrations', 'Connect POS systems', 'integrations'),
        ('view_chat_history', 'View Chat History', 'See all AI conversations', 'chat'),
        ('configure_notifications', 'Configure Notifications', 'Set up alerts', 'notifications')
    """)
    
    op.create_table(
        'team_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('role', postgresql.ENUM('owner', 'admin', 'manager', 'staff', 'accountant', 'viewer', name='team_role', create_type=False), nullable=False),
        sa.Column('token', sa.String(255), unique=True, nullable=False),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_team_invitations_token', 'team_invitations', ['token'])
    op.create_index('idx_team_invitations_email', 'team_invitations', ['email'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. POS INTEGRATIONS
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE pos_adapter_type AS ENUM ('tally', 'shopify', 'woocommerce', 'zoho', 'csv_webhook', 'custom_api')")
    op.execute("CREATE TYPE pos_sync_status AS ENUM ('never_synced', 'syncing', 'synced', 'error', 'disabled')")
    
    op.create_table(
        'pos_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('adapter_type', postgresql.ENUM('tally', 'shopify', 'woocommerce', 'zoho', 'csv_webhook', 'custom_api', name='pos_adapter_type', create_type=False), nullable=False),
        sa.Column('connection_name', sa.String(100), nullable=False),
        sa.Column('credentials_encrypted', sa.LargeBinary, nullable=False),
        sa.Column('credentials_version', sa.Integer, server_default='1'),
        sa.Column('endpoint_url', sa.Text),
        sa.Column('sync_interval_minutes', sa.Integer, server_default='15'),
        sa.Column('sync_sales', sa.Boolean, server_default='true'),
        sa.Column('sync_inventory', sa.Boolean, server_default='true'),
        sa.Column('push_orders', sa.Boolean, server_default='false'),
        sa.Column('sync_status', postgresql.ENUM('never_synced', 'syncing', 'synced', 'error', 'disabled', name='pos_sync_status', create_type=False), server_default='never_synced'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True)),
        sa.Column('last_sync_duration_seconds', sa.Integer),
        sa.Column('last_sync_records_processed', sa.Integer),
        sa.Column('last_sync_error', sa.Text),
        sa.Column('consecutive_failures', sa.Integer, server_default='0'),
        sa.Column('field_mapping', postgresql.JSONB, server_default='{}'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_pos_connections_business', 'pos_connections', ['business_id'])
    op.create_index('idx_pos_connections_status', 'pos_connections', ['sync_status'])
    
    op.create_table(
        'pos_sync_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pos_connections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('records_fetched', sa.Integer, server_default='0'),
        sa.Column('records_created', sa.Integer, server_default='0'),
        sa.Column('records_updated', sa.Integer, server_default='0'),
        sa.Column('records_skipped', sa.Integer, server_default='0'),
        sa.Column('records_failed', sa.Integer, server_default='0'),
        sa.Column('errors', postgresql.JSONB, server_default='[]'),
        sa.Column('raw_response_sample', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_pos_sync_logs_connection', 'pos_sync_logs', ['connection_id', 'started_at'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. INDUSTRY MODULES
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE module_type AS ENUM ('supermart', 'cafe', 'restaurant', 'hotel', 'retail', 'pharmacy', 'kirana')")
    
    op.create_table(
        'enabled_modules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module_type', postgresql.ENUM('supermart', 'cafe', 'restaurant', 'hotel', 'retail', 'pharmacy', 'kirana', name='module_type', create_type=False), nullable=False),
        sa.Column('is_enabled', sa.Boolean, server_default='true'),
        sa.Column('config', postgresql.JSONB, server_default='{}'),
        sa.Column('features_enabled', postgresql.JSONB, server_default='[]'),
        sa.Column('enabled_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('enabled_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.UniqueConstraint('business_id', 'module_type', name='uq_enabled_modules_business_type'),
    )
    op.create_index('idx_enabled_modules_business', 'enabled_modules', ['business_id'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. PRICING RULES & OPTIMIZATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE pricing_rule_type AS ENUM ('static', 'dynamic', 'time_based', 'demand_based', 'competitor', 'bundle', 'margin_target')")
    
    op.create_table(
        'pricing_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='CASCADE'), nullable=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('categories.id', ondelete='CASCADE'), nullable=True),
        sa.Column('apply_to_all', sa.Boolean, server_default='false'),
        sa.Column('rule_type', postgresql.ENUM('static', 'dynamic', 'time_based', 'demand_based', 'competitor', 'bundle', 'margin_target', name='pricing_rule_type', create_type=False), nullable=False),
        sa.Column('rule_name', sa.String(100), nullable=False),
        sa.Column('config', postgresql.JSONB, nullable=False),
        sa.Column('min_price', sa.Numeric(12, 2)),
        sa.Column('max_price', sa.Numeric(12, 2)),
        sa.Column('min_margin_percent', sa.Numeric(5, 2), server_default='10'),
        sa.Column('max_adjustment_percent', sa.Numeric(5, 2), server_default='25'),
        sa.Column('active_from', sa.DateTime(timezone=True)),
        sa.Column('active_to', sa.DateTime(timezone=True)),
        sa.Column('priority', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_pricing_rules_business', 'pricing_rules', ['business_id'])
    op.create_index('idx_pricing_rules_item', 'pricing_rules', ['item_id'])
    op.create_index('idx_pricing_rules_active', 'pricing_rules', ['is_active', 'active_from', 'active_to'])
    
    op.create_table(
        'pricing_recommendations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('current_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('current_margin_percent', sa.Numeric(5, 2)),
        sa.Column('recommended_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('recommended_margin_percent', sa.Numeric(5, 2)),
        sa.Column('expected_demand_change_percent', sa.Numeric(5, 2)),
        sa.Column('expected_revenue_change', sa.Numeric(12, 2)),
        sa.Column('expected_profit_change', sa.Numeric(12, 2)),
        sa.Column('reasoning', sa.Text, nullable=False),
        sa.Column('factors', postgresql.JSONB, nullable=False),
        sa.Column('confidence', sa.Numeric(4, 2), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('applied_at', sa.DateTime(timezone=True)),
        sa.Column('applied_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_pricing_recommendations_business', 'pricing_recommendations', ['business_id'])
    op.create_index('idx_pricing_recommendations_pending', 'pricing_recommendations', ['status', 'valid_until'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE notification_channel AS ENUM ('whatsapp', 'sms', 'email', 'in_app', 'push')")
    op.execute("CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'delivered', 'failed', 'read')")
    op.execute("CREATE TYPE notification_priority AS ENUM ('critical', 'high', 'medium', 'low')")
    
    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('whatsapp_enabled', sa.Boolean, server_default='true'),
        sa.Column('whatsapp_number', sa.String(20)),
        sa.Column('email_enabled', sa.Boolean, server_default='true'),
        sa.Column('email_address', sa.String(255)),
        sa.Column('sms_enabled', sa.Boolean, server_default='false'),
        sa.Column('sms_number', sa.String(20)),
        sa.Column('in_app_enabled', sa.Boolean, server_default='true'),
        sa.Column('push_enabled', sa.Boolean, server_default='false'),
        sa.Column('push_token', sa.Text),
        sa.Column('alert_preferences', postgresql.JSONB, server_default='{}'),
        sa.Column('quiet_hours_enabled', sa.Boolean, server_default='false'),
        sa.Column('quiet_hours_start', sa.Time, server_default='22:00'),
        sa.Column('quiet_hours_end', sa.Time, server_default='07:00'),
        sa.Column('max_whatsapp_per_day', sa.Integer, server_default='10'),
        sa.Column('max_sms_per_day', sa.Integer, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('user_id', 'business_id', name='uq_notification_preferences_user_business'),
    )
    op.create_index('idx_notification_preferences_user', 'notification_preferences', ['user_id'])
    op.create_index('idx_notification_preferences_business', 'notification_preferences', ['business_id'])
    
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('body_html', sa.Text),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('priority', postgresql.ENUM('critical', 'high', 'medium', 'low', name='notification_priority', create_type=False), nullable=False, server_default='medium'),
        sa.Column('channel', postgresql.ENUM('whatsapp', 'sms', 'email', 'in_app', 'push', name='notification_channel', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'sent', 'delivered', 'failed', 'read', name='notification_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('delivered_at', sa.DateTime(timezone=True)),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.Column('failed_at', sa.DateTime(timezone=True)),
        sa.Column('failure_reason', sa.Text),
        sa.Column('external_id', sa.Text),
        sa.Column('action_url', sa.Text),
        sa.Column('action_data', postgresql.JSONB),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_notifications_user', 'notifications', ['user_id', 'created_at'])
    op.create_index('idx_notifications_business', 'notifications', ['business_id'])
    op.create_index('idx_notifications_pending', 'notifications', ['status', 'created_at'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. REPORTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE report_type AS ENUM ('daily_summary', 'weekly_summary', 'monthly_summary', 'inventory_report', 'sales_report', 'profit_report', 'dead_stock_report', 'pricing_report', 'forecast_report', 'decision_report', 'tax_report', 'custom')")
    op.execute("CREATE TYPE report_status AS ENUM ('queued', 'generating', 'completed', 'failed')")
    op.execute("CREATE TYPE report_format AS ENUM ('pdf', 'xlsx', 'csv', 'json')")
    
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report_type', postgresql.ENUM('daily_summary', 'weekly_summary', 'monthly_summary', 'inventory_report', 'sales_report', 'profit_report', 'dead_stock_report', 'pricing_report', 'forecast_report', 'decision_report', 'tax_report', 'custom', name='report_type', create_type=False), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('parameters', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('status', postgresql.ENUM('queued', 'generating', 'completed', 'failed', name='report_status', create_type=False), nullable=False, server_default='queued'),
        sa.Column('format', postgresql.ENUM('pdf', 'xlsx', 'csv', 'json', name='report_format', create_type=False), nullable=False, server_default='pdf'),
        sa.Column('file_url', sa.Text),
        sa.Column('file_size_bytes', sa.BigInteger),
        sa.Column('page_count', sa.Integer),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('generation_time_seconds', sa.Integer),
        sa.Column('error_message', sa.Text),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('is_scheduled', sa.Boolean, server_default='false'),
        sa.Column('schedule_cron', sa.String(100)),
        sa.Column('next_run_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('shared_with', postgresql.JSONB, server_default='[]'),
        sa.Column('is_public', sa.Boolean, server_default='false'),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_reports_business', 'reports', ['business_id'])
    op.create_index('idx_reports_status', 'reports', ['status'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. ACTION EXECUTION & REVERSAL
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.execute("CREATE TYPE action_status AS ENUM ('pending', 'executing', 'completed', 'failed', 'reversed')")
    op.execute("CREATE TYPE action_source AS ENUM ('ai_auto', 'ai_approved', 'manual', 'scheduled', 'pos_sync')")
    
    op.create_table(
        'executed_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('decision_log.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source', postgresql.ENUM('ai_auto', 'ai_approved', 'manual', 'scheduled', 'pos_sync', name='action_source', create_type=False), nullable=False),
        sa.Column('action_type', sa.String(30), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('previous_state', postgresql.JSONB, nullable=False),
        sa.Column('new_state', postgresql.JSONB, nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'executing', 'completed', 'failed', 'reversed', name='action_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('executed_at', sa.DateTime(timezone=True)),
        sa.Column('executed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('external_actions', postgresql.JSONB, server_default='[]'),
        sa.Column('is_reversible', sa.Boolean, server_default='true'),
        sa.Column('is_reversed', sa.Boolean, server_default='false'),
        sa.Column('reversed_at', sa.DateTime(timezone=True)),
        sa.Column('reversed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('reversal_reason', sa.Text),
        sa.Column('outcome', postgresql.JSONB),
        sa.Column('outcome_computed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_executed_actions_business', 'executed_actions', ['business_id'])
    op.create_index('idx_executed_actions_decision', 'executed_actions', ['decision_id'])
    op.create_index('idx_executed_actions_entity', 'executed_actions', ['entity_type', 'entity_id'])
    op.create_index('idx_executed_actions_status', 'executed_actions', ['status'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 10. AUDIT LOG (Partitioned)
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True)),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('user_email', sa.String(255)),
        sa.Column('user_role', sa.String(30)),
        sa.Column('action_type', sa.String(100), nullable=False),
        sa.Column('action_category', sa.String(30), nullable=False),
        sa.Column('entity_type', sa.String(50)),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True)),
        sa.Column('entity_name', sa.String(255)),
        sa.Column('old_value', postgresql.JSONB),
        sa.Column('new_value', postgresql.JSONB),
        sa.Column('ip_address', postgresql.INET),
        sa.Column('user_agent', sa.Text),
        sa.Column('request_id', postgresql.UUID(as_uuid=True)),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_audit_log_business', 'audit_log', ['business_id', 'created_at'])
    op.create_index('idx_audit_log_user', 'audit_log', ['user_id', 'created_at'])
    op.create_index('idx_audit_log_action', 'audit_log', ['action_type', 'created_at'])
    op.create_index('idx_audit_log_entity', 'audit_log', ['entity_type', 'entity_id', 'created_at'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 11. ANALYTICS CACHE
    # ═══════════════════════════════════════════════════════════════════════════
    
    op.create_table(
        'analytics_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('analytics_type', sa.String(50), nullable=False),
        sa.Column('period_start', sa.Date, nullable=False),
        sa.Column('period_end', sa.Date, nullable=False),
        sa.Column('results', postgresql.JSONB, nullable=False),
        sa.Column('computation_time_ms', sa.Integer),
        sa.Column('records_analyzed', sa.Integer),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('business_id', 'analytics_type', 'period_start', 'period_end', name='uq_analytics_cache_key'),
    )
    op.create_index('idx_analytics_cache_business', 'analytics_cache', ['business_id'])
    op.create_index('idx_analytics_cache_expires', 'analytics_cache', ['expires_at'])

    # ═══════════════════════════════════════════════════════════════════════════
    # 12. EXTEND EXISTING TABLES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Users: Add security fields
    op.add_column('users', sa.Column('phone_verified', sa.Boolean, server_default='false'))
    op.add_column('users', sa.Column('email_verified', sa.Boolean, server_default='false'))
    op.add_column('users', sa.Column('two_factor_enabled', sa.Boolean, server_default='false'))
    op.add_column('users', sa.Column('two_factor_secret', sa.Text))
    op.add_column('users', sa.Column('last_password_change', sa.DateTime(timezone=True)))
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True)))
    
    # Items: Add pricing optimization fields
    op.add_column('items', sa.Column('min_price', sa.Numeric(12, 2)))
    op.add_column('items', sa.Column('max_price', sa.Numeric(12, 2)))
    op.add_column('items', sa.Column('competitor_price', sa.Numeric(12, 2)))
    op.add_column('items', sa.Column('competitor_updated_at', sa.DateTime(timezone=True)))
    op.add_column('items', sa.Column('price_elasticity', sa.Numeric(5, 3)))
    op.add_column('items', sa.Column('last_price_change', sa.DateTime(timezone=True)))
    op.add_column('items', sa.Column('price_change_count_30d', sa.Integer, server_default='0'))
    
    # Inventory: Add more tracking fields
    op.add_column('inventory', sa.Column('supplier_id', postgresql.UUID(as_uuid=True)))
    op.add_column('inventory', sa.Column('lead_time_days', sa.Integer, server_default='2'))
    op.add_column('inventory', sa.Column('safety_stock', sa.Numeric(12, 2)))
    op.add_column('inventory', sa.Column('economic_order_qty', sa.Numeric(12, 2)))
    op.add_column('inventory', sa.Column('last_stockout_date', sa.Date))
    op.add_column('inventory', sa.Column('stockout_count_90d', sa.Integer, server_default='0'))
    
    # Businesses: Add operational fields
    op.add_column('businesses', sa.Column('operating_hours', postgresql.JSONB))
    op.add_column('businesses', sa.Column('contact_phone', sa.String(20)))
    op.add_column('businesses', sa.Column('contact_email', sa.String(255)))
    op.add_column('businesses', sa.Column('gstin', sa.String(15)))
    op.add_column('businesses', sa.Column('pan', sa.String(10)))


def downgrade() -> None:
    # Drop in reverse order due to dependencies
    
    # 12. Remove extended columns
    op.drop_column('businesses', 'pan')
    op.drop_column('businesses', 'gstin')
    op.drop_column('businesses', 'contact_email')
    op.drop_column('businesses', 'contact_phone')
    op.drop_column('businesses', 'operating_hours')
    
    op.drop_column('inventory', 'stockout_count_90d')
    op.drop_column('inventory', 'last_stockout_date')
    op.drop_column('inventory', 'economic_order_qty')
    op.drop_column('inventory', 'safety_stock')
    op.drop_column('inventory', 'lead_time_days')
    op.drop_column('inventory', 'supplier_id')
    
    op.drop_column('items', 'price_change_count_30d')
    op.drop_column('items', 'last_price_change')
    op.drop_column('items', 'price_elasticity')
    op.drop_column('items', 'competitor_updated_at')
    op.drop_column('items', 'competitor_price')
    op.drop_column('items', 'max_price')
    op.drop_column('items', 'min_price')
    
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'last_password_change')
    op.drop_column('users', 'two_factor_secret')
    op.drop_column('users', 'two_factor_enabled')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'phone_verified')
    
    # 11. Drop analytics cache
    op.drop_table('analytics_cache')
    
    # 10. Drop audit log
    op.drop_table('audit_log')
    
    # 9. Drop executed actions
    op.drop_table('executed_actions')
    op.execute("DROP TYPE IF EXISTS action_source")
    op.execute("DROP TYPE IF EXISTS action_status")
    
    # 8. Drop reports
    op.drop_table('reports')
    op.execute("DROP TYPE IF EXISTS report_format")
    op.execute("DROP TYPE IF EXISTS report_status")
    op.execute("DROP TYPE IF EXISTS report_type")
    
    # 7. Drop notifications
    op.drop_table('notifications')
    op.drop_table('notification_preferences')
    op.execute("DROP TYPE IF EXISTS notification_priority")
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute("DROP TYPE IF EXISTS notification_channel")
    
    # 6. Drop pricing
    op.drop_table('pricing_recommendations')
    op.drop_table('pricing_rules')
    op.execute("DROP TYPE IF EXISTS pricing_rule_type")
    
    # 5. Drop modules
    op.drop_table('enabled_modules')
    op.execute("DROP TYPE IF EXISTS module_type")
    
    # 4. Drop POS
    op.drop_table('pos_sync_logs')
    op.drop_table('pos_connections')
    op.execute("DROP TYPE IF EXISTS pos_sync_status")
    op.execute("DROP TYPE IF EXISTS pos_adapter_type")
    
    # 3. Drop team
    op.drop_table('team_invitations')
    op.drop_table('team_members')
    op.execute("DROP TYPE IF EXISTS team_role")
    op.drop_table('permission_definitions')
    
    # 2. Drop multi-business
    op.drop_column('businesses', 'is_headquarters')
    op.drop_column('businesses', 'longitude')
    op.drop_column('businesses', 'latitude')
    op.drop_column('businesses', 'location_name')
    op.drop_column('businesses', 'location_code')
    op.drop_column('businesses', 'organization_id')
    op.drop_table('organizations')
    
    # 1. Drop billing
    op.drop_table('billing_events')
    op.drop_table('subscription_usage')
    op.drop_table('subscriptions')
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.execute("DROP TYPE IF EXISTS subscription_plan")
