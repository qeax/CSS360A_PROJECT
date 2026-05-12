"""
Remove rows that were loaded from the demo seed (source=demo).

When you switch to real listings (e.g. eBay), run this once, then use
source='ebay' or another non-demo value for new rows.

Usage (from project root, backend container):
  docker compose exec backend python -m app.purge_demo
  docker compose exec backend python -m app.purge_demo --dry-run

Options:
  --dry-run   Print how many rows would be deleted, do not delete.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models.car import Car

DEMO_SOURCE = "demo"


def run(dry_run: bool) -> int:
    db = SessionLocal()
    try:
        n = db.scalar(
            select(func.count()).select_from(Car).where(Car.source == DEMO_SOURCE)
        ) or 0
        if n == 0:
            print("No rows with source='demo' to remove.")
            return 0
        if dry_run:
            print(f"Dry run: would delete {n} row(s) where source='{DEMO_SOURCE}'.")
            return 0
        db.execute(delete(Car).where(Car.source == DEMO_SOURCE))
        db.commit()
        print(f"Deleted {n} demo row(s) (source='{DEMO_SOURCE}').")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Purge failed: {e}")
        return 1
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Remove demo seed rows from cars table.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show count only, do not delete.",
    )
    args = p.parse_args(argv)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
