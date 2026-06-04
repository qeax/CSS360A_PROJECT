"""Tests for resolving full listing description from stored car data."""

from types import SimpleNamespace

from app.repositories.cars import _listing_description_full


def test_description_full_prefers_db_column():
    car = SimpleNamespace(
        description_full="<p>Full from column</p>",
        raw_listing_json={"description": "<p>From raw</p>"},
    )
    assert _listing_description_full(car) == "<p>Full from column</p>"


def test_description_full_falls_back_to_raw_json():
    car = SimpleNamespace(
        description_full=None,
        raw_listing_json={"description": "<p>Full HTML description</p>"},
    )
    assert _listing_description_full(car) == "<p>Full HTML description</p>"


def test_description_full_empty_when_missing():
    car = SimpleNamespace(description_full=None, raw_listing_json={"title": "No desc"})
    assert _listing_description_full(car) is None
