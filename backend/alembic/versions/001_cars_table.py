"""cars table and ebay-ready columns

Revision ID: 001
Revises:
Create Date: 2026-04-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_full_table() -> None:
    op.create_table(
        "cars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("repair_cost", sa.Float(), nullable=False),
        sa.Column("resale_value", sa.Float(), nullable=False),
        sa.Column("mileage", sa.Integer(), nullable=True),
        sa.Column("condition", sa.String(length=50), nullable=True),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column(
            "source",
            sa.String(length=50),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
        sa.Column("external_listing_id", sa.String(length=128), nullable=True),
        sa.Column("listing_url", sa.String(length=1024), nullable=True),
        sa.Column("raw_listing_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cars_brand"), "cars", ["brand"], unique=False)
    op.create_index(op.f("ix_cars_external_listing_id"), "cars", ["external_listing_id"], unique=False)
    op.create_index(op.f("ix_cars_id"), "cars", ["id"], unique=False)
    op.create_index(op.f("ix_cars_model"), "cars", ["model"], unique=False)
    op.create_index(op.f("ix_cars_price"), "cars", ["price"], unique=False)
    op.create_index(op.f("ix_cars_year"), "cars", ["year"], unique=False)


def _add_missing_columns(cols: set) -> None:
    with op.batch_alter_table("cars", schema=None) as batch_op:
        if "image_url" not in cols:
            batch_op.add_column(sa.Column("image_url", sa.String(length=512), nullable=True))
        if "source" not in cols:
            batch_op.add_column(
                sa.Column(
                    "source",
                    sa.String(length=50),
                    server_default=sa.text("'manual'"),
                    nullable=False,
                )
            )
        if "external_listing_id" not in cols:
            batch_op.add_column(sa.Column("external_listing_id", sa.String(length=128), nullable=True))
        if "listing_url" not in cols:
            batch_op.add_column(sa.Column("listing_url", sa.String(length=1024), nullable=True))
        if "raw_listing_json" not in cols:
            batch_op.add_column(sa.Column("raw_listing_json", sa.JSON(), nullable=True))
        if "created_at" not in cols:
            batch_op.add_column(
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                    nullable=False,
                )
            )
        if "updated_at" not in cols:
            batch_op.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                    nullable=False,
                )
            )


def _ensure_indexes(inspector) -> None:
    existing = {ix["name"] for ix in inspector.get_indexes("cars")}
    if "ix_cars_external_listing_id" not in existing:
        op.create_index(
            op.f("ix_cars_external_listing_id"), "cars", ["external_listing_id"], unique=False
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "cars" not in inspector.get_table_names():
        _create_full_table()
        return

    cols = {c["name"] for c in inspector.get_columns("cars")}
    _add_missing_columns(cols)
    inspector = inspect(bind)
    _ensure_indexes(inspector)


def downgrade() -> None:
    op.drop_table("cars")
