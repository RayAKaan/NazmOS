"""Add first-class owner constraints."""
from alembic import op
import sqlalchemy as sa
revision="ff01_owner_const"
down_revision="rec_intel_v2_0824"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("businesses", sa.Column("constraints_json", sa.JSON(), nullable=True))
def downgrade():
    op.drop_column("businesses", "constraints_json")
