"""ingest_search_key on cars + inventory_search_runs cache table

Revision ID: 011
Revises: 010
Create Date: 2026-05-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cars",
        sa.Column("ingest_search_key", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_cars_ingest_search_key", "cars", ["ingest_search_key"])

    op.create_table(
        "inventory_search_runs",
        sa.Column("query_key", sa.String(length=128), nullable=False),
        sa.Column("ebay_query", sa.String(length=256), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("listing_count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("query_key"),
    )


def downgrade() -> None:
    op.drop_table("inventory_search_runs")
    op.drop_index("ix_cars_ingest_search_key", table_name="cars")
    op.drop_column("cars", "ingest_search_key")
