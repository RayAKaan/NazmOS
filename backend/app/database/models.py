from sqlalchemy import Column, String, Boolean, DateTime, Numeric, ForeignKey, CheckConstraint, Index, UniqueConstraint, text, BigInteger, JSON, Enum, Time, LargeBinary, Date, Integer
from app.database.types import UUID
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from decimal import Decimal
import uuid


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class SubscriptionPlan(str, PyEnum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, PyEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    PAUSED = "paused"


class TeamRole(str, PyEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


class POSAdapterType(str, PyEnum):
    TALLY = "tally"
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"
    ZOHO = "zoho"
    CSV_WEBHOOK = "csv_webhook"
    CUSTOM_API = "custom_api"
    FOODICS = "foodics"
    SALLA = "salla"


class POSSyncStatus(str, PyEnum):
    NEVER_SYNCED = "never_synced"
    SYNCING = "syncing"
    SYNCED = "synced"
    ERROR = "error"
    DISABLED = "disabled"


class ModuleType(str, PyEnum):
    SUPERMART = "supermart"
    CAFE = "cafe"
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    RETAIL = "retail"
    PHARMACY = "pharmacy"
    BAQALA = "baqala"
    GROCERY = "grocery"


class PricingRuleType(str, PyEnum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    TIME_BASED = "time_based"
    DEMAND_BASED = "demand_based"
    COMPETITOR = "competitor"
    BUNDLE = "bundle"
    MARGIN_TARGET = "margin_target"


class NotificationChannel(str, PyEnum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"
    PUSH = "push"


class NotificationStatus(str, PyEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class NotificationPriority(str, PyEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReportType(str, PyEnum):
    DAILY_SUMMARY = "daily_summary"
    WEEKLY_SUMMARY = "weekly_summary"
    MONTHLY_SUMMARY = "monthly_summary"
    INVENTORY_REPORT = "inventory_report"
    SALES_REPORT = "sales_report"
    PROFIT_REPORT = "profit_report"
    DEAD_STOCK_REPORT = "dead_stock_report"
    PRICING_REPORT = "pricing_report"
    FORECAST_REPORT = "forecast_report"
    DECISION_REPORT = "decision_report"
    TAX_REPORT = "tax_report"
    CUSTOM = "custom"


class ReportStatus(str, PyEnum):
    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportFormat(str, PyEnum):
    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"


class ActionStatus(str, PyEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class ActionSource(str, PyEnum):
    AI_AUTO = "ai_auto"
    AI_APPROVED = "ai_approved"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    POS_SYNC = "pos_sync"


# ═══════════════════════════════════════════════════════════════════════════
# CORE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    role = Column(String(20), default="owner")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    phone_verified = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)
    last_password_change = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('owner', 'manager', 'staff', 'admin')", name="user_role_check"),
    )


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    address = Column(String, nullable=True)
    city = Column(String(100), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    currency = Column(String(3), default="SAR")
    timezone = Column(String(50), default="Asia/Riyadh")
    is_demo = Column(Boolean, default=False)
    llm_usage_tokens = Column(BigInteger, default=0)
    llm_requests_today = Column(Numeric(10, 0), default=0)
    last_forecast_run = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    location_code = Column(String(20), nullable=True)
    location_name = Column(String(100), nullable=True)
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    is_headquarters = Column(Boolean, default=False)
    
    operating_hours = Column(JSON, nullable=True)
    contact_phone = Column(String(20), nullable=True)
    contact_email = Column(String(255), nullable=True)
    # KSA commercial registration fields
    cr_number = Column(String(20), nullable=True)   # MISA / Ministry of Commerce CR Number
    wasfaty_id = Column(String(30), nullable=True)  # Community Pharmacy Wasfaty ID

    __table_args__ = (
        CheckConstraint("type IN ('supermart', 'cafe', 'retail', 'hotel', 'restaurant', 'pharmacy', 'grocery', 'baqala')", name="business_type_check"),
        Index("idx_business_owner", "owner_id"),
        Index("idx_businesses_organization", "organization_id"),
    )


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String, nullable=True)
    sort_order = Column(Numeric(10, 0), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_category_business_name"),
        Index("idx_category_business", "business_id"),
    )


class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), nullable=True)
    unit = Column(String(50), default="piece")
    cost_price = Column(Numeric(12, 2), nullable=False)
    sell_price = Column(Numeric(12, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), default=0)
    is_active = Column(Boolean, default=True)
    last_forecasted = Column(DateTime(timezone=True), nullable=True)
    forecast_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    min_price = Column(Numeric(12, 2), nullable=True)
    max_price = Column(Numeric(12, 2), nullable=True)
    competitor_price = Column(Numeric(12, 2), nullable=True)
    competitor_updated_at = Column(DateTime(timezone=True), nullable=True)
    price_elasticity = Column(Numeric(5, 3), nullable=True)
    last_price_change = Column(DateTime(timezone=True), nullable=True)
    price_change_count_30d = Column(Integer, default=0)

    # Shariah ethics guardrails – populated during item import/POS sync/manual checks
    shariah_status = Column(String(30), default="unknown")  # unknown, halal_guard_passed, flagged_haram, review_required
    shariah_flags = Column(JSON, nullable=True)
    shariah_checked_at = Column(DateTime(timezone=True), nullable=True)

    # Recovery Match identity/safety metadata
    barcode = Column(String(100), nullable=True)
    brand = Column(String(100), nullable=True)
    pack_size = Column(String(50), nullable=True)  # e.g. 24x330ml, 1kg, 250g
    storage_type = Column(String(30), nullable=True)  # ambient, chilled, frozen, regulated

    __table_args__ = (
        CheckConstraint("cost_price >= 0", name="item_cost_price_check"),
        CheckConstraint("sell_price >= 0", name="item_sell_price_check"),
        Index("idx_item_business", "business_id"),
        Index("idx_item_category", "category_id"),
        Index("idx_item_business_name", "business_id", "name"),
        Index("idx_item_sku", "sku"),
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    current_stock = Column(Numeric(12, 2), nullable=False, default=0)
    reorder_level = Column(Numeric(12, 2), default=10)
    max_stock = Column(Numeric(12, 2), default=100)
    last_restocked = Column(DateTime(timezone=True), nullable=True)
    forecasted_demand_7d = Column(Numeric(12, 2), nullable=True)
    forecasted_demand_30d = Column(Numeric(12, 2), nullable=True)
    forecast_confidence = Column(Numeric(4, 2), nullable=True)
    anomaly_flag = Column(Boolean, default=False)
    anomaly_detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    supplier_id = Column(UUID(as_uuid=True), nullable=True)
    lead_time_days = Column(Integer, default=2)
    safety_stock = Column(Numeric(12, 2), nullable=True)
    economic_order_qty = Column(Numeric(12, 2), nullable=True)
    last_stockout_date = Column(Date, nullable=True)
    stockout_count_90d = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("business_id", "item_id", name="uq_inventory_business_item"),
        CheckConstraint("current_stock >= 0", name="inventory_stock_check"),
        Index("idx_inventory_business", "business_id"),
        Index("idx_inventory_item", "item_id"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    quantity = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    cost_price = Column(Numeric(12, 2), nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    profit = Column(Numeric(12, 2), nullable=False)
    transaction_type = Column(String(20), default="sale")
    payment_method = Column(String(20), default="cash")
    reference_id = Column(String(100), nullable=True, index=True)  # External POS webhook reference ID
    row_hash = Column(String(64), nullable=True)
    transaction_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("quantity > 0", name="transaction_quantity_check"),
        CheckConstraint("transaction_type IN ('sale', 'return', 'waste')", name="transaction_type_check"),
        Index("idx_transaction_business", "business_id"),
        Index("idx_transaction_item", "item_id"),
        Index("idx_transaction_business_date", "business_id", "transaction_at"),
        Index("idx_transaction_date", "transaction_at"),
        # Dedup: one row_hash per tenant; NULL row_hash (legacy/webhook rows)
        # is exempt so those rows are not blocked by the uniqueness.
        Index(
            "uq_transactions_row_hash",
            "business_id",
            "row_hash",
            unique=True,
            postgresql_where=text("row_hash IS NOT NULL"),
        ),
    )


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    total_sales = Column(Numeric(12, 2), default=0)
    total_profit = Column(Numeric(12, 2), default=0)
    total_transactions = Column(Numeric(10, 0), default=0)
    top_item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=True)
    top_item_qty = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "date", name="uq_daily_summary_business_date"),
        Index("idx_daily_summary_business_date", "business_id", "date"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 MODELS
# ═══════════════════════════════════════════════════════════════════════════

class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stored_filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String, nullable=False)
    sha256_hash = Column(String, nullable=False)
    status = Column(String(20), default="uploaded")
    row_count_raw = Column(Numeric(10, 0), nullable=True)
    row_count_imported = Column(Numeric(10, 0), nullable=True)
    row_count_failed = Column(Numeric(10, 0), default=0)
    detected_columns = Column(JSON, nullable=True)
    column_mapping = Column(JSON, nullable=True)
    sample_rows = Column(JSON, nullable=True)
    date_range_start = Column(DateTime(timezone=True), nullable=True)
    date_range_end = Column(DateTime(timezone=True), nullable=True)
    validation_errors = Column(JSON, default=[])
    error_summary = Column(String, nullable=True)
    scan_completed_at = Column(DateTime(timezone=True), nullable=True)
    mapping_saved_at = Column(DateTime(timezone=True), nullable=True)
    etl_started_at = Column(DateTime(timezone=True), nullable=True)
    etl_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    celery_task_id = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_uploaded_files_business", "business_id"),
        Index("idx_uploaded_files_status", "status"),
        Index("idx_uploaded_files_created", "created_at"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=True)
    message_count = Column(Numeric(10, 0), default=0)
    total_tokens = Column(Numeric(10, 0), default=0)
    is_archived = Column(Boolean, default=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_chat_sessions_user", "user_id"),
        Index("idx_chat_sessions_business", "business_id"),
        Index("idx_chat_sessions_last_msg", "last_message_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(String, nullable=False)
    content_tokens = Column(Numeric(10, 0), nullable=True)
    model_used = Column(String(50), nullable=True)
    prompt_tokens = Column(Numeric(10, 0), nullable=True)
    completion_tokens = Column(Numeric(10, 0), nullable=True)
    latency_ms = Column(Numeric(10, 0), nullable=True)
    finish_reason = Column(String(30), nullable=True)
    decisions = Column(JSON, default=[])
    context_snapshot = Column(JSON, nullable=True)
    feedback = Column(String(10), nullable=True)
    feedback_note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="chat_message_role_check"),
        Index("idx_chat_messages_session", "session_id"),
        Index("idx_chat_messages_created", "session_id", "created_at"),
    )


class ForecastCache(Base):
    __tablename__ = "forecast_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    model_version = Column(String(20), default="prophet_v1")
    training_rows = Column(Numeric(10, 0), nullable=True)
    training_from = Column(DateTime(timezone=True), nullable=True)
    training_to = Column(DateTime(timezone=True), nullable=True)
    mape_score = Column(Numeric(5, 2), nullable=True)
    rmse_score = Column(Numeric(10, 2), nullable=True)
    forecast_7d = Column(JSON, nullable=False)
    forecast_30d = Column(JSON, nullable=False)
    weekly_pattern = Column(JSON, nullable=False)
    trend_direction = Column(String(10), nullable=True)
    trend_strength = Column(Numeric(5, 2), nullable=True)
    trained_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "item_id", name="uq_forecast_cache_business_item"),
        Index("idx_forecast_cache_business", "business_id"),
        Index("idx_forecast_cache_expires", "expires_at"),
    )


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    chat_message_id = Column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(30), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String, nullable=False)
    quantity = Column(Numeric(12, 2), nullable=True)
    estimated_value = Column(Numeric(12, 2), nullable=True)
    confidence = Column(Numeric(4, 2), nullable=True)
    by_when = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String, nullable=False)
    raw_output = Column(JSON, nullable=True)
    was_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    actual_outcome = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_decision_log_business", "business_id"),
        Index("idx_decision_log_created", "created_at"),
        Index("idx_decision_log_action", "action_type"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 MODELS
# ═══════════════════════════════════════════════════════════════════════════

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    default_currency = Column(String(3), default="SAR")
    default_timezone = Column(String(50), default="Asia/Riyadh")
    logo_url = Column(String, nullable=True)
    primary_color = Column(String(7), default="#3b82f6")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    stripe_customer_id = Column(String, unique=True, nullable=True)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    stripe_price_id = Column(String, nullable=True)
    plan = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="trialing")
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    ai_queries_limit = Column(Integer, nullable=False, default=50)
    locations_limit = Column(Integer, nullable=False, default=1)
    team_members_limit = Column(Integer, nullable=False, default=1)
    pos_integrations_limit = Column(Integer, nullable=False, default=0)
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_subscriptions_business", "business_id", unique=True),
    )


