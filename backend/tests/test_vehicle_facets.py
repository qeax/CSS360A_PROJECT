"""Tests for eBay vehicle facet normalization (Make/Model/Year/Mileage)."""

from app.integrations.ebay.parse_item import resolve_listing_mileage, resolve_vehicle_facets


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


def test_resolve_listing_mileage_from_aspects():
    mi = resolve_listing_mileage(
        "Ford Mustang",
        aspects=[
            {"localizedAspectName": "Mileage", "localizedAspectValues": ["52,000 mi"]},
        ],
    )
    assert mi == 52000


def test_facets_from_stored_raw_json_shape():
    """Raw listings use aspects with name/value (not localizedAspectValues)."""
    aspects = [
        {"type": "STRING", "name": "Year", "value": "1967"},
        {"type": "STRING", "name": "Mileage", "value": "43000"},
        {"type": "STRING", "name": "Model", "value": "F-100"},
        {"type": "STRING", "name": "Make", "value": "Ford"},
    ]
    facets = resolve_vehicle_facets(
        "1967 Ford F-100",
        brand_hint="1967",
        model_hint="Ford F-100",
        aspects=aspects,
    )
    assert facets["year"] == 1967
    assert facets["brand"] == "Ford"
    assert facets["model"] == "F-100"
    mi = resolve_listing_mileage("1967 Ford F-100", aspects=aspects)
    assert mi == 43000


def test_parse_item_location_no_us_default():
    from app.integrations.ebay.parse_item import _parse_item_location

    loc = _parse_item_location({})
    assert loc["country"] is None
