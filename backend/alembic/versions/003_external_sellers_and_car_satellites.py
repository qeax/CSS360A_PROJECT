"""external sellers, listing columns, car satellite tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_sellers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "platform",
            sa.String(length=32),
            server_default=sa.text("'ebay'"),
            nullable=False,
        ),
        sa.Column("external_seller_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.String(length=1024), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "external_seller_id",
            name="uq_external_sellers_platform_external_id",
        ),
    )
    op.create_index(op.f("ix_external_sellers_id"), "external_sellers", ["id"], unique=False)

    op.add_column("cars", sa.Column("seller_id", sa.Integer(), nullable=True))
    op.add_column(
        "cars",
        sa.Column("listing_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("cars", sa.Column("bid_count", sa.Integer(), nullable=True))
    op.add_column("cars", sa.Column("listing_format", sa.String(length=50), nullable=True))
    op.add_column("cars", sa.Column("description_summary", sa.String(length=1024), nullable=True))
    op.add_column("cars", sa.Column("description_full", sa.Text(), nullable=True))
    op.add_column(
        "cars",
        sa.Column("api_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cars",
        sa.Column("seller_item_revision", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_cars_seller_id_external_sellers",
        "cars",
        "external_sellers",
        ["seller_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_cars_seller_id"), "cars", ["seller_id"], unique=False)

    op.create_table(
        "car_locations",
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=256), nullable=True),
        sa.Column("postal_code_masked", sa.String(length=32), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("car_id"),
    )

    op.create_table(
        "car_listing_terms",
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column(
            "ship_to_home",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "local_pickup",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "in_store_pickup",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("delivery_options_raw", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("car_id"),
    )

    op.create_table(
        "car_media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_car_media_car_id"), "car_media", ["car_id"], unique=False)

    op.create_table(
        "vehicle_aspect_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("aspects_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_vehicle_aspect_snapshots_car_id"),
        "vehicle_aspect_snapshots",
        ["car_id"],
        unique=False,
    )

    op.create_table(
        "vehicle_history_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_report_id", sa.String(length=256), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_vehicle_history_reports_car_id"),
        "vehicle_history_reports",
        ["car_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vehicle_history_reports_car_id"), table_name="vehicle_history_reports")
    op.drop_table("vehicle_history_reports")

    op.drop_index(
        op.f("ix_vehicle_aspect_snapshots_car_id"), table_name="vehicle_aspect_snapshots"
    )
    op.drop_table("vehicle_aspect_snapshots")

    op.drop_index(op.f("ix_car_media_car_id"), table_name="car_media")
    op.drop_table("car_media")

    op.drop_table("car_listing_terms")

    op.drop_table("car_locations")

    op.drop_constraint("fk_cars_seller_id_external_sellers", "cars", type_="foreignkey")
    op.drop_index(op.f("ix_cars_seller_id"), table_name="cars")
    op.drop_column("cars", "seller_item_revision")
    op.drop_column("cars", "api_synced_at")
    op.drop_column("cars", "description_full")
    op.drop_column("cars", "description_summary")
    op.drop_column("cars", "listing_format")
    op.drop_column("cars", "bid_count")
    op.drop_column("cars", "listing_ends_at")
    op.drop_column("cars", "seller_id")

    op.drop_index(op.f("ix_external_sellers_id"), table_name="external_sellers")
    op.drop_table("external_sellers")
