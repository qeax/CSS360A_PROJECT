"""Tests for eBay vehicle facet normalization (Make/Model/Year)."""

from app.integrations.ebay.parse_item import resolve_vehicle_facets


def test_year_in_make_aspect_moves_to_year():
    facets = resolve_vehicle_facets(
        "1967 Ford Mustang Fastback",
        aspects=[
            {"localizedAspectName": "Make", "localizedAspectValues": ["1967"]},
            {"localizedAspectName": "Model", "localizedAspectValues": ["Mustang"]},
        ],
    )
    assert facets["year"] == 1967
    assert facets["brand"] != "1967"
    assert "1967" not in (facets["brand"] or "")
    assert facets["model"] == "Mustang"


def test_parse_item_location_no_us_default():
    from app.integrations.ebay.parse_item import _parse_item_location

    loc = _parse_item_location({})
    assert loc["country"] is None
