from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.car_satellite import VehicleAspectSnapshot
from app.services.pricing.types import ComparableCandidate, PricingInput
from app.services.vehicle_aspects import extended_vehicle_fields_from_aspects_json

_AUCTION_COMP_MIN_PRICE = 1000.0
_AUCTION_COMP_MEDIAN_RATIO = 0.25


def _is_auction_format(listing_format: str | None) -> bool:
    return "AUCTION" in (listing_format or "").upper()


def _is_reliable_comp_price(price: float, listing_format: str | None, *, floor: float) -> bool:
    """Exclude early-auction bids that would skew comp medians downward."""
    if not _is_auction_format(listing_format):
        return True
    if price < _AUCTION_COMP_MIN_PRICE:
        return False
    if floor > 0 and price < floor:
        return False
    return True


_RECENCY_HALFLIFE_DAYS = 45.0


def _norm_text(v: str | None) -> str:
    return (v or "").strip().lower()


def _year_similarity(target: int | None, comp: int | None) -> float:
    if target is None or comp is None:
        return 0.5
    return math.exp(-abs(target - comp) / 1.5)


def _mileage_similarity(target: int | None, comp: int | None) -> float:
    if target is None or comp is None:
        return 0.5
    return math.exp(-abs(target - comp) / 25_000.0)


def _match_similarity(a: str | None, b: str | None) -> float:
    aa, bb = _norm_text(a), _norm_text(b)
    if not aa or not bb:
        return 0.5
    return 1.0 if aa == bb else 0.0


def _region_similarity(a: str | None, b: str | None) -> float:
    aa, bb = _norm_text(a), _norm_text(b)
    if not aa or not bb:
        return 0.35
    return 1.0 if aa == bb else 0.2


def _recency_similarity(synced_at: datetime | None) -> float:
    if synced_at is None:
        return 0.3
    now = datetime.now(timezone.utc)
    ref = synced_at if synced_at.tzinfo is not None else synced_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - ref).total_seconds() / 86400.0)
    return math.exp(-days / _RECENCY_HALFLIFE_DAYS)


def _candidate_similarity(target: PricingInput, comp: Car, aspect_fields: dict[str, Any]) -> float:
    weights = {
        "make_model": 0.26,
        "year": 0.20,
        "mileage": 0.17,
        "condition": 0.13,
        "title": 0.08,
        "region": 0.08,
        "recency": 0.08,
    }
    score = 0.0
    score += weights["make_model"] * (
        1.0
        if _norm_text(target.brand) == _norm_text(comp.brand)
        and _norm_text(target.model) == _norm_text(comp.model)
        else 0.0
    )
    score += weights["year"] * _year_similarity(target.year, comp.year)
    score += weights["mileage"] * _mileage_similarity(target.mileage, comp.mileage)
    score += weights["condition"] * _match_similarity(target.condition, comp.condition)
    score += weights["title"] * _match_similarity(target.vehicle_title, comp.vehicle_title)
    loc_region = comp.location.region if comp.location is not None else None
    score += weights["region"] * _region_similarity(target.region, loc_region)
    score += weights["recency"] * _recency_similarity(comp.api_synced_at)
    trim_target = _norm_text(target.trim)
    trim_comp = _norm_text(aspect_fields.get("trim"))
    if trim_target and trim_comp and trim_target == trim_comp:
        score += 0.04
    engine_target = _norm_text(target.engine)
    engine_comp = _norm_text(aspect_fields.get("engine"))
    if engine_target and engine_comp and engine_target == engine_comp:
        score += 0.03
    return max(0.0, min(1.0, score))


def weighted_trimmed_median(
    values: list[tuple[float, float]], *, trim_ratio: float = 0.1
) -> float | None:
    rows = [(float(v), float(max(w, 0.0001))) for v, w in values if v > 0]
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    n = len(rows)
    trim = int(n * trim_ratio)
    if n - 2 * trim >= 2:
        rows = rows[trim : n - trim]
    total_w = sum(w for _, w in rows)
    if total_w <= 0:
        return None
    acc = 0.0
    half = total_w / 2.0
    for value, weight in rows:
        acc += weight
        if acc >= half:
            return value
    return rows[-1][0]


def find_comparables(
    db: Session, listing: PricingInput, *, limit: int = 20
) -> list[ComparableCandidate]:
    stmt = select(Car).where(
        and_(
            Car.price_known.is_(True),
            Car.brand == listing.brand,
            Car.model == listing.model,
            Car.source == "ebay",
        )
    )
    if listing.car_id is not None:
        stmt = stmt.where(Car.id != listing.car_id)
    if listing.year is not None:
        stmt = stmt.where(Car.year.between(listing.year - 2, listing.year + 2))

    rows = list(db.scalars(stmt.limit(300)).all())
    provisional_prices = sorted(
        float(c.price) for c in rows if c.price is not None and float(c.price) > 0
    )
    provisional_median = None
    if provisional_prices:
        mid = len(provisional_prices) // 2
        if len(provisional_prices) % 2:
            provisional_median = provisional_prices[mid]
        else:
            provisional_median = (provisional_prices[mid - 1] + provisional_prices[mid]) / 2.0
    auction_floor = _AUCTION_COMP_MIN_PRICE
    if provisional_median is not None and provisional_median > 0:
        auction_floor = max(
            _AUCTION_COMP_MIN_PRICE, provisional_median * _AUCTION_COMP_MEDIAN_RATIO
        )

    out: list[ComparableCandidate] = []
    for car in rows:
        comp_price = float(car.price) if car.price is not None else 0.0
        if comp_price <= 0:
            continue
        if not _is_reliable_comp_price(comp_price, car.listing_format, floor=auction_floor):
            continue
        aspects = (
            car.aspect_snapshots[0].aspects_json if getattr(car, "aspect_snapshots", None) else None
        )
        if not aspects:
            snap = db.execute(
                select(VehicleAspectSnapshot)
                .where(VehicleAspectSnapshot.car_id == car.id)
                .order_by(VehicleAspectSnapshot.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            aspects = snap.aspects_json if snap is not None else None
        fields = extended_vehicle_fields_from_aspects_json(aspects)
        sim = _candidate_similarity(listing, car, fields)
        if sim <= 0:
            continue
        out.append(
            ComparableCandidate(
                car_id=int(car.id),
                price=float(car.price),
                brand=car.brand,
                model=car.model,
                year=car.year,
                mileage=car.mileage,
                condition=car.condition,
                vehicle_title=car.vehicle_title,
                listing_format=car.listing_format,
                region=car.location.region if car.location is not None else None,
                synced_at=car.api_synced_at,
                trim=fields.get("trim"),
                engine=fields.get("engine"),
                body_style=fields.get("body_style"),
                source=car.source or "manual",
                similarity=sim,
            )
        )
    out.sort(key=lambda c: c.similarity, reverse=True)
    return out[:limit]
