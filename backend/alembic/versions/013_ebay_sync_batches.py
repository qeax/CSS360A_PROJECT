"""ebay_sync_batches table for staged search summaries

Revision ID: 013
Revises: 012
Create Date: 2026-06-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ebay_sync_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("search_key", sa.String(length=128), nullable=False),
        sa.Column("search_query", sa.String(length=512), nullable=False),
        sa.Column("summaries_json", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "search_key", name="uq_ebay_sync_batches_user_search_key"),
    )
    op.create_index(
        op.f("ix_ebay_sync_batches_user_id"), "ebay_sync_batches", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_ebay_sync_batches_search_key"), "ebay_sync_batches", ["search_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ebay_sync_batches_search_key"), table_name="ebay_sync_batches")
    op.drop_index(op.f("ix_ebay_sync_batches_user_id"), table_name="ebay_sync_batches")
    op.drop_table("ebay_sync_batches")
