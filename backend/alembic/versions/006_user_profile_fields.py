"""add display_name and profile_picture_url to users

Revision ID: 006
Revises: 005
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("profile_picture_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_picture_url")
    op.drop_column("users", "display_name")
