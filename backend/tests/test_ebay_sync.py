"""Tests for eBay → DB upsert (hybrid inventory)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.integrations.ebay.inventory import _default_ebay_query
from app.models import EbaySyncBatch  # noqa: F401 — register table
from app.models.car import Car
from app.models.car_satellite import CarLocation, CarMedia
from app.services.ebay_sync import (
    build_ebay_search_query,
    reset_sync_cooldown_for_tests,
    sync_ebay_inventory,
    upsert_ebay_listing,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _sample_listing(
    ext_id: str = "v1|100|0",
    *,
    price: float = 15000,
    title: str = "2018 Honda Civic LX Sedan",
    year: int = 2018,
) -> dict:
    return {
        "external_listing_id": ext_id,
        "title": title,
        "price": price,
        "condition": "Used",
        "vehicle_title": "Clean",
        "listing_format": "BUY_IT_NOW",
        "listing_url": "https://www.ebay.com/itm/100",
        "image_url": "https://i.ebayimg.com/x.jpg",
        "image_urls": ["https://i.ebayimg.com/x.jpg"],
        "location": {"city": "Portland", "region": "OR", "country": "United States"},
        "delivery": {"ship_to_home": True, "local_pickup": False, "in_store_pickup": False},
        "seller_username": "dealer_a",
        "mileage": 52000,
        "brand": "Honda",
        "model": "Civic",
        "year": year,
        "aspects_json": [
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Sedan"]},
        ],
        "source": "ebay",
    }


def test_build_ebay_search_query_short_uses_default():
    default_q = _default_ebay_query()
    assert build_ebay_search_query(q="ab") == default_q
    assert build_ebay_search_query(q=None) == default_q


def test_build_ebay_search_query_ignores_makes():
    q = build_ebay_search_query(q="honda civic")
    assert q == "honda civic"
    assert build_ebay_search_query(q="ab") == _default_ebay_query()


def test_upsert_ebay_listing_insert(db):
    car = upsert_ebay_listing(
        db,
        _sample_listing(
            title="1967 Ford Mustang",
            year=1967,
        ),
    )
    db.commit()
    assert car is not None
    assert car.id is not None
    assert car.source == "ebay"
    assert car.external_listing_id == "v1|100|0"
    assert car.year == 1967
    assert car.repair_cost >= 0
    assert car.resale_value > car.price

    loc = db.get(CarLocation, car.id)
    assert loc is not None
    assert loc.city == "Portland"

    media = db.scalars(select(CarMedia).where(CarMedia.car_id == car.id)).all()
    assert len(media) == 1


def test_upsert_ebay_listing_unknown_price(db):
    listing = _sample_listing()
    listing["price"] = None
    car = upsert_ebay_listing(db, listing)
    db.commit()
    assert car is not None
    assert car.price_known is False
    assert car.price == 0.0


def test_upsert_ebay_listing_updates_duplicate(db):
    upsert_ebay_listing(db, _sample_listing(price=15000))
    db.commit()
    upsert_ebay_listing(db, _sample_listing(price=16000))
    db.commit()
    rows = db.scalars(select(Car).where(Car.external_listing_id == "v1|100|0")).all()
    assert len(rows) == 1
    assert rows[0].price == 16000


def test_sync_cooldown(monkeypatch, db):
    monkeypatch.setenv("EBAY_SYNC_MIN_INTERVAL_SEC", "60")
    reset_sync_cooldown_for_tests()

    calls = {"n": 0}

    def fake_search(**_kwargs):
        calls["n"] += 1
        return [_sample_listing("v1|200|0")]

    monkeypatch.setattr(
        "app.services.ebay_sync.search_listings_batch",
        fake_search,
    )

    class _FakeClient:
        sandbox = False

        def is_configured(self) -> bool:
            return True

        def enrich_summaries(self, rows, *, max_items=None):
            if not rows:
                return []
            return [{**rows[0], "raw_listing_json": {"itemId": "v1|200|0"}}]

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())

    sync_ebay_inventory(db, user_id=1, q="honda", enforce_cooldown=True)
    assert calls["n"] == 1

    from app.services.ebay_sync import EbaySyncCooldownError, check_sync_cooldown

    with pytest.raises(EbaySyncCooldownError):
        check_sync_cooldown(1)


def test_sync_fetch_failure_returns_failed_status(monkeypatch, db):
    reset_sync_cooldown_for_tests()

    def boom(**_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.services.ebay_sync.search_listings_batch", boom)

    class _FakeClient:
        sandbox = False

        def is_configured(self) -> bool:
            return True

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())

    stats = sync_ebay_inventory(db, user_id=2, q="honda", enforce_cooldown=False)
    assert stats["status"] == "failed"
    assert stats["synced"] == 0
    assert "network down" in stats.get("error", "")


def test_sync_success_includes_ok_status(monkeypatch, db):
    reset_sync_cooldown_for_tests()

    listing = _sample_listing("v1|300|0")
    listing["raw_listing_json"] = {"itemId": "v1|300|0"}

    monkeypatch.setattr(
        "app.services.ebay_sync.search_listings_batch",
        lambda **_kwargs: [listing],
    )

    class _FakeClient:
        sandbox = False

        def is_configured(self) -> bool:
            return True

        def enrich_summaries(self, rows, *, max_items=None):
            return [rows[0] if rows else None]

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())

    stats = sync_ebay_inventory(db, user_id=3, q="honda", enforce_cooldown=False)
    assert stats["status"] == "ok"
    assert stats["synced"] == 1
