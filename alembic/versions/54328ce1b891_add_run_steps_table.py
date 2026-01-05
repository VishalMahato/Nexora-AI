"""add run_steps table

Revision ID: 54328ce1b891
Revises: 2a8101a17061
Create Date: 2026-01-05 09:22:16.756793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '54328ce1b891'
down_revision: Union[str, Sequence[str], None] = '2a8101a17061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_name", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_run_steps_run_id_started_at", "run_steps", ["run_id", "started_at"])
    op.create_index("idx_run_steps_run_id_step_name", "run_steps", ["run_id", "step_name"])


def downgrade() -> None:
    op.drop_index("idx_run_steps_run_id_step_name", table_name="run_steps")
    op.drop_index("idx_run_steps_run_id_started_at", table_name="run_steps")
    op.drop_table("run_steps")