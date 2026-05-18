"""add vehicle_title to cars

Revision ID: 005
Revises: 004
Create Date: 2026-05-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("vehicle_title", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("cars", "vehicle_title")
