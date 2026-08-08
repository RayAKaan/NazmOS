"""Add partner program tables.

Revision ID: e8a1b2c3d4e5
Revises: d3e7a8c9b10e
Create Date: 2026-08-08 00:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.database.types import UUID


revision: str = 'e8a1b2c3d4e5'
down_revision: Union[str, None] = 'd3e7a8c9b10e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'partners',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('partner_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(30), default='pending'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('name_ar', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('cr_number', sa.String(20), nullable=True),
        sa.Column('monshaat_certified', sa.Boolean, default=False),
        sa.Column('referral_code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('commission_pct', sa.Numeric(5, 2), default=10.00),
        sa.Column('total_referrals', sa.Integer, default=0),
        sa.Column('total_converted', sa.Integer, default=0),
        sa.Column('total_revenue_sar', sa.Numeric(14, 2), default=0),
        sa.Column('payout_due_sar', sa.Numeric(14, 2), default=0),
        sa.Column('bank_iban', sa.String(50), nullable=True),
        sa.Column('notes', sa.String, nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("partner_type IN ('accountant', 'advisor', 'consultant', 'auditor', 'fintech')", name='partner_type_check'),
        sa.CheckConstraint("status IN ('pending', 'active', 'suspended')", name='partner_status_check'),
        sa.Index('idx_partners_status', 'status'),
        sa.Index('idx_partners_city', 'city'),
    )

    op.create_table(
        'partner_referrals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('partner_id', UUID(as_uuid=True), sa.ForeignKey('partners.id', ondelete='CASCADE'), nullable=False),
        sa.Column('business_id', UUID(as_uuid=True), sa.ForeignKey('businesses.id', ondelete='SET NULL'), nullable=True),
        sa.Column('merchant_name', sa.String(255), nullable=False),
        sa.Column('merchant_email', sa.String(255), nullable=True),
        sa.Column('merchant_phone', sa.String(20), nullable=True),
        sa.Column('estimated_arr_sar', sa.Numeric(12, 2), nullable=True),
        sa.Column('status', sa.String(30), default='lead'),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('churned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payout_sar', sa.Numeric(12, 2), nullable=True),
        sa.Column('payout_paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.String, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("status IN ('lead', 'converted', 'churned')", name='referral_status_check'),
        sa.Index('idx_partner_referrals_partner', 'partner_id', 'created_at'),
        sa.Index('idx_partner_referrals_status', 'status'),
    )


def downgrade() -> None:
    op.drop_table('partner_referrals')
    op.drop_table('partners')
