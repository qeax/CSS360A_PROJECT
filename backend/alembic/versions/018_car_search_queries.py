"""add car search queries history table

Revision ID: 018
Revises: 017
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "car_search_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.String(length=256), nullable=False),
        sa.Column("query_key", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="ebay"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("car_id", "query_key", name="uq_car_search_queries_car_query_key"),
    )
    op.create_index("ix_car_search_queries_car_id", "car_search_queries", ["car_id"], unique=False)
    op.create_index(
        "ix_car_search_queries_query_key", "car_search_queries", ["query_key"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_car_search_queries_query_key", table_name="car_search_queries")
    op.drop_index("ix_car_search_queries_car_id", table_name="car_search_queries")
    op.drop_table("car_search_queries")
