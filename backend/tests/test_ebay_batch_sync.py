"""Tests for staged eBay batch sync (search pool, enrich waves of 50)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — register all tables on Base
from app.db import Base
from app.models.car import Car
from app.models.ebay_sync_batch import EbaySyncBatch
from app.services.ebay_sync import (
    _get_active_batch,
    _save_batch,
    continue_ebay_batch,
    reset_sync_cooldown_for_tests,
    search_listings_batch,
    start_ebay_batch,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _search_rows(n: int, *, prefix: str = "v1") -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "external_listing_id": f"{prefix}|{i}|0",
                "title": f"2018 Test Car {i}",
                "price": 10000 + i,
                "source": "ebay",
            }
        )
    return rows


def _detail_for(row: dict) -> dict:
    return {
        "itemId": row["external_listing_id"],
        "title": row["title"],
        "price": {"value": str(row["price"]), "currency": "USD"},
        "localizedAspects": [
            {"name": "Make", "value": "Honda"},
            {"name": "Model", "value": "Civic"},
            {"name": "Year", "value": "2018"},
        ],
        "buyingOptions": ["FIXED_PRICE"],
    }


def test_search_listings_batch_filters_vehicles(monkeypatch):
    monkeypatch.setattr(
        "app.services.ebay_sync.search_listings_batch",
        lambda **_kwargs: _search_rows(3),
    )
    rows = search_listings_batch(query="car")
    assert len(rows) == 3


def test_start_batch_enriches_first_wave_only(monkeypatch, db):
    reset_sync_cooldown_for_tests()
    summaries = _search_rows(5, prefix="batch")

    class _FakeClient:
        def is_configured(self) -> bool:
            return True

        def search_listings(self, query, limit=None, max_price=None):
            return summaries[:limit]

        def enrich_summaries(self, rows, *, max_items=None):
            out = []
            for r in rows:
                if r["external_listing_id"].endswith("|2|0"):
                    out.append(None)
                else:
                    merged = dict(r)
                    merged["raw_listing_json"] = _detail_for(r)
                    merged["brand"] = "Honda"
                    merged["model"] = "Civic"
                    merged["year"] = 2018
                    out.append(merged)
            return out

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())
    monkeypatch.setattr("app.services.ebay_sync.ebay_wave_size", lambda: 3)
    monkeypatch.setattr("app.services.ebay_sync.ebay_batch_size", lambda: 5)
    monkeypatch.setattr(
        "app.services.ebay_sync.search_listings_batch",
        lambda **_kwargs: summaries,
    )

    stats = start_ebay_batch(db, user_id=1, q="car", enforce_cooldown=False)
    assert stats["status"] == "ok"
    assert stats["synced"] == 2
    assert len(stats["wave_items"]) == 2

    cars = db.scalars(select(Car)).all()
    assert len(cars) == 2

    batch = db.execute(select(EbaySyncBatch)).scalar_one()
    assert batch.cursor == 3
    assert stats["ebay_batch"]["pending_in_batch"] == 2


def test_continue_batch_second_wave(monkeypatch, db):
    reset_sync_cooldown_for_tests()
    summaries = _search_rows(4, prefix="cont")

    class _FakeClient:
        def is_configured(self) -> bool:
            return True

        def search_listings(self, query, limit=None, max_price=None):
            return summaries[:limit]

        def enrich_summaries(self, rows, *, max_items=None):
            return [
                {
                    **r,
                    "raw_listing_json": _detail_for(r),
                    "brand": "Honda",
                    "model": "Civic",
                    "year": 2018,
                }
                for r in rows
            ]

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())
    monkeypatch.setattr("app.services.ebay_sync.ebay_wave_size", lambda: 2)
    monkeypatch.setattr("app.services.ebay_sync.ebay_batch_size", lambda: 4)
    monkeypatch.setattr(
        "app.services.ebay_sync.search_listings_batch",
        lambda **_kwargs: summaries,
    )

    start_ebay_batch(db, user_id=2, q="car", enforce_cooldown=False)
    stats = continue_ebay_batch(db, user_id=2, q="car")
    assert stats["status"] == "ok"
    assert stats["synced"] == 2
    assert len(db.scalars(select(Car)).all()) == 4
    assert stats["ebay_batch"]["pending_in_batch"] == 0


def test_get_active_batch_handles_naive_expires_at(db):
    """MariaDB often returns naive datetimes even for DateTime(timezone=True)."""
    _save_batch(
        db,
        user_id=1,
        search_key="mazda",
        search_query="mazda",
        summaries=[],
    )
    batch = db.execute(select(EbaySyncBatch)).scalar_one()
    batch.expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    db.commit()

    assert _get_active_batch(db, 1, "mazda") is not None

    batch.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
    db.commit()

    assert _get_active_batch(db, 1, "mazda") is None