class SubscriptionUsage(Base):
    __tablename__ = "subscription_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    usage_date = Column(Date, nullable=False)
    ai_queries_used = Column(Integer, default=0)
    decisions_applied = Column(Integer, default=0)
    notifications_sent = Column(Integer, default=0)
    llm_prompt_tokens = Column(Integer, default=0)
    llm_completion_tokens = Column(Integer, default=0)
    estimated_cost_cents = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("subscription_id", "usage_date", name="uq_subscription_usage_date"),
    )


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)
    stripe_event_id = Column(String, unique=True, nullable=True)
    amount_cents = Column(Integer, nullable=True)
    currency = Column(String(3), default="SAR")
    payload = Column(JSON, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_billing_events_business", "business_id"),
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="staff")
    permissions = Column(JSON, default=[])
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_team_members_business", "business_id"),
        Index("idx_team_members_organization", "organization_id"),
        Index("idx_team_members_user", "user_id"),
    )


class PermissionDefinition(Base):
    __tablename__ = "permission_definitions"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String, nullable=True)
    category = Column(String(30), nullable=False)
    requires_plan = Column(String(20), default="free")


class TeamInvitation(Base):
    __tablename__ = "team_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    role = Column(String(20), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_team_invitations_token", "token"),
    )


class POSConnection(Base):
    __tablename__ = "pos_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    adapter_type = Column(String(20), nullable=False)
    connection_name = Column(String(100), nullable=False)
    credentials_encrypted = Column(LargeBinary, nullable=False)
    credentials_version = Column(Integer, default=1)
    endpoint_url = Column(String, nullable=True)
    sync_interval_minutes = Column(Integer, default=15)
    sync_sales = Column(Boolean, default=True)
    sync_inventory = Column(Boolean, default=True)
    push_orders = Column(Boolean, default=False)
    sync_status = Column(String(20), default="never_synced")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_duration_seconds = Column(Integer, nullable=True)
    last_sync_records_processed = Column(Integer, nullable=True)
    last_sync_error = Column(String, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    field_mapping = Column(JSON, default={})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pos_connections_business", "business_id"),
    )


