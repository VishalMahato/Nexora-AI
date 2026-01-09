"""add runs.artifacts jsonb

Revision ID: 6d1f2f0a9c2e
Revises: 4c1306f19771
Create Date: 2026-01-08 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6d1f2f0a9c2e"
down_revision: Union[str, Sequence[str], None] = "4c1306f19771"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "artifacts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("runs", "artifacts", server_default=None)


def downgrade() -> None:
    op.drop_column("runs", "artifacts")
