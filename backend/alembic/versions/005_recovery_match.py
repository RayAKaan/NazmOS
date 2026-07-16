"""Recovery Match schema

Revision ID: 005
Revises: 004
Create Date: 2026-07-06

Adds retailer-to-retailer recovery matching tables and item identity fields.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("barcode", sa.String(100), nullable=True))
    op.add_column("items", sa.Column("brand", sa.String(100), nullable=True))
    op.add_column("items", sa.Column("pack_size", sa.String(50), nullable=True))
    op.add_column("items", sa.Column("storage_type", sa.String(30), nullable=True))
    op.create_index("idx_item_barcode", "items", ["barcode"])

    op.create_table(
        "recovery_match_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, server_default="false"),
        sa.Column("allow_contact_reveal", sa.Boolean, server_default="false"),
        sa.Column("max_distance_km", sa.Numeric(6, 2), server_default="5"),
        sa.Column("allowed_categories", postgresql.JSONB, nullable=True),
        sa.Column("excluded_categories", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("business_id", name="uq_recovery_match_settings_business"),
    )
    op.create_index("idx_recovery_match_settings_enabled", "recovery_match_settings", ["is_enabled"])

    op.create_table(
        "stock_recovery_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("seller_business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("quantity_available", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_cost_sar", sa.Numeric(12, 2), nullable=True),
        sa.Column("asking_price_sar", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("batch_number", sa.String(100), nullable=True),
        sa.Column("storage_type", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), server_default="seller_approved"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity_available > 0", name="stock_recovery_listing_qty_positive"),
        sa.CheckConstraint("asking_price_sar >= 0", name="stock_recovery_listing_price_nonnegative"),
    )
    op.create_index("idx_stock_recovery_listings_seller_status", "stock_recovery_listings", ["seller_business_id", "status"])
    op.create_index("idx_stock_recovery_listings_item", "stock_recovery_listings", ["item_id"])
    op.create_index("idx_stock_recovery_listings_barcode", "stock_recovery_listings", ["barcode"])

    op.create_table(
        "stock_recovery_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_recovery_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buyer_branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("buyer_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("distance_km", sa.Numeric(8, 2), nullable=True),
        sa.Column("buyer_need_qty", sa.Numeric(12, 2), nullable=True),
        sa.Column("buyer_days_left", sa.Numeric(8, 2), nullable=True),
        sa.Column("status", sa.String(30), server_default="suggested"),
        sa.Column("seller_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buyer_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovered_value_sar", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("listing_id", "buyer_business_id", "buyer_item_id", name="uq_stock_recovery_match_unique_buyer_item"),
    )
    op.create_index("idx_stock_recovery_matches_buyer_status", "stock_recovery_matches", ["buyer_business_id", "status"])
    op.create_index("idx_stock_recovery_matches_listing", "stock_recovery_matches", ["listing_id"])

    op.create_table(
        "stock_recovery_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_recovery_matches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_recovery_listings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("actor_business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_stock_recovery_events_match", "stock_recovery_events", ["match_id", "created_at"])
    op.create_index("idx_stock_recovery_events_listing", "stock_recovery_events", ["listing_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_stock_recovery_events_listing", table_name="stock_recovery_events")
    op.drop_index("idx_stock_recovery_events_match", table_name="stock_recovery_events")
    op.drop_table("stock_recovery_events")
    op.drop_index("idx_stock_recovery_matches_listing", table_name="stock_recovery_matches")
    op.drop_index("idx_stock_recovery_matches_buyer_status", table_name="stock_recovery_matches")
    op.drop_table("stock_recovery_matches")
    op.drop_index("idx_stock_recovery_listings_barcode", table_name="stock_recovery_listings")
    op.drop_index("idx_stock_recovery_listings_item", table_name="stock_recovery_listings")
    op.drop_index("idx_stock_recovery_listings_seller_status", table_name="stock_recovery_listings")
    op.drop_table("stock_recovery_listings")
    op.drop_index("idx_recovery_match_settings_enabled", table_name="recovery_match_settings")
    op.drop_table("recovery_match_settings")
    op.drop_index("idx_item_barcode", table_name="items")
    op.drop_column("items", "storage_type")
    op.drop_column("items", "pack_size")
    op.drop_column("items", "brand")
    op.drop_column("items", "barcode")
