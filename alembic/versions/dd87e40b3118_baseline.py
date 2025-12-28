"""baseline

Revision ID: dd87e40b3118
Revises: 818d62e57c1c
Create Date: 2025-12-28 07:21:52.584692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd87e40b3118'
# down_revision: Union[str, Sequence[str], None] = '818d62e57c1c'
down_revision = None

branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
