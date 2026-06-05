"""user_notifications + users.watch_last_full_check_at

Revision ID: 015
Revises: 014
Create Date: 2026-06-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("watch_last_full_check_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_notifications_user_id"), "user_notifications", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_notifications_car_id"), "user_notifications", ["car_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_notifications_created_at"), "user_notifications", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_notifications_created_at"), table_name="user_notifications")
    op.drop_index(op.f("ix_user_notifications_car_id"), table_name="user_notifications")
    op.drop_index(op.f("ix_user_notifications_user_id"), table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_column("users", "watch_last_full_check_at")
