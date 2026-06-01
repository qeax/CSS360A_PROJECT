"""Search query normalization and DB relevance matching."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.car import Car
from app.repositories.cars import _car_matches_q_soft, apply_filters, load_inventory_cars_from_db
from app.services.search_query import meaningful_query_tokens, normalize_search_key


def test_normalize_search_key_collapses_whitespace():
    assert normalize_search_key("  Luxury   Cars  ") == "luxury cars"


def test_meaningful_query_tokens_drop_generic_car_words():
    assert meaningful_query_tokens("luxury cars") == ["luxury"]
    assert meaningful_query_tokens("honda civic") == ["honda", "civic"]


def test_car_matches_requires_all_meaningful_tokens():
    assert _car_matches_q_soft(
        brand="BMW",
        model="7 Series",
        year=2019,
        city="",
        region="",
        country="",
        listing_format="AUCTION",
        condition="Used",
        body_style="Sedan",
        vehicle_title="Clean",
        drive_type="RWD",
        description_summary="luxury sedan executive",
        tokens=["luxury"],
    )
    assert not _car_matches_q_soft(
        brand="Honda",
        model="Civic",
        year=2018,
        city="",
        region="",
        country="",
        listing_format="BUY_IT_NOW",
        condition="Used",
        body_style="Sedan",
        vehicle_title="Clean",
        drive_type="FWD",
        description_summary="economy commuter",
        tokens=["luxury"],
    )


def _ebay_car(
    *,
    ext_id: str,
    brand: str,
    model: str,
    summary: str,
    ingest_key: str | None,
    price_known: bool = True,
):
    return SimpleNamespace(
        id=1,
        brand=brand,
        model=model,
        year=2019,
        price=20000.0,
        repair_cost=1000.0,
        resale_value=24000.0,
        mileage=40000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="AUCTION",
        listing_ends_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        listing_terms=SimpleNamespace(ship_to_home=True, local_pickup=False, in_store_pickup=False),
        location=SimpleNamespace(
            country="United States",
            region="CA",
            city="LA",
            postal_code_masked=None,
            latitude=None,
            longitude=None,
        ),
        external_seller=SimpleNamespace(username="s"),
        aspect_snapshots=[],
        image_url=None,
        media=[],
        description_summary=summary,
        source="ebay",
        external_listing_id=ext_id,
        bid_count=2,
        ingest_search_key=ingest_key,
        price_known=price_known,
    )


def _apply(cars, q: str, **kwargs):
    return apply_filters(
        cars,
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
        q=q,
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
        **kwargs,
    )


def test_exclude_unknown_price_filter():
    no_price = _ebay_car(
        ext_id="e0",
        brand="Ford",
        model="Mustang",
        summary="ford mustang",
        ingest_key="ford",
        price_known=False,
    )
    priced = _ebay_car(
        ext_id="e1",
        brand="Ford",
        model="F-150",
        summary="ford truck",
        ingest_key="ford",
    )
    out = _apply([no_price, priced], "ford", exclude_unknown_price=True)
    assert len(out) == 1
    assert out[0]["price_known"] is True


def test_apply_filters_scopes_ebay_by_ingest_search_key():
    luxury = _ebay_car(
        ext_id="e1",
        brand="Mercedes-Benz",
        model="S-Class",
        summary="luxury flagship",
        ingest_key="luxury cars",
    )
    honda = _ebay_car(
        ext_id="e2",
        brand="Honda",
        model="Civic",
        summary="honda civic economy",
        ingest_key="honda civic",
    )
    out = _apply([luxury, honda], "luxury cars")
    assert len(out) == 1
    assert out[0]["brand"] == "Mercedes-Benz"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_load_inventory_scoped_to_search_key(db):
    db.add(
        Car(
            brand="BMW",
            model="X5",
            year=2020,
            price=30000.0,
            repair_cost=2000.0,
            resale_value=35000.0,
            source="ebay",
            external_listing_id="ebay-lux-1",
            ingest_search_key="luxury cars",
        )
    )
    db.add(
        Car(
            brand="Toyota",
            model="Corolla",
            year=2018,
            price=12000.0,
            repair_cost=800.0,
            resale_value=14000.0,
            source="ebay",
            external_listing_id="ebay-honda-1",
            ingest_search_key="honda civic",
        )
    )
    db.add(
        Car(
            brand="Mercedes-Benz",
            model="S-Class",
            year=2019,
            price=40000.0,
            repair_cost=2500.0,
            resale_value=48000.0,
            source="ebay",
            external_listing_id="ebay-legacy-1",
            ingest_search_key=None,
            description_summary="luxury sedan",
        )
    )
    db.commit()
    rows = load_inventory_cars_from_db(db, search_key="luxury cars")
    brands = {r.brand for r in rows}
    assert "BMW" in brands
    assert "Mercedes-Benz" in brands
    assert "Toyota" not in brands
