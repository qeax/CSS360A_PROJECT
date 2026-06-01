"""Location filter tests including Not specified sentinel."""

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import joinedload, sessionmaker

from app.db import Base
from app.models.car import Car
from app.models.car_satellite import CarLocation
from app.repositories.cars import LOCATION_NOT_SPECIFIED, apply_filters, compute_inventory_meta


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _car_with_location(db, *, country=None, region=None, city=None):
    car = Car(
        brand="Test",
        model="Car",
        year=2020,
        price=10000,
        repair_cost=0,
        resale_value=12000,
        source="ebay",
        external_listing_id=f"test-{uuid.uuid4().hex}",
    )
    db.add(car)
    db.flush()
    db.add(
        CarLocation(
            car_id=car.id,
            country=country,
            region=region,
            city=city,
        )
    )
    db.commit()
    return car


def test_meta_includes_location_not_specified_flags(db):
    _car_with_location(db, country=None, region=None, city=None)
    _car_with_location(db, country="United States", region=None, city=None)
    meta = compute_inventory_meta(db)
    assert meta["location_not_specified"]["country"] is True
    assert meta["location_not_specified"]["region"] is True


def test_filter_country_not_specified(db):
    _car_with_location(db, country=None, region=None, city=None)
    _car_with_location(db, country="Canada", region="ON", city="Toronto")
    rows = list(db.scalars(select(Car).options(joinedload(Car.location))).all())
    out = apply_filters(
        rows,
        make=None,
        makes=None,
        model=None,
        min_year=None,
        max_year=None,
        min_mileage=None,
        max_mileage=None,
        condition=None,
        conditions=None,
        max_price=None,
        min_price=None,
        min_profit=None,
        min_roi=None,
        q=None,
        countries=[LOCATION_NOT_SPECIFIED],
        regions=None,
        cities=None,
        radius_km=None,
        radius_mi=None,
        anchor_lat=None,
        anchor_lng=None,
        listing_formats=None,
        body_styles=None,
        delivery_modes=None,
        vehicle_titles=None,
    )
    assert len(out) == 1
    assert out[0]["location"] is None or not out[0]["location"].get("country")
