from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.vehicle_price_segment import VehiclePriceSegment
from app.services.pricing.types import PricingInput


@dataclass(frozen=True)
class SegmentBaseline:
    segment_key: str
    sample_count: int
    median_price: float
    p25_price: float | None
    p75_price: float | None
    median_mileage: int | None


def _segment_key(brand: str, model: str, year_bucket: int) -> str:
    return f"{brand.strip().lower()}|{model.strip().lower()}|{year_bucket}"


def _year_bucket(year: int | None) -> int:
    if year is None:
        return 0
    return int(year)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    idx = int(round((len(values) - 1) * p))
    return float(values[max(0, min(len(values) - 1, idx))])


def rebuild_vehicle_price_segments(db: Session) -> int:
    rows = list(
        db.scalars(
            select(Car).where(
                and_(
                    Car.price_known.is_(True),
                    Car.source == "ebay",
                    Car.brand.is_not(None),
                    Car.model.is_not(None),
                )
            )
        ).all()
    )
    buckets: dict[str, list[Car]] = {}
    for car in rows:
        key = _segment_key(car.brand, car.model, _year_bucket(car.year))
        buckets.setdefault(key, []).append(car)
    db.execute(delete(VehiclePriceSegment))
    now = datetime.now(timezone.utc)
    created = 0
    for key, cars in buckets.items():
        prices = sorted(float(c.price) for c in cars if c.price is not None and c.price > 0)
        if not prices:
            continue
        miles = sorted(int(c.mileage) for c in cars if c.mileage is not None and c.mileage > 0)
        brand, model, yb = key.split("|")
        db.add(
            VehiclePriceSegment(
                segment_key=key,
                brand=brand,
                model=model,
                year_bucket=int(yb),
                sample_count=len(prices),
                median_price=float(statistics.median(prices)),
                p25_price=_percentile(prices, 0.25),
                p75_price=_percentile(prices, 0.75),
                median_mileage=int(statistics.median(miles)) if miles else None,
                updated_at=now,
            )
        )
        created += 1
    return created


def get_segment_baseline(db: Session, listing: PricingInput) -> SegmentBaseline | None:
    brand = listing.brand.strip().lower()
    model = listing.model.strip().lower()
    year = _year_bucket(listing.year)
    keys = [key for key in (_segment_key(brand, model, year), _segment_key(brand, model, 0)) if key]
    if year:
        keys.append(_segment_key(brand, model, year - 1))
        keys.append(_segment_key(brand, model, year + 1))
    for key in keys:
        row = db.execute(
            select(VehiclePriceSegment).where(VehiclePriceSegment.segment_key == key)
        ).scalar_one_or_none()
        if row is None:
            continue
        return SegmentBaseline(
            segment_key=row.segment_key,
            sample_count=int(row.sample_count or 0),
            median_price=float(row.median_price or 0.0),
            p25_price=float(row.p25_price) if row.p25_price is not None else None,
            p75_price=float(row.p75_price) if row.p75_price is not None else None,
            median_mileage=int(row.median_mileage) if row.median_mileage is not None else None,
        )
    return None
