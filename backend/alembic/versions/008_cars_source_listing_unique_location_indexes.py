"""cars unique (source, external_listing_id) and car_locations filter indexes

Revision ID: 008
Revises: 007
Create Date: 2026-05-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_source_listing_ids(connection) -> None:
    """Keep newest row per (source, external_listing_id) before adding UNIQUE."""
    dialect = connection.dialect.name
    if dialect == "sqlite":
        connection.execute(
            sa.text(
                """
                DELETE FROM cars
                WHERE external_listing_id IS NOT NULL
                  AND id NOT IN (
                    SELECT MAX(id) FROM cars
                    WHERE external_listing_id IS NOT NULL
                    GROUP BY source, external_listing_id
                  )
                """
            )
        )
    else:
        connection.execute(
            sa.text(
                """
                DELETE c1 FROM cars c1
                INNER JOIN cars c2
                  ON c1.source = c2.source
                 AND c1.external_listing_id = c2.external_listing_id
                 AND c1.id < c2.id
                WHERE c1.external_listing_id IS NOT NULL
                """
            )
        )


def upgrade() -> None:
    bind = op.get_bind()
    _dedupe_source_listing_ids(bind)

    op.create_unique_constraint(
        "uq_cars_source_external_listing_id",
        "cars",
        ["source", "external_listing_id"],
    )

    op.create_index("ix_car_locations_country", "car_locations", ["country"], unique=False)
    op.create_index("ix_car_locations_region", "car_locations", ["region"], unique=False)
    op.create_index("ix_car_locations_city", "car_locations", ["city"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_car_locations_city", table_name="car_locations")
    op.drop_index("ix_car_locations_region", table_name="car_locations")
    op.drop_index("ix_car_locations_country", table_name="car_locations")
    op.drop_constraint("uq_cars_source_external_listing_id", "cars", type_="unique")