class WebhookEvent(Base):
    """Audit trail for every inbound webhook. Supports replay and forensic debugging."""
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=True)
    external_event_id = Column(String(255), nullable=True)
    signature_valid = Column(Boolean, nullable=False, default=False)
    payload_hash = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(30), nullable=False, default="received")
    error = Column(String, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_webhook_events_business_created", "business_id", "created_at"),
        Index("idx_webhook_events_status", "status", "created_at"),
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_events_provider_external_id"),
    )


class POSSyncLog(Base):
    __tablename__ = "pos_sync_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("pos_connections.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False)
    records_fetched = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    errors = Column(JSON, default=[])
    raw_response_sample = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_pos_sync_logs_connection", "connection_id", "started_at"),
    )


class EnabledModule(Base):
    __tablename__ = "enabled_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    module_type = Column(String(20), nullable=False)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default={})
    features_enabled = Column(JSON, default=[])
    enabled_at = Column(DateTime(timezone=True), server_default=func.now())
    enabled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("business_id", "module_type", name="uq_enabled_modules_business_type"),
    )


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    apply_to_all = Column(Boolean, default=False)
    rule_type = Column(String(20), nullable=False)
    rule_name = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False)
    min_price = Column(Numeric(12, 2), nullable=True)
    max_price = Column(Numeric(12, 2), nullable=True)
    min_margin_percent = Column(Numeric(5, 2), default=10)
    max_adjustment_percent = Column(Numeric(5, 2), default=25)
    active_from = Column(DateTime(timezone=True), nullable=True)
    active_to = Column(DateTime(timezone=True), nullable=True)
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pricing_rules_business", "business_id"),
        Index("idx_pricing_rules_item", "item_id"),
    )


class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    current_price = Column(Numeric(12, 2), nullable=False)
    current_margin_percent = Column(Numeric(5, 2), nullable=True)
    recommended_price = Column(Numeric(12, 2), nullable=False)
    recommended_margin_percent = Column(Numeric(5, 2), nullable=True)
    expected_demand_change_percent = Column(Numeric(5, 2), nullable=True)
    expected_revenue_change = Column(Numeric(12, 2), nullable=True)
    expected_profit_change = Column(Numeric(12, 2), nullable=True)
    reasoning = Column(String, nullable=False)
    factors = Column(JSON, nullable=False)
    confidence = Column(Numeric(4, 2), nullable=False)
    status = Column(String(20), default="pending")
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_pricing_recommendations_business", "business_id"),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    whatsapp_enabled = Column(Boolean, default=True)
    whatsapp_number = Column(String(20), nullable=True)
    email_enabled = Column(Boolean, default=True)
    email_address = Column(String(255), nullable=True)
    sms_enabled = Column(Boolean, default=False)
    sms_number = Column(String(20), nullable=True)
    in_app_enabled = Column(Boolean, default=True)
    push_enabled = Column(Boolean, default=False)
    push_token = Column(String, nullable=True)
    alert_preferences = Column(JSON, default={})
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(Time, default="22:00")
    quiet_hours_end = Column(Time, default="07:00")
    max_whatsapp_per_day = Column(Integer, default=10)
    max_sms_per_day = Column(Integer, default=5)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "business_id", name="uq_notification_preferences_user_business"),
        Index("idx_notification_preferences_business", "business_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(String, nullable=False)
    body_html = Column(String, nullable=True)
    notification_type = Column(String(50), nullable=False)
    priority = Column(String(20), nullable=False, default="medium")
    channel = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)
    external_id = Column(String, nullable=True)
    action_url = Column(String, nullable=True)
    action_data = Column(JSON, nullable=True)
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_notifications_user", "user_id", "created_at"),
        Index("idx_notifications_business", "business_id"),
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String(30), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    parameters = Column(JSON, nullable=False, default={})
    status = Column(String(20), nullable=False, default="queued")
    format = Column(String(10), nullable=False, default="pdf")
    file_url = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    page_count = Column(Integer, nullable=True)
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    generation_time_seconds = Column(Integer, nullable=True)
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    is_scheduled = Column(Boolean, default=False)
    schedule_cron = Column(String(100), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    shared_with = Column(JSON, default=[])
    is_public = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_reports_business", "business_id"),
    )


