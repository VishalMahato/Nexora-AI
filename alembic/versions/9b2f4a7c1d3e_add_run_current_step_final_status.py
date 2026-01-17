"""add runs.current_step and runs.final_status

Revision ID: 9b2f4a7c1d3e
Revises: 6d1f2f0a9c2e
Create Date: 2026-03-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b2f4a7c1d3e"
down_revision: Union[str, Sequence[str], None] = "6d1f2f0a9c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("current_step", sa.String(length=64), nullable=True))
    op.add_column("runs", sa.Column("final_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "final_status")
    op.drop_column("runs", "current_step")
