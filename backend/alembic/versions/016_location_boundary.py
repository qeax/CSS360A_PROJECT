"""Add boundary_geojson to car_locations for region outline maps."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("car_locations", sa.Column("boundary_geojson", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("car_locations", "boundary_geojson")