class ExecutedAction(Base):
    __tablename__ = "executed_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("decision_log.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(20), nullable=False)
    action_type = Column(String(30), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    previous_state = Column(JSON, nullable=False)
    new_state = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    executed_at = Column(DateTime(timezone=True), nullable=True)
    executed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    external_actions = Column(JSON, default=[])
    is_reversible = Column(Boolean, default=True)
    is_reversed = Column(Boolean, default=False)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reversed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reversal_reason = Column(String, nullable=True)
    outcome = Column(JSON, nullable=True)
    outcome_computed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_executed_actions_business", "business_id"),
        Index("idx_executed_actions_decision", "decision_id"),
        Index("idx_executed_actions_entity", "entity_type", "entity_id"),
    )


class DeletionRequest(Base):
    """GDPR / PDPL erasure requests with a mandatory grace period."""
    __tablename__ = "deletion_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_purge_at = Column(DateTime(timezone=True), nullable=False)
    purged_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="pending")
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_deletion_requests_status_purge", "status", "scheduled_purge_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), nullable=False)
    organization_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(30), nullable=True)
    action_type = Column(String(100), nullable=False)
    action_category = Column(String(30), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    entity_name = Column(String(255), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    request_id = Column(UUID(as_uuid=True), nullable=True)
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_audit_log_business", "business_id", "created_at"),
        Index("idx_audit_log_user", "user_id", "created_at"),
        Index("idx_audit_log_action", "action_type", "created_at"),
    )


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    analytics_type = Column(String(50), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    results = Column(JSON, nullable=False)
    computation_time_ms = Column(Integer, nullable=True)
    records_analyzed = Column(Integer, nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "analytics_type", "period_start", "period_end", name="uq_analytics_cache_key"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# NAZM AGENT OS – v1.5 – KSA
# Universal – Pharmacy first, then Food, then Auto Parts
# ═══════════════════════════════════════════════════════════════════════════

class AgentActionStatus(str, PyEnum):
    INFO_ONLY = "info_only"
    PENDING_APPROVAL = "pending_approval"
    AUTO_EXECUTED = "auto_executed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class AgentActionType(str, PyEnum):
    RESTOCK = "restock"
    PRICING_INCREASE = "pricing_increase"
    PRICING_DECREASE = "pricing_decrease"
    CASH_ALERT = "cash_alert"
    STAFF_SCHEDULE = "staff_schedule"
    EXPIRY_ALERT = "expiry_alert"
    SUPPLIER_SWITCH = "supplier_switch"


class AgentAction(Base):
    """Nazm attention feed – every agentic decision goes here first"""
    __tablename__ = "agent_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default="pending_approval")
    
    # Ranking
    confidence = Column(Numeric(4, 2), nullable=False)  # 0.00 - 1.00
    priority = Column(Integer, default=3)  # 1=critical, 5=low
    urgency_score = Column(Numeric(6, 2), nullable=True)
    
    # What
    title = Column(String(255), nullable=False)
    title_ar = Column(String(255), nullable=True)
    summary = Column(String, nullable=False)
    summary_ar = Column(String, nullable=True)
    
    # Payload – structured action data
    # e.g. {"item_id": "...", "item_name": "Almarai Milk", "quantity": 135, "supplier_id": "...", "estimated_cost_sar": 1012, "eta": "2026-07-06"}
    payload = Column(JSON, nullable=False, default={})
    
    # Financial impact
    estimated_value_sar = Column(Numeric(12, 2), nullable=True)
    estimated_savings_sar = Column(Numeric(12, 2), nullable=True)
    
    # Autonomy audit
    autonomy_dial_at_creation = Column(Integer, nullable=False)  # 0-100
    was_auto_executed = Column(Boolean, default=False)
    
    # Approval flow
    expires_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decision_note = Column(String, nullable=True)
    
    # WhatsApp
    whatsapp_message_id = Column(String(255), nullable=True)
    whatsapp_status = Column(String(30), nullable=True)
    
    # Outcome tracking
    applied_at = Column(DateTime(timezone=True), nullable=True)
    outcome_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_agent_actions_business_status", "business_id", "status"),
        Index("idx_agent_actions_created", "created_at"),
    )


class AutonomyPolicy(Base):
    """Per-business, per-action-type autonomy dial – 0 to 100"""
    __tablename__ = "autonomy_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(30), nullable=False)  # restock, pricing_increase, cash_transfer, staff_schedule, expiry_alert
    
    dial = Column(Integer, nullable=False, default=50)  # 0=inform only, 50=draft+approve, 100=auto-execute
    
    # Guardrails
    ceiling_sar = Column(Numeric(12, 2), nullable=True)  # max auto-spend per action
    max_price_increase_pct = Column(Numeric(5, 2), nullable=True)  # default 5%
    max_price_decrease_pct = Column(Numeric(5, 2), nullable=True)  # default 10%
    max_quantity = Column(Numeric(12, 2), nullable=True)
    
    # Timing
    quiet_hours_start = Column(Time, default="22:00")
    quiet_hours_end = Column(Time, default="07:00")
    require_2fa_above_sar = Column(Numeric(12, 2), nullable=True)
    
    # Meta
    is_active = Column(Boolean, default=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "action_type", name="uq_autonomy_business_action"),
        CheckConstraint("dial >= 0 AND dial <= 100", name="autonomy_dial_range"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# SUPPLIER NETWORK – two-sided moat
# ═══════════════════════════════════════════════════════════════════════════

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_ar = Column(String(255), nullable=False)
    name_en = Column(String(255), nullable=False)
    city = Column(String(100), nullable=True)  # Riyadh, Jeddah, Buraidah
    phone = Column(String(20), nullable=True)
    whatsapp_number = Column(String(20), nullable=True)
    
    category = Column(String(50), nullable=True)  # dairy, pharma, food_wholesale, auto_parts
    lead_time_days = Column(Integer, default=2)
    min_order_sar = Column(Numeric(12, 2), default=0)
    delivery_days = Column(String(50), nullable=True)  # "Sat,Mon,Wed"
    
    # Network aggregation – updated nightly
    total_shops_ordering = Column(Integer, default=0)
    total_monthly_volume_sar = Column(Numeric(14, 2), default=0)
    
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_suppliers_city_category", "city", "category"),
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    
    # Link to agent
    agent_action_id = Column(UUID(as_uuid=True), ForeignKey("agent_actions.id"), nullable=True)
    
    po_number = Column(String(50), nullable=True, unique=True)
    status = Column(String(30), default="draft")  # draft, pending_approval, sent, confirmed, received, cancelled
    
    total_sar = Column(Numeric(12, 2), default=0)
    items_json = Column(JSON, nullable=False)  # [{item_id, qty, unit_cost}]
    
    # WhatsApp
    whatsapp_message_id = Column(String(255), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    expected_delivery = Column(Date, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    
    created_by_agent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_po_business", "business_id", "created_at"),
        Index("idx_po_supplier", "supplier_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# RECOVERY MATCH – retailer-to-retailer stock recovery (manual-confirm v1)
# ═══════════════════════════════════════════════════════════════════════════

class RecoveryMatchSettings(Base):
    __tablename__ = "recovery_match_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    is_enabled = Column(Boolean, default=False)
    allow_contact_reveal = Column(Boolean, default=False)
    max_distance_km = Column(Numeric(6, 2), default=5)
    allowed_categories = Column(JSON, nullable=True)
    excluded_categories = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", name="uq_recovery_match_settings_business"),
        Index("idx_recovery_match_settings_enabled", "is_enabled"),
    )


class StockRecoveryListing(Base):
    __tablename__ = "stock_recovery_listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    seller_branch_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)

    sku = Column(String(100), nullable=True)
    barcode = Column(String(100), nullable=True)
    item_name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    quantity_available = Column(Numeric(12, 2), nullable=False)
    unit_cost_sar = Column(Numeric(12, 2), nullable=True)
    asking_price_sar = Column(Numeric(12, 2), nullable=False)
    discount_pct = Column(Numeric(5, 2), nullable=True)
    expiry_date = Column(Date, nullable=True)
    batch_number = Column(String(100), nullable=True)
    storage_type = Column(String(30), nullable=True)
    status = Column(String(30), default="seller_approved")
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("quantity_available > 0", name="stock_recovery_listing_qty_positive"),
        CheckConstraint("asking_price_sar >= 0", name="stock_recovery_listing_price_nonnegative"),
        Index("idx_stock_recovery_listings_seller_status", "seller_business_id", "status"),
        Index("idx_stock_recovery_listings_item", "item_id"),
        Index("idx_stock_recovery_listings_barcode", "barcode"),
    )


class StockRecoveryMatch(Base):
    __tablename__ = "stock_recovery_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("stock_recovery_listings.id", ondelete="CASCADE"), nullable=False)
    buyer_business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    buyer_branch_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True)
    buyer_item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL"), nullable=True)

    match_score = Column(Numeric(5, 2), nullable=False)
    distance_km = Column(Numeric(8, 2), nullable=True)
    buyer_need_qty = Column(Numeric(12, 2), nullable=True)
    buyer_days_left = Column(Numeric(8, 2), nullable=True)
    status = Column(String(30), default="suggested")
    seller_approved_at = Column(DateTime(timezone=True), nullable=True)
    buyer_approved_at = Column(DateTime(timezone=True), nullable=True)
    contact_revealed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    recovered_value_sar = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("listing_id", "buyer_business_id", "buyer_item_id", name="uq_stock_recovery_match_unique_buyer_item"),
        Index("idx_stock_recovery_matches_buyer_status", "buyer_business_id", "status"),
        Index("idx_stock_recovery_matches_listing", "listing_id"),
    )


class StockRecoveryEvent(Base):
    __tablename__ = "stock_recovery_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(UUID(as_uuid=True), ForeignKey("stock_recovery_matches.id", ondelete="CASCADE"), nullable=True)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("stock_recovery_listings.id", ondelete="CASCADE"), nullable=True)
    actor_business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False)
    notes = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_stock_recovery_events_match", "match_id", "created_at"),
        Index("idx_stock_recovery_events_listing", "listing_id", "created_at"),
    )


