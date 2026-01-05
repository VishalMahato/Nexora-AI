"""add tool_calls table

Revision ID: 4c1306f19771
Revises: 54328ce1b891
Create Date: 2026-01-05 09:46:43.381740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4c1306f19771'
down_revision: Union[str, Sequence[str], None] = '54328ce1b891'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["run_steps.id"], ondelete="SET NULL"),
    )

    op.create_index(
        "idx_tool_calls_run_id_started_at",
        "tool_calls",
        ["run_id", "started_at"],
    )
    op.create_index(
        "idx_tool_calls_step_id",
        "tool_calls",
        ["step_id"],
    )
    op.create_index(
        "idx_tool_calls_tool_name_started_at",
        "tool_calls",
        ["tool_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_tool_calls_tool_name_started_at", table_name="tool_calls")
    op.drop_index("idx_tool_calls_step_id", table_name="tool_calls")
    op.drop_index("idx_tool_calls_run_id_started_at", table_name="tool_calls")
    op.drop_table("tool_calls")