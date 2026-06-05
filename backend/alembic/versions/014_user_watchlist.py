"""user_watchlist_items table

Revision ID: 014
Revises: 013
Create Date: 2026-06-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_watchlist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("last_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "car_id", name="uq_user_watchlist_user_car"),
    )
    op.create_index(
        op.f("ix_user_watchlist_items_user_id"), "user_watchlist_items", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_watchlist_items_car_id"), "user_watchlist_items", ["car_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_watchlist_items_car_id"), table_name="user_watchlist_items")
    op.drop_index(op.f("ix_user_watchlist_items_user_id"), table_name="user_watchlist_items")
    op.drop_table("user_watchlist_items")