class MoneyAudit(Base):
    """Founder-reviewable Money Audit generated from merchant sales + inventory files."""
    __tablename__ = "money_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(30), default="generated")  # generated, reviewed, sent, archived
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    money_at_risk_sar = Column(Numeric(14, 2), nullable=False, default=0)
    dead_stock_value_sar = Column(Numeric(14, 2), nullable=False, default=0)
    stockout_risk_value_sar = Column(Numeric(14, 2), nullable=False, default=0)
    margin_leakage_sar = Column(Numeric(14, 2), nullable=False, default=0)
    overstock_value_sar = Column(Numeric(14, 2), nullable=False, default=0)

    money_approved_sar = Column(Numeric(14, 2), nullable=False, default=0)
    money_recovered_sar = Column(Numeric(14, 2), nullable=False, default=0)
    confidence_score = Column(Numeric(5, 2), nullable=False, default=0)
    data_quality_score = Column(Numeric(5, 2), nullable=False, default=0)

    missing_data = Column(JSON, nullable=True)
    summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_money_audits_business_created", "business_id", "created_at"),
        Index("idx_money_audits_status", "status"),
    )


class FeatureFlag(Base):
    """Dynamic feature flags for per-business / per-plan rollout control."""
    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    # Global default when no business override exists.
    default_value = Column(Boolean, default=False, nullable=False)
    # Optional plan gating: comma-separated plan names, e.g. "basic,pro,enterprise".
    allowed_plans = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_feature_flags_key", "key"),
    )


