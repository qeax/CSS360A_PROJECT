from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.car import Car
from app.models.car_satellite import CarLocation, VehicleAspectSnapshot
from app.models.vehicle_price_segment import VehiclePriceSegment  # noqa: F401
from app.services.pricing import PricingInput, ResalePricingService, rebuild_vehicle_price_segments


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_comp(
    db,
    *,
    ext_id: str,
    brand: str,
    model: str,
    year: int,
    price: float,
    mileage: int,
    region: str = "CA",
):
    car = Car(
        brand=brand,
        model=model,
        year=year,
        price=price,
        repair_cost=1200.0,
        resale_value=price * 1.1,
        mileage=mileage,
        condition="Used",
        vehicle_title="Clean",
        source="ebay",
        external_listing_id=ext_id,
        price_known=True,
        api_synced_at=datetime.now(timezone.utc),
    )
    db.add(car)
    db.flush()
    db.add(CarLocation(car_id=car.id, country="United States", region=region, city="LA"))
    db.add(
        VehicleAspectSnapshot(
            car_id=car.id,
            aspects_json=[{"name": "Trim", "value": "EX"}, {"name": "Engine", "value": "2.0L"}],
        )
    )


def test_resale_service_uses_comps_when_available(db):
    for idx, price in enumerate((17100.0, 18200.0, 17600.0, 18800.0, 17900.0), start=1):
        _seed_comp(
            db,
            ext_id=f"c{idx}",
            brand="Honda",
            model="Civic",
            year=2020,
            price=price,
            mileage=45_000 + idx * 3_000,
        )
    db.commit()
    rebuild_vehicle_price_segments(db)
    inp = PricingInput(
        external_listing_id="target",
        source="ebay",
        purchase_price=16000.0,
        brand="Honda",
        model="Civic",
        year=2020,
        mileage=50_000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="BUY_IT_NOW",
        region="CA",
        synced_at=datetime.now(timezone.utc),
        trim="EX",
        engine="2.0L",
        body_style="Sedan",
        title_text="2020 Honda Civic EX",
    )
    out = ResalePricingService().estimate(inp, db=db)
    assert out.method.startswith("comps")
    assert out.comp_count >= 2
    assert out.resale_value > 0


def test_resale_service_falls_back_to_segment(db):
    for idx, price in enumerate((9000.0, 9800.0, 10200.0), start=1):
        _seed_comp(
            db,
            ext_id=f"f{idx}",
            brand="Ford",
            model="Focus",
            year=2016,
            price=price,
            mileage=90_000 + idx * 2_000,
            region="TX",
        )
    db.commit()
    rebuild_vehicle_price_segments(db)
    inp = PricingInput(
        external_listing_id="target-f",
        source="ebay",
        purchase_price=8500.0,
        brand="Ford",
        model="Focus",
        year=2018,
        mileage=92_000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="AUCTION",
        region="NY",
        synced_at=datetime.now(timezone.utc),
        title_text="2018 Ford Focus",
    )
    out = ResalePricingService(comp_threshold=0.9).estimate(inp, db=db)
    assert out.method in ("segment", "comps_shrunk")
    assert out.resale_value > 0


def test_segment_rebuild_handles_pipe_in_model(db):
    _seed_comp(
        db,
        ext_id="pipe-1",
        brand="Ford",
        model="F-150|SuperCrew",
        year=2018,
        price=22000.0,
        mileage=80_000,
    )
    created = rebuild_vehicle_price_segments(db)
    assert created >= 1
    db.commit()


def test_resale_service_falls_back_to_heuristic_when_no_data(db):
    inp = PricingInput(
        external_listing_id="solo",
        source="ebay",
        purchase_price=12000.0,
        brand="Saab",
        model="9-3",
        year=2005,
        mileage=120_000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="BUY_IT_NOW",
        region=None,
        synced_at=datetime.now(timezone.utc),
        title_text="2005 Saab 9-3",
    )
    out = ResalePricingService().estimate(inp, db=db)
    assert out.method == "heuristic"
    assert out.confidence <= 0.4
