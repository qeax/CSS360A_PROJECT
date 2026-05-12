"""user audit events and moderation placeholders on users

Revision ID: 004
Revises: 003
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("ip_address_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_audit_events_user_id"), "user_audit_events", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_audit_events_created_at"),
        "user_audit_events",
        ["created_at"],
        unique=False,
    )

    op.add_column(
        "users",
        sa.Column(
            "account_status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("restricted_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("moderation_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "moderation_note")
    op.drop_column("users", "restricted_until")
    op.drop_column("users", "account_status")

    op.drop_index(op.f("ix_user_audit_events_created_at"), table_name="user_audit_events")
    op.drop_index(op.f("ix_user_audit_events_user_id"), table_name="user_audit_events")
    op.drop_table("user_audit_events")