class FeatureFlagOverride(Base):
    """Per-business feature flag override."""
    __tablename__ = "feature_flag_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_flag_id = Column(UUID(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    value = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("feature_flag_id", "business_id", name="uq_feature_flag_business"),
        Index("idx_feature_flag_overrides_business", "business_id"),
    )


class IdempotencyKey(Base):
    """Cached responses for idempotent POST/PATCH/PUT requests."""
    __tablename__ = "idempotency_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    scope_method = Column(String(10), nullable=False)
    scope_path = Column(String(500), nullable=False)
    request_hash = Column(String(64), nullable=True)
    response_status = Column(Integer, nullable=False)
    response_body = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "business_id", "idempotency_key", "scope_method", "scope_path",
            name="uq_idempotency_scope",
        ),
        Index(
            "idx_idempotency_key_lookup",
            "business_id", "idempotency_key", "scope_method", "scope_path",
        ),
        Index("idx_idempotency_expires", "expires_at"),
    )


class MoneyAuditAction(Base):
    """Approval-ready recovery action from a Money Audit."""
    __tablename__ = "money_audit_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id = Column(UUID(as_uuid=True), ForeignKey("money_audits.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL"), nullable=True)

    action_type = Column(String(40), nullable=False)  # discount, reorder, margin_fix, recovery_match, review
    priority = Column(Integer, default=3)
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    expected_recovery_sar = Column(Numeric(14, 2), nullable=False, default=0)
    quantity = Column(Numeric(12, 2), nullable=True)
    recommended_discount_pct = Column(Numeric(5, 2), nullable=True)

    status = Column(String(30), default="suggested")  # suggested, approved, rejected, completed
    approval_channel = Column(String(30), nullable=True)  # dashboard, whatsapp_manual, whatsapp_api
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_value_sar = Column(Numeric(14, 2), nullable=True)
    notes = Column(String, nullable=True)
    evidence = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_money_audit_actions_audit", "audit_id"),
        Index("idx_money_audit_actions_business_status", "business_id", "status"),
        Index("idx_money_audit_actions_item", "item_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# VERTICAL MODULES – Pharmacy FIRST
# ═══════════════════════════════════════════════════════════════════════════

class PharmacyLot(Base):
    """FEFO inventory – expiry tracking – SFDA compliant"""
    __tablename__ = "pharmacy_lots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    
    batch_number = Column(String(100), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    cost_per_unit = Column(Numeric(12, 2), nullable=True)
    
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Auto-calculated
    days_to_expiry = Column(Integer, nullable=True)
    is_expired = Column(Boolean, default=False)
    is_near_expiry = Column(Boolean, default=False)  # < 90 days
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_pharmacy_lots_expiry", "business_id", "expiry_date"),
        Index("idx_pharmacy_lots_item", "item_id"),
    )


class SFDARecall(Base):
    """SFDA drug recall feed – auto-matched against inventory"""
    __tablename__ = "sfda_recalls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drug_code = Column(String(100), nullable=False, index=True)  # SFDA / GTIN
    drug_name_ar = Column(String(255), nullable=True)
    drug_name_en = Column(String(255), nullable=True)
    
    recall_date = Column(Date, nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high, critical
    reason = Column(String, nullable=True)
    action_required = Column(String, nullable=True)
    
    source_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_sfda_code", "drug_code"),
    )


# Food / Cafe – Recipe BOM – Module 2 – tables exist, UI gated OFF
class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    menu_item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(255), nullable=False)
    yield_qty = Column(Numeric(10, 2), default=1)  # e.g. 1 shawarma sandwich
    yield_unit = Column(String(20), default="piece")
    
    # ingredients: [{item_id: "chicken_breast", qty: 0.15, unit: "kg"}, ...]
    ingredients_json = Column(JSON, nullable=False)
    
    # Auto-calculated
    total_cogs_sar = Column(Numeric(12, 2), nullable=True)
    target_margin_pct = Column(Numeric(5, 2), default=40)
    last_cost_update = Column(DateTime(timezone=True), nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "menu_item_id", name="uq_recipe_menu_item"),
    )


