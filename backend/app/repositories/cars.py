from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.car import Car
from app.services.flip import calculate_flip_score


def iter_cars(db: Session):
    return db.scalars(
        select(Car)
        .options(
            joinedload(Car.external_seller),
            joinedload(Car.location),
            joinedload(Car.listing_terms),
        )
        .order_by(Car.id)
    ).all()


def apply_filters(
    cars: list,
    make: Optional[str],
    model: Optional[str],
    min_year: Optional[int],
    max_year: Optional[int],
    condition: Optional[str],
    max_price: Optional[float],
    min_profit: Optional[float],
    min_roi: Optional[float],
) -> list:
    results = []
    for car in cars:
        if make and make.lower() not in car.brand.lower():
            continue
        if model and model.lower() not in car.model.lower():
            continue
        if min_year and car.year < min_year:
            continue
        if max_year and car.year > max_year:
            continue
        condition_value = car.condition
        if condition and (
            not condition_value or condition.lower() not in condition_value.lower()
        ):
            continue
        if max_price and car.price > max_price:
            continue

        analysis = calculate_flip_score(
            car.price, car.resale_value, car.repair_cost or 0
        )
        if min_profit and analysis["net_profit"] < min_profit:
            continue
        if min_roi and analysis["roi"] < min_roi:
            continue

        mileage = car.mileage
        if mileage is None:
            mileage = 75000 + (car.id * 1500)

        listing_terms = car.listing_terms
        delivery = None
        if listing_terms is not None:
            delivery = {
                "ship_to_home": listing_terms.ship_to_home,
                "local_pickup": listing_terms.local_pickup,
                "in_store_pickup": listing_terms.in_store_pickup,
            }

        loc = car.location
        location_out = None
        if loc is not None:
            location_out = {
                "country": loc.country,
                "region": loc.region,
                "city": loc.city,
                "postal_code_masked": loc.postal_code_masked,
            }

        seller_username = None
        es = car.external_seller
        if es is not None:
            seller_username = es.username

        listing_ends_at = None
        if car.listing_ends_at is not None:
            listing_ends_at = car.listing_ends_at.isoformat()

        results.append(
            {
                "id": car.id,
                "brand": car.brand,
                "model": car.model,
                "year": car.year,
                "price": car.price,
                "repair_cost": car.repair_cost,
                "resale_value": car.resale_value,
                "mileage": mileage,
                "condition": car.condition,
                "image_url": car.image_url,
                "source": car.source or "manual",
                "external_listing_id": car.external_listing_id,
                "listing_url": car.listing_url,
                "listing_ends_at": listing_ends_at,
                "bid_count": car.bid_count,
                "listing_format": car.listing_format,
                "description_summary": car.description_summary,
                "seller_username": seller_username,
                "location": location_out,
                "delivery": delivery,
                **analysis,
            }
        )
    return results
