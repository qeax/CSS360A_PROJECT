"""cars.price_known; drop unused inventory_search_runs cache table

Revision ID: 012
Revises: 011
Create Date: 2026-05-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cars",
        sa.Column("price_known", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_table("inventory_search_runs")


def downgrade() -> None:
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
    op.drop_column("cars", "price_known")
