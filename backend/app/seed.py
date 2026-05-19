"""
Load demo inventory when the cars table is empty.

By default **no rows are written**: the API serves the same deterministic demo
catalog from memory (see ``DEMO_IN_MEMORY_WHEN_EMPTY`` and ``repositories.cars``).

To **persist** demo rows into MySQL, set ``SEED_WRITE_DEMO_TO_DB=1``.

Run: python -m app.seed (from backend directory)
"""

from __future__ import annotations

import os

from sqlalchemy import func, select

from app.db import SessionLocal
from app.demo_seed import insert_generated_demo_cars
from app.models.car import Car


def run() -> int:
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(Car)) or 0
        if count > 0:
            print("Cars table is not empty; skipping seed.")
            return 0

        write_demo = os.getenv("SEED_WRITE_DEMO_TO_DB", "").lower() in ("1", "true", "yes")

        if write_demo:
            n = int(os.environ.get("DEMO_SEED_COUNT", "100"))
            inserted = insert_generated_demo_cars(db, n)
            db.commit()
            print(f"Seeded {inserted} generated demo cars into the database.")
            return 0

        print(
            "Cars table is empty; no DB seed written. "
            "Inventory is served from the in-memory demo catalog (default). "
            "To insert demo rows into MySQL, set SEED_WRITE_DEMO_TO_DB=1."
        )
        return 0
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
