from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.car import Car
from app.repositories.cars import _listing_ends_at_iso
from app.services.flip import calculate_flip_score, flip_metrics_unknown
from app.services.pricing.service import ResalePricingService
from app.services.pricing.types import PricingInput, ResaleEstimate
from app.services.vehicle_aspects import extended_vehicle_fields_from_aspects_json


def pricing_input_from_car(car: Car) -> PricingInput | None:
    if not getattr(car, "price_known", True):
        return None
    price = float(car.price or 0)
    if price <= 0:
        return None
    aspects = car.aspect_snapshots[0].aspects_json if car.aspect_snapshots else None
    fields = extended_vehicle_fields_from_aspects_json(aspects)
    region = car.location.region if car.location is not None else None
    title_text = None
    if isinstance(car.raw_listing_json, dict):
        title_text = car.raw_listing_json.get("title")
    return PricingInput(
        external_listing_id=car.external_listing_id,
        source=car.source or "ebay",
        purchase_price=price,
        brand=car.brand or "Unknown",
        model=car.model or "Listing",
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
        title_text=title_text,
        car_id=int(car.id),
        raw_listing_json=car.raw_listing_json if isinstance(car.raw_listing_json, dict) else None,
    )


def apply_resale_estimate_to_car(car: Car, estimate: ResaleEstimate) -> None:
    car.resale_value = float(estimate.resale_value)
    car.resale_method = estimate.method
    car.resale_confidence = float(estimate.confidence)
    car.resale_comp_count = int(estimate.comp_count)
    car.resale_segment_key = estimate.segment_key
    car.resale_estimated_at = datetime.now(timezone.utc)


def refresh_car_resale_estimate(db: Session, car: Car) -> ResaleEstimate | None:
    listing = pricing_input_from_car(car)
    if listing is None:
        return None
    estimate = ResalePricingService().estimate(listing, db=db)
    apply_resale_estimate_to_car(car, estimate)
    return estimate


def _patch_api_item_resale(item: dict[str, Any], car: Car) -> None:
    price_known = bool(getattr(car, "price_known", True))
    if price_known:
        analysis = calculate_flip_score(
            car.price, car.resale_value, car.repair_cost or 0, price_known=True
        )
    else:
        analysis = flip_metrics_unknown()
    item["resale_value"] = car.resale_value
    item["resale_method"] = car.resale_method
    item["resale_confidence"] = car.resale_confidence
    item["resale_comp_count"] = car.resale_comp_count
    item["resale_segment_key"] = car.resale_segment_key
    item["resale_estimated_at"] = _listing_ends_at_iso(car.resale_estimated_at)
    item.update(analysis)


def refresh_resale_api_items(db: Session, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reprice visible inventory rows from DB comps only (no eBay calls)."""
    if not items:
        return items
    ids = [int(x["id"]) for x in items if x.get("id") is not None]
    if not ids:
        return items
    cars = list(
        db.scalars(
            select(Car)
            .where(Car.id.in_(ids))
            .options(
                joinedload(Car.location),
                selectinload(Car.aspect_snapshots),
            )
        ).all()
    )
    car_by_id = {int(c.id): c for c in cars}
    service = ResalePricingService()
    touched = False
    for item in items:
        car = car_by_id.get(int(item.get("id") or 0))
        if car is None:
            continue
        listing = pricing_input_from_car(car)
        if listing is None:
            continue
        estimate = service.estimate(listing, db=db)
        apply_resale_estimate_to_car(car, estimate)
        _patch_api_item_resale(item, car)
        touched = True
    if touched:
        db.commit()
    return items
