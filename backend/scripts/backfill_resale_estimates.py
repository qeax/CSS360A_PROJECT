"""Backfill ARV model outputs for existing car rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models.car import Car
from app.services.pricing import PricingInput, ResalePricingService, rebuild_vehicle_price_segments
from app.services.vehicle_aspects import extended_vehicle_fields_from_aspects_json


def run_backfill() -> None:
    db = SessionLocal()
    try:
        rebuild_vehicle_price_segments(db)
        service = ResalePricingService()
        cars = list(
            db.scalars(
                select(Car).where(Car.price_known.is_(True), Car.price > 0, Car.source == "ebay")
            )
        )
        updated = 0
        for car in cars:
            aspects = car.aspect_snapshots[0].aspects_json if car.aspect_snapshots else None
            fields = extended_vehicle_fields_from_aspects_json(aspects)
            region = car.location.region if car.location is not None else None
            listing = PricingInput(
                external_listing_id=car.external_listing_id,
                source=car.source or "ebay",
                purchase_price=float(car.price),
                brand=car.brand,
                model=car.model,
                year=car.year,
                mileage=car.mileage,
                condition=car.condition,
                vehicle_title=car.vehicle_title,
                listing_format=car.listing_format,
                region=region,
                synced_at=car.api_synced_at,
                trim=fields.get("trim"),
                engine=fields.get("engine"),
                body_style=fields.get("body_style"),
                title_text=(car.raw_listing_json or {}).get("title")
                if isinstance(car.raw_listing_json, dict)
                else None,
                car_id=int(car.id),
            )
            estimate = service.estimate(listing, db=db)
            car.resale_value = float(estimate.resale_value)
            car.resale_method = estimate.method
            car.resale_confidence = float(estimate.confidence)
            car.resale_comp_count = int(estimate.comp_count)
            car.resale_segment_key = estimate.segment_key
            car.resale_estimated_at = datetime.now(timezone.utc)
            updated += 1
        db.commit()
        print(f"Backfilled resale estimates for {updated} cars.")
    finally:
        db.close()


if __name__ == "__main__":
    run_backfill()
