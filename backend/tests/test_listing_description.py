"""Tests for resolving full listing description from stored car data."""

from types import SimpleNamespace

from app.repositories.cars import _listing_description_full, _listing_title


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


def test_description_full_prefers_longer_raw_json():
    short = "Short summary only."
    long_html = "<!DOCTYPE html><html><body><p>Full eBay HTML document</p></body></html>"
    car = SimpleNamespace(
        description_full=short,
        raw_listing_json={"description": long_html},
    )
    assert _listing_description_full(car) == long_html


def test_listing_title_prefers_raw_title():
    car = SimpleNamespace(
        description_summary="Short fallback title",
        raw_listing_json={"title": "2020 BMW M340i xDrive Sedan Fully Loaded"},
    )
    assert _listing_title(car) == "2020 BMW M340i xDrive Sedan Fully Loaded"
