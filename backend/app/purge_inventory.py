"""
Delete all inventory rows (cars and related satellites, external sellers).

Use before switching to eBay-only in-memory catalog or to remove stale DB data.

Usage (from project root):
  docker compose exec backend python -m app.purge_inventory
  docker compose exec backend python -m app.purge_inventory --dry-run
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models.car import Car
from app.models.external_seller import ExternalSeller
from app.repositories.cars import invalidate_in_memory_demo_cache


def run(dry_run: bool) -> int:
    db = SessionLocal()
    try:
        car_n = db.scalar(select(func.count()).select_from(Car)) or 0
        seller_n = db.scalar(select(func.count()).select_from(ExternalSeller)) or 0
        if car_n == 0 and seller_n == 0:
            print("Inventory already empty (no cars or external_sellers).")
            invalidate_in_memory_demo_cache()
            return 0
        if dry_run:
            print(f"Dry run: would delete {car_n} car(s) and {seller_n} external_seller row(s).")
            return 0
        db.execute(delete(Car))
        db.execute(delete(ExternalSeller))
        db.commit()
        invalidate_in_memory_demo_cache()
        print(f"Deleted {car_n} car(s) and {seller_n} external_seller row(s).")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Purge failed: {e}")
        return 1
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Remove all cars and external sellers from the database."
    )
    p.add_argument("--dry-run", action="store_true", help="Show counts only, do not delete.")
    return run(dry_run=p.parse_args(argv).dry_run)


if __name__ == "__main__":
    sys.exit(main())
