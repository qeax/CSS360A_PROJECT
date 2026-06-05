"""resale pricing columns and vehicle segments

Revision ID: 019
Revises: 018
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("resale_method", sa.String(length=32), nullable=True))
    op.add_column("cars", sa.Column("resale_confidence", sa.Float(), nullable=True))
    op.add_column("cars", sa.Column("resale_comp_count", sa.Integer(), nullable=True))
    op.add_column("cars", sa.Column("resale_segment_key", sa.String(length=160), nullable=True))
    op.add_column(
        "cars", sa.Column("resale_estimated_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "vehicle_price_segments",
        sa.Column("segment_key", sa.String(length=160), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("year_bucket", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("median_price", sa.Float(), nullable=False),
        sa.Column("p25_price", sa.Float(), nullable=True),
        sa.Column("p75_price", sa.Float(), nullable=True),
        sa.Column("median_mileage", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("segment_key"),
    )
    op.create_index(
        "ix_vehicle_price_segments_brand", "vehicle_price_segments", ["brand"], unique=False
    )
    op.create_index(
        "ix_vehicle_price_segments_model", "vehicle_price_segments", ["model"], unique=False
    )
    op.create_index(
        "ix_vehicle_price_segments_year_bucket",
        "vehicle_price_segments",
        ["year_bucket"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_price_segments_year_bucket", table_name="vehicle_price_segments")
    op.drop_index("ix_vehicle_price_segments_model", table_name="vehicle_price_segments")
    op.drop_index("ix_vehicle_price_segments_brand", table_name="vehicle_price_segments")
    op.drop_table("vehicle_price_segments")

    op.drop_column("cars", "resale_estimated_at")
    op.drop_column("cars", "resale_segment_key")
    op.drop_column("cars", "resale_comp_count")
    op.drop_column("cars", "resale_confidence")
    op.drop_column("cars", "resale_method")
