"""Recovery intelligence financial model and upload reconciliation.

Revision: rec_intel_v2_0824
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "rec_intel_v2_0824"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand transaction classifications so returns/adjustments are explicit.
    op.drop_constraint("transaction_type_check", "transactions", type_="check")
    op.create_check_constraint(
        "transaction_type_check", "transactions",
        "transaction_type IN ('sale', 'return', 'refund', 'waste', 'adjustment', 'transfer')",
    )

    # Keep legacy columns for compatibility; new fields are the canonical model.
    for name in [
        "inventory_value_sar", "capital_at_risk_sar", "revenue_at_risk_sar",
        "gross_profit_at_risk_sar", "recoverable_value_low_sar",
        "recoverable_value_high_sar", "expected_recovery_sar",
    ]:
        op.add_column("money_audits", sa.Column(name, sa.Numeric(14, 2), nullable=True))

    op.add_column("money_audits", sa.Column("financial_model_version", sa.String(30), nullable=False, server_default="v2"))
    op.add_column("money_audits", sa.Column("recovery_confidence", sa.String(24), nullable=False, server_default="INSUFFICIENT DATA"))
    op.add_column("money_audits", sa.Column("evidence_summary", sa.JSON(), nullable=True))

    op.add_column("money_audit_actions", sa.Column("recoverable_value_low_sar", sa.Numeric(14, 2), nullable=True))
    op.add_column("money_audit_actions", sa.Column("recoverable_value_high_sar", sa.Numeric(14, 2), nullable=True))
    op.add_column("money_audit_actions", sa.Column("expected_recovery_sar_v2", sa.Numeric(14, 2), nullable=True))
    op.add_column("money_audit_actions", sa.Column("recovery_confidence", sa.String(24), nullable=False, server_default="INSUFFICIENT DATA"))
    op.add_column("money_audit_actions", sa.Column("financial_model", sa.JSON(), nullable=True))
    op.add_column("money_audit_actions", sa.Column("measurement_window_days", sa.Integer(), nullable=True))
    op.add_column("money_audit_actions", sa.Column("prediction_error_pct", sa.Numeric(8, 2), nullable=True))

    op.add_column("uploaded_files", sa.Column("rows_rejected", sa.JSON(), nullable=True))
    op.add_column("uploaded_files", sa.Column("data_quality_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("uploaded_files", sa.Column("data_quality_report", sa.JSON(), nullable=True))
    op.add_column("uploaded_files", sa.Column("row_count_received", sa.BigInteger(), nullable=True))
    op.add_column("uploaded_files", sa.Column("row_count_rejected", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_constraint("transaction_type_check", "transactions", type_="check")
    op.create_check_constraint("transaction_type_check", "transactions", "transaction_type IN ('sale', 'return', 'waste')")
    for c in ["row_count_rejected", "row_count_received", "data_quality_report", "data_quality_score", "rows_rejected"]:
        op.drop_column("uploaded_files", c)
    for c in ["prediction_error_pct", "measurement_window_days", "financial_model", "recovery_confidence", "expected_recovery_sar_v2", "recoverable_value_high_sar", "recoverable_value_low_sar"]:
        op.drop_column("money_audit_actions", c)
    for c in ["evidence_summary", "recovery_confidence", "financial_model_version", "expected_recovery_sar", "recoverable_value_high_sar", "recoverable_value_low_sar", "gross_profit_at_risk_sar", "revenue_at_risk_sar", "capital_at_risk_sar", "inventory_value_sar"]:
        op.drop_column("money_audits", c)
