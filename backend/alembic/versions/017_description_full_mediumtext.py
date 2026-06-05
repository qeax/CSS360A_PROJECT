"""widen description_full for large eBay HTML listings

Revision ID: 017
Revises: 016
Create Date: 2026-06-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "cars",
            "description_full",
            existing_type=sa.Text(),
            type_=mysql.MEDIUMTEXT(),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "cars",
            "description_full",
            existing_type=mysql.MEDIUMTEXT(),
            type_=sa.Text(),
            existing_nullable=True,
        )