# Auto Parts – Module 3 – tables exist, UI gated OFF
class PartCompatibility(Base):
    __tablename__ = "parts_compatibility"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    
    make = Column(String(50), nullable=False)  # Toyota, Hyundai, Nissan
    model = Column(String(100), nullable=False)
    year_from = Column(Integer, nullable=True)
    year_to = Column(Integer, nullable=True)
    engine_code = Column(String(50), nullable=True)
    oem_number = Column(String(100), nullable=True)
    
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_parts_make_model", "make", "model"),
        Index("idx_parts_oem", "oem_number"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 3: Context & Temporal Reasoning Engine
# ═══════════════════════════════════════════════════════════════════════════

class BusinessContext(Base):
    """External context attached to business events (weather, holidays, regs, …)."""
    __tablename__ = "business_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    context_type = Column(String(50), nullable=False)  # holiday, weather, prayer_time, inflation, regulation, competitor, …
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_until = Column(DateTime(timezone=True), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    confidence = Column(Numeric(4, 3), nullable=False, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_business_context_business_type", "business_id", "context_type"),
        Index("idx_business_context_effective", "business_id", "effective_from", "effective_until"),
    )


class EventDerivation(Base):
    """Causal links between events for temporal reasoning / explainability."""
    __tablename__ = "event_derivations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    cause_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    effect_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    derivation_type = Column(String(50), nullable=False)  # caused_by, correlated_with, followed_by
    confidence = Column(Numeric(4, 3), nullable=False, default=0.5)
    evidence = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "cause_event_id", "effect_event_id", "derivation_type", name="uq_event_derivation"),
        Index("idx_event_derivations_effect", "effect_event_id"),
        Index("idx_event_derivations_cause", "cause_event_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 5: Agents, Planning, Simulation, Execution
# ═══════════════════════════════════════════════════════════════════════════

class PlanStatus(str, PyEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Plan(Base):
    """Goal-driven plan produced by the Planning Engine."""
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    goal = Column(String(500), nullable=False)
    steps = Column(JSON, nullable=False, default=list)  # ordered JSONB steps
    estimated_roi = Column(Numeric(12, 2), nullable=True)
    estimated_cost = Column(Numeric(12, 2), nullable=True)
    estimated_duration_hours = Column(Numeric(8, 2), nullable=True)
    simulation_id = Column(UUID(as_uuid=True), ForeignKey("simulations.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), nullable=False, default="draft")
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_plans_business_status", "business_id", "status"),
        Index("idx_plans_business_created", "business_id", "created_at"),
    )


class SimulationStatus(str, PyEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Simulation(Base):
    """What-if simulation run against a copy of business memory."""
    __tablename__ = "simulations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    scenario = Column(JSON, nullable=False, default=dict)
    assumptions = Column(JSON, nullable=False, default=dict)
    results = Column(JSON, nullable=True)
    status = Column(String(30), nullable=False, default="draft")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_simulations_business_status", "business_id", "status"),
        Index("idx_simulations_business_created", "business_id", "created_at"),
    )


class ExecutionJobStatus(str, PyEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ExecutionJob(Base):
    """Tracks every action sent to an external system by the Execution Engine."""
    __tablename__ = "execution_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("intelligence_decisions.id", ondelete="SET NULL"), nullable=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    external_reference = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    result = Column(JSON, nullable=True)
    error = Column(String, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rollback_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_execution_jobs_business_status", "business_id", "status"),
        Index("idx_execution_jobs_decision", "decision_id"),
        Index("idx_execution_jobs_plan", "plan_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 4: Decision & Explainability Engine
# ═══════════════════════════════════════════════════════════════════════════

class DecisionStatus(str, PyEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class IntelligenceDecision(Base):
    """Ranked, auditable decision produced by the Decision Engine."""
    __tablename__ = "intelligence_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    decision_type = Column(String(50), nullable=False)  # restock, pricing, discount, supplier_switch, cash_alert, …
    input_event_ids = Column(JSON, nullable=False, default=list)
    rules_applied = Column(JSON, nullable=False, default=list)
    memory_snapshot = Column(JSON, nullable=True)
    graph_evidence = Column(JSON, nullable=True)
    context_evidence = Column(JSON, nullable=True)
    candidate_actions = Column(JSON, nullable=False, default=list)
    ranked_action = Column(JSON, nullable=True)
    confidence = Column(Numeric(4, 3), nullable=False, default=0.0)
    expected_roi = Column(Numeric(12, 2), nullable=True)
    risk_score = Column(Numeric(4, 3), nullable=False, default=0.0)
    urgency = Column(Numeric(4, 3), nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="draft")
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    explanation = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_intelligence_decisions_business", "business_id", "created_at"),
        Index("idx_intelligence_decisions_status", "business_id", "status"),
        Index("idx_intelligence_decisions_type", "business_id", "decision_type"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 6: Learning Engine
# ═══════════════════════════════════════════════════════════════════════════

class FeedbackSource(str, PyEnum):
    MANUAL = "manual"
    SYSTEM = "system"


class OutcomeFeedback(Base):
    """Feedback loop comparing predicted vs actual outcomes of intelligence decisions."""
    __tablename__ = "outcome_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("intelligence_decisions.id", ondelete="SET NULL"), nullable=True)
    execution_job_id = Column(UUID(as_uuid=True), ForeignKey("execution_jobs.id", ondelete="SET NULL"), nullable=True)
    decision_type = Column(String(50), nullable=True)
    predicted_outcome = Column(JSON, nullable=False, default=dict)
    actual_outcome = Column(JSON, nullable=False, default=dict)
    delta = Column(JSON, nullable=False, default=dict)
    feedback_source = Column(String(20), nullable=False, default=FeedbackSource.MANUAL.value)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_outcome_feedback_business_type", "business_id", "decision_type"),
        Index("idx_outcome_feedback_decision", "decision_id"),
        Index("idx_outcome_feedback_recorded", "business_id", "recorded_at"),
    )


class ModelPerformance(Base):
    """Per-business, per-decision-type accuracy and ROI error tracked by the Learning Engine."""
    __tablename__ = "model_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    decision_type = Column(String(50), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    samples = Column(Integer, nullable=False, default=0)
    accuracy = Column(Numeric(5, 4), nullable=True)
    roi_error = Column(Numeric(12, 4), nullable=True)
    mean_latency_ms = Column(Numeric(10, 2), nullable=True)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "decision_type", "window_start", name="uq_model_performance_window"),
        Index("idx_model_performance_business_type", "business_id", "decision_type"),
        Index("idx_model_performance_window", "business_id", "decision_type", "window_start", "window_end"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 2: Knowledge Graph Engine
# ═══════════════════════════════════════════════════════════════════════════

class GraphEntity(Base):
    """Node in the business knowledge graph.

    Storage is relational PostgreSQL first; the abstraction is kept generic so
    Apache AGE or Neo4j can be swapped in later without changing consumers.
    """
    __tablename__ = "graph_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(50), nullable=False)  # supplier, product, branch, employee, customer, …
    external_id = Column(String(255), nullable=True)  # POS-specific reference
    name = Column(String(255), nullable=False)
    attributes = Column(JSON, nullable=False, default=dict)
    # Optional embedding stored as JSON array; migrate to pgvector when scale demands.
    vector = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "entity_type", "external_id", name="uq_graph_entity_business_type_ext"),
        Index("idx_graph_entities_business_type", "business_id", "entity_type"),
        Index("idx_graph_entities_name", "business_id", "name"),
    )


class GraphRelationship(Base):
    """Edge in the business knowledge graph with evidence and temporal validity."""
    __tablename__ = "graph_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("graph_entities.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50), nullable=False)  # SUPPLIES, SOLD_MOSTLY_AT, MANAGES, WORKS_AT, …
    strength = Column(Numeric(4, 3), nullable=False, default=0.5)  # 0–1
    evidence_event_ids = Column(JSON, nullable=False, default=list)
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "source_id", "target_id", "relation_type", name="uq_graph_relationship_edge"),
        Index("idx_graph_relationships_source", "source_id"),
        Index("idx_graph_relationships_target", "target_id"),
        Index("idx_graph_relationships_business_type", "business_id", "relation_type"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 1: Business Memory Engine
# ═══════════════════════════════════════════════════════════════════════════

class MemoryType(str, PyEnum):
    """Supported business memory document types."""
    CURRENT_STATE = "current_state"
    FORECASTS = "forecasts"
    GOALS = "goals"
    PATTERNS = "patterns"
    SEASONALITY = "seasonality"
    FAILURES = "failures"
    RELATIONSHIPS = "relationships"


class BusinessMemory(Base):
    """Living, queryable projection of business state derived from the event stream.

    One JSONB document per business + memory_type. Projectors are idempotent and
    update this table in response to events.
    """
    __tablename__ = "business_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    memory_type = Column(String(50), nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=0)  # optimistic counter for replay detection
    updated_by_event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("business_id", "memory_type", name="uq_business_memory_business_type"),
        Index("idx_business_memory_business_type", "business_id", "memory_type"),
        Index("idx_business_memory_updated", "business_id", "updated_at"),
    )


class MemoryUpdate(Base):
    """Audit log of every mutation to a business memory document."""
    __tablename__ = "memory_updates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    memory_type = Column(String(50), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    path = Column(String(500), nullable=False)  # dot-notation path, e.g. "inventory.item_abc.stock"
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_memory_updates_business_type", "business_id", "memory_type"),
        Index("idx_memory_updates_event", "event_id"),
        Index("idx_memory_updates_occurred", "business_id", "occurred_at"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER – Phase 0: Universal Event Engine
# ═══════════════════════════════════════════════════════════════════════════

class EventType(Base):
    """Registry of supported business event types and their schemas."""
    __tablename__ = "event_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    description = Column(String, nullable=True)
    schema = Column(JSON, nullable=False, default={})
    example = Column(JSON, nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def json_schema(self) -> dict:
        """Alias for ``schema`` so Pydantic models can avoid shadowing BaseModel.schema."""
        return self.schema or {}


class EventSubscription(Base):
    """Consumer subscriptions for the event bus."""
    __tablename__ = "event_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True)
    consumer_name = Column(String(100), nullable=False)
    event_pattern = Column(String(255), nullable=False)  # e.g. "sale.*", "inventory.changed"
    queue_or_channel = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_event_subscriptions_pattern", "event_pattern"),
        Index("idx_event_subscriptions_business", "business_id"),
    )


class Event(Base):
    """Append-only business event stream. The backbone of the intelligence layer."""
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(100), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    source = Column(String(50), nullable=False)  # foodics, salla, csv, manual, api, etc.
    source_id = Column(String(255), nullable=True)  # external reference id
    payload = Column(JSON, nullable=False)
    context_snapshot = Column(JSON, nullable=True)
    actor_type = Column(String(50), nullable=True)  # user, system, webhook, agent
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    causation_id = Column(UUID(as_uuid=True), nullable=True)
    checksum = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_events_business_occurred", "business_id", "occurred_at"),
        Index("idx_events_business_type", "business_id", "event_type"),
        Index("idx_events_source_source_id", "source", "source_id"),
        UniqueConstraint("business_id", "source", "source_id", "checksum", name="uq_events_dedupe"),
    )


class PartnerStatus(str, PyEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class PartnerType(str, PyEnum):
    ACCOUNTANT = "accountant"
    ADVISOR = "advisor"
    CONSULTANT = "consultant"
    AUDITOR = "auditor"
    FINTECH = "fintech"


class ReferralStatus(str, PyEnum):
    LEAD = "lead"
    CONVERTED = "converted"
    CHURNED = "churned"


class Partner(Base):
    """Accountant / Monshaat advisor / fintech partner program member."""
    __tablename__ = "partners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    partner_type = Column(String(30), nullable=False)
    status = Column(String(30), default="pending")

    name = Column(String(255), nullable=False)
    name_ar = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    cr_number = Column(String(20), nullable=True)
    monshaat_certified = Column(Boolean, default=False)

    referral_code = Column(String(50), unique=True, nullable=False, index=True)
    commission_pct = Column(Numeric(5, 2), default=Decimal("10.00"))
    total_referrals = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)
    total_revenue_sar = Column(Numeric(14, 2), default=0)
    payout_due_sar = Column(Numeric(14, 2), default=0)
    bank_iban = Column(String(50), nullable=True)

    notes = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("partner_type IN ('accountant', 'advisor', 'consultant', 'auditor', 'fintech')", name="partner_type_check"),
        CheckConstraint("status IN ('pending', 'active', 'suspended')", name="partner_status_check"),
        Index("idx_partners_status", "status"),
        Index("idx_partners_city", "city"),
    )


class PartnerReferral(Base):
    """Merchant referred by a partner. Tracked for payout and program analytics."""
    __tablename__ = "partner_referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True)

    merchant_name = Column(String(255), nullable=False)
    merchant_email = Column(String(255), nullable=True)
    merchant_phone = Column(String(20), nullable=True)
    estimated_arr_sar = Column(Numeric(12, 2), nullable=True)
    status = Column(String(30), default="lead")

    converted_at = Column(DateTime(timezone=True), nullable=True)
    churned_at = Column(DateTime(timezone=True), nullable=True)
    payout_sar = Column(Numeric(12, 2), nullable=True)
    payout_paid_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('lead', 'converted', 'churned')", name="referral_status_check"),
        Index("idx_partner_referrals_partner", "partner_id", "created_at"),
        Index("idx_partner_referrals_status", "status"),
    )
