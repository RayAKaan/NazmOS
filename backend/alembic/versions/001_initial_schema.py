"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('role', sa.String(20), default='owner'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_user_email', 'users', ['email'])
    
    op.create_table(
        'businesses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('address', sa.Text, nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('currency', sa.String(3), default='INR'),
        sa.Column('timezone', sa.String(50), default='Asia/Kolkata'),
        sa.Column('is_demo', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_business_owner', 'businesses', ['owner_id'])
    
    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('sort_order', sa.Numeric(10, 0), default=0),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('business_id', 'name', name='uq_category_business_name'),
    )
    op.create_index('idx_category_business', 'categories', ['business_id'])
    
    op.create_table(
        'items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(50), default='piece'),
        sa.Column('cost_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('sell_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('tax_rate', sa.Numeric(5, 2), default=0),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_item_business', 'items', ['business_id'])
    op.create_index('idx_item_category', 'items', ['category_id'])
    op.create_index('idx_item_sku', 'items', ['sku'])
    
    op.create_table(
        'inventory',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('current_stock', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('reorder_level', sa.Numeric(12, 2), default=10),
        sa.Column('max_stock', sa.Numeric(12, 2), default=100),
        sa.Column('last_restocked', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('business_id', 'item_id', name='uq_inventory_business_item'),
    )
    op.create_index('idx_inventory_business', 'inventory', ['business_id'])
    op.create_index('idx_inventory_item', 'inventory', ['item_id'])
    
    op.create_table(
        'transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='SET NULL'), nullable=True),
        sa.Column('quantity', sa.Numeric(12, 2), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('cost_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('profit', sa.Numeric(12, 2), nullable=False),
        sa.Column('transaction_type', sa.String(20), default='sale'),
        sa.Column('payment_method', sa.String(20), default='cash'),
        sa.Column('transaction_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('idx_transaction_business', 'transactions', ['business_id'])
    op.create_index('idx_transaction_item', 'transactions', ['item_id'])
    op.create_index('idx_transaction_business_date', 'transactions', ['business_id', 'transaction_at'])
    op.create_index('idx_transaction_date', 'transactions', ['transaction_at'])
    
    op.create_table(
        'daily_summaries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('business_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_sales', sa.Numeric(12, 2), default=0),
        sa.Column('total_profit', sa.Numeric(12, 2), default=0),
        sa.Column('total_transactions', sa.Numeric(10, 0), default=0),
        sa.Column('top_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id'), nullable=True),
        sa.Column('top_item_qty', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.UniqueConstraint('business_id', 'date', name='uq_daily_summary_business_date'),
    )
    op.create_index('idx_daily_summary_business_date', 'daily_summaries', ['business_id', 'date'])


def downgrade() -> None:
    op.drop_table('daily_summaries')
    op.drop_table('transactions')
    op.drop_table('inventory')
    op.drop_table('items')
    op.drop_table('categories')
    op.drop_table('businesses')
    op.drop_table('users')
