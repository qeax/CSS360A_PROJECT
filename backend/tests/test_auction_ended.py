"""Ended auction detection, filtering, and mark_expired_auctions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.car import Car
from app.repositories.cars import (
    apply_filters,
    auction_has_ended,
    is_auction_listing,
    mark_expired_auctions,
)


def _auction_car(*, ends_at: datetime, car_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=car_id,
        brand="Toyota",
        model="Camry",
        year=2019,
        price=10000.0,
        repair_cost=800.0,
        resale_value=12000.0,
        mileage=50000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="AUCTION",
        listing_ends_at=ends_at,
        listing_terms=SimpleNamespace(ship_to_home=True, local_pickup=False, in_store_pickup=False),
        location=SimpleNamespace(
            country="United States",
            region="WA",
            city="Seattle",
            postal_code_masked=None,
            latitude=None,
            longitude=None,
        ),
        external_seller=SimpleNamespace(username="seller1"),
        aspect_snapshots=[],
        image_url=None,
        media=[],
        description_summary="2019 Toyota Camry",
        source="demo",
        external_listing_id="demo-auction-1",
        bid_count=3,
    )


def _apply(car, *, exclude_ended_auctions: bool = True):
    return apply_filters(
        [car],
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
        countries=None,
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
        exclude_ended_auctions=exclude_ended_auctions,
    )


def test_is_auction_listing_and_ended():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    future = now + timedelta(hours=5)
    past = now - timedelta(hours=1)
    active = _auction_car(ends_at=future)
    ended = _auction_car(ends_at=past)
    assert is_auction_listing(active)
    assert not auction_has_ended(active, now=now)
    assert auction_has_ended(ended, now=now)


def test_apply_filters_hides_ended_auctions_by_default():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ended = _auction_car(ends_at=now - timedelta(hours=2))
    assert _apply(ended, exclude_ended_auctions=True) == []


def test_apply_filters_shows_ended_when_excluded_flag_false():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ended = _auction_car(ends_at=now - timedelta(hours=2))
    out = _apply(ended, exclude_ended_auctions=False)
    assert len(out) == 1
    assert out[0]["auction_ended"] is True


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_mark_expired_auctions_sets_column(db):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    car = Car(
        brand="Ford",
        model="F-150",
        year=2018,
        price=15000.0,
        repair_cost=1000.0,
        resale_value=18000.0,
        source="ebay",
        external_listing_id="ebay-ended-1",
        listing_format="AUCTION",
        listing_ends_at=now - timedelta(hours=3),
    )
    db.add(car)
    db.commit()
    n = mark_expired_auctions(db, now=now)
    db.commit()
    assert n == 1
    row = db.execute(select(Car).where(Car.external_listing_id == "ebay-ended-1")).scalar_one()
    assert row.auction_ended_at is not None


def test_cars_api_exclude_ended_auctions_false(client, monkeypatch):
    monkeypatch.setenv("INVENTORY_MODE", "auto")
    monkeypatch.setenv("DEMO_IN_MEMORY_WHEN_EMPTY", "true")
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    from app.integrations.ebay.client import reset_ebay_client
    from app.repositories.cars import invalidate_in_memory_demo_cache

    reset_ebay_client()
    invalidate_in_memory_demo_cache()

    hidden = client.get("/cars", params={"listing_formats": ["AUCTION"], "limit": 50})
    assert hidden.status_code == 200
    hidden_ids = {i["id"] for i in hidden.json()["items"] if i.get("auction_ended")}

    shown = client.get(
        "/cars",
        params={"listing_formats": ["AUCTION"], "limit": 50, "exclude_ended_auctions": "false"},
    )
    assert shown.status_code == 200
    shown_ended = [i for i in shown.json()["items"] if i.get("auction_ended")]
    if not shown_ended:
        pytest.skip("no ended demo auctions in catalog")
    assert any(i["id"] not in hidden_ids for i in shown_ended)
