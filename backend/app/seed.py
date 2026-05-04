"""
Load demo rows from seeds/cars_seed.json when the cars table is empty.

Rows are inserted with source=demo so they can be removed later via python -m app.purge_demo.

Run: python -m app.seed (from backend directory, with PYTHONPATH=. or installed package)
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.car import Car


def seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "seeds" / "cars_seed.json"


def run() -> int:
    path = seed_path()
    if not path.is_file():
        print(f"Seed file not found: {path}")
        return 1

    rows = json.loads(path.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(Car)) or 0
        if count > 0:
            print("Cars table is not empty; skipping seed.")
            return 0
        for row in rows:
            allowed = {
                "brand",
                "model",
                "year",
                "price",
                "repair_cost",
                "resale_value",
                "mileage",
                "condition",
                "image_url",
                "source",
                "external_listing_id",
                "listing_url",
                "raw_listing_json",
            }
            data = {k: row[k] for k in allowed if k in row}
            db.add(Car(**data))
        db.commit()
        print(f"Seeded {len(rows)} cars.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
