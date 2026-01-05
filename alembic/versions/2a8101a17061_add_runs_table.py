"""add runs table

Revision ID: 2a8101a17061
Revises: dd87e40b3118
Create Date: 2025-12-28 10:17:38.929720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql




# revision identifiers, used by Alembic.
revision: str = '2a8101a17061'
down_revision: Union[str, Sequence[str], None] = 'dd87e40b3118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None




def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("wallet_address", sa.String(length=64), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_runs_wallet_chain", "runs", ["wallet_address", "chain_id"])
    op.create_index("idx_runs_status_updated", "runs", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_runs_status_updated", table_name="runs")
    op.drop_index("idx_runs_wallet_chain", table_name="runs")
    op.drop_table("runs")