"""add checkpoint_writes.task_path

Revision ID: 3f2c0a9b1d7e
Revises: 9b2f4a7c1d3e
Create Date: 2026-03-03 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "3f2c0a9b1d7e"
down_revision: Union[str, Sequence[str], None] = "9b2f4a7c1d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "checkpoint_writes" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("checkpoint_writes")}
    if "task_path" in columns:
        return
    op.add_column("checkpoint_writes", sa.Column("task_path", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "checkpoint_writes" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("checkpoint_writes")}
    if "task_path" not in columns:
        return
    op.drop_column("checkpoint_writes", "task_path")
