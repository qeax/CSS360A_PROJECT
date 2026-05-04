from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.car import Car
from app.services.flip import calculate_flip_score


def iter_cars(db: Session):
    return db.scalars(select(Car).order_by(Car.id)).all()


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
                **analysis,
            }
        )
    return results
