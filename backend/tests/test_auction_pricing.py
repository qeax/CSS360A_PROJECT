"""Auction bid reliability and effective purchase price for ROI."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.car import Car
from app.models.car_satellite import CarLocation, VehicleAspectSnapshot
from app.models.vehicle_price_segment import VehiclePriceSegment  # noqa: F401
from app.services.flip import (
    _is_collectible_vehicle,
    calculate_flip_score_for_listing,
    estimate_flip_from_listing,
    is_unreliable_auction_bid,
    resolve_effective_purchase_price,
)
from app.services.pricing import rebuild_vehicle_price_segments
from app.services.pricing.refresh import _patch_api_item_resale


def test_unreliable_auction_bid_low_price():
    assert is_unreliable_auction_bid(99, "AUCTION") is True
    assert is_unreliable_auction_bid(99, "BUY_IT_NOW") is False


def test_unreliable_auction_bid_vs_reference():
    assert is_unreliable_auction_bid(2000, "AUCTION", reference_value=17000) is True
    assert is_unreliable_auction_bid(8000, "AUCTION", reference_value=17000) is False


def test_unreliable_auction_bid_early_bids():
    assert is_unreliable_auction_bid(3000, "AUCTION", bid_count=0) is True
    assert is_unreliable_auction_bid(3000, "AUCTION", bid_count=5) is False


def test_auction_low_bid_roi_is_reasonable():
    out = calculate_flip_score_for_listing(
        99,
        17000,
        1200,
        listing_format="AUCTION",
        bid_count=0,
        year=2018,
        title_text="2018 Honda Civic",
    )
    assert out["roi_is_preliminary"] is True
    assert out["purchase_price_effective"] > 1000
    assert out["roi"] < 50


def test_fixed_price_low_price_not_preliminary():
    out = calculate_flip_score_for_listing(
        99,
        500,
        50,
        listing_format="BUY_IT_NOW",
        year=2010,
        title_text="2010 Ford Focus parts",
    )
    assert out["roi_is_preliminary"] is False
    assert out["purchase_price_effective"] == 99


def test_collectible_detection_uses_model_year():
    assert _is_collectible_vehicle("1969 Ford Mustang", 1969) is True
    assert _is_collectible_vehicle("1969 Ford Mustang", 6) is False


def test_effective_price_uses_baseline_when_no_segment():
    effective, estimated = resolve_effective_purchase_price(
        99,
        listing_format="AUCTION",
        bid_count=0,
        year=2018,
        title_text="2018 Honda Civic",
    )
    assert estimated is True
    assert effective >= 10000


def test_repair_cost_uses_effective_price_for_auction():
    repair_low_bid, _ = estimate_flip_from_listing(
        99,
        year=2018,
        mileage=72_000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="AUCTION",
        bid_count=0,
        title_text="2018 Honda Civic",
        listing_id="auction-99",
    )
    repair_baseline, _ = estimate_flip_from_listing(
        12500,
        year=2018,
        mileage=72_000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="AUCTION",
        bid_count=0,
        title_text="2018 Honda Civic",
        listing_id="auction-baseline",
    )
    assert repair_low_bid > 500
    assert abs(repair_low_bid - repair_baseline) < repair_baseline * 0.15


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


def _seed_auction_comp(db, *, ext_id: str, price: float):
    car = Car(
        brand="Honda",
        model="Civic",
        year=2018,
        price=price,
        repair_cost=800.0,
        resale_value=price * 1.1,
        mileage=70_000,
        condition="Used",
        vehicle_title="Clean",
        source="ebay",
        external_listing_id=ext_id,
        price_known=True,
        listing_format="AUCTION",
        api_synced_at=datetime.now(timezone.utc),
    )
    db.add(car)
    db.flush()
    db.add(CarLocation(car_id=car.id, country="United States", region="CA", city="LA"))
    db.add(
        VehicleAspectSnapshot(
            car_id=car.id,
            aspects_json=[{"name": "Trim", "value": "EX"}],
        )
    )


def test_segment_rebuild_excludes_low_auction_bids(db):
    for idx, price in enumerate((50.0, 12000.0, 13000.0, 12500.0), start=1):
        _seed_auction_comp(db, ext_id=f"a{idx}", price=price)
    db.commit()
    rebuild_vehicle_price_segments(db)
    db.commit()
    row = db.query(VehiclePriceSegment).filter_by(model="civic").one()
    assert row.median_price >= 10000
    assert row.sample_count == 3


def test_patch_api_item_resale_does_not_crash():
    car = Car(
        brand="Honda",
        model="Civic",
        year=2018,
        price=99,
        repair_cost=900,
        resale_value=17000,
        source="ebay",
        listing_format="AUCTION",
        bid_count=0,
        price_known=True,
        raw_listing_json={"title": "2018 Honda Civic"},
    )
    item: dict = {"id": 1}
    _patch_api_item_resale(item, car)
    assert item["roi_is_preliminary"] is True
    assert item["purchase_price_effective"] > 1000
    assert item["roi"] is not None
