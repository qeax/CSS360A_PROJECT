from datetime import datetime, timezone
from types import SimpleNamespace

from app.integrations.ebay.inventory import ebay_listing_dict_to_car_view, resolve_listing_url
from app.integrations.ebay.parse_item import _parse_mileage, merge_search_summary, parse_get_item
from app.integrations.ebay.vehicle_filter import is_likely_vehicle_listing
from app.repositories.cars import (
    _MILEAGE_BOUNDS_DEFAULT_MAX,
    _MILEAGE_BOUNDS_DEFAULT_MIN,
    _demo_catalog_slider_bounds,
    _listing_ends_at_iso,
    _resolve_mileage_meta_bounds,
    apply_filters,
)


def test_parse_get_item_extracts_vehicle_facets():
    item = {
        "itemId": "v1|99|0",
        "title": "2019 Toyota Camry SE",
        "itemWebUrl": "https://www.ebay.com/itm/99",
        "price": {"value": "18500", "currency": "USD"},
        "condition": "Used",
        "buyingOptions": ["FIXED_PRICE"],
        "bidCount": 0,
        "localizedAspects": [
            {"localizedAspectName": "Make", "localizedAspectValues": ["Toyota"]},
            {"localizedAspectName": "Model", "localizedAspectValues": ["Camry"]},
            {"localizedAspectName": "Year", "localizedAspectValues": ["2019"]},
            {"localizedAspectName": "Mileage", "localizedAspectValues": ["42,150 mi"]},
            {"localizedAspectName": "Drive Type", "localizedAspectValues": ["FWD"]},
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Sedan"]},
            {"localizedAspectName": "Title", "localizedAspectValues": ["Clean"]},
        ],
        "itemLocation": {
            "address": {"city": "Seattle", "stateOrProvince": "WA", "country": "US"},
            "postalCode": "98101",
        },
        "estimatedAvailabilities": [
            {"deliveryOptions": ["SHIP_TO_HOME", "SELLER_ARRANGED_LOCAL_PICKUP"]}
        ],
        "image": {"imageUrl": "https://i.ebayimg.com/a.jpg"},
        "additionalImages": [{"imageUrl": "https://i.ebayimg.com/b.jpg"}],
        "seller": {"username": "dealer_test"},
        "shortDescription": "Well maintained Camry.",
    }
    parsed = parse_get_item(item)
    assert parsed["brand"] == "Toyota"
    assert parsed["model"] == "Camry"
    assert parsed["year"] == 2019
    assert parsed["mileage"] == 42150
    assert parsed["vehicle_title"] == "Clean"
    assert parsed["listing_format"] == "BUY_IT_NOW"
    assert parsed["seller_username"] == "dealer_test"
    assert len(parsed["image_urls"]) == 2
    assert parsed["delivery"]["ship_to_home"] is True
    assert parsed["delivery"]["local_pickup"] is True


def test_merge_search_summary_prefers_get_item():
    search = {
        "external_listing_id": "v1|1|0",
        "title": "2018 Honda Civic",
        "price": "17000",
        "location_city": "Portland",
        "source": "ebay",
    }
    detail = {
        "itemId": "v1|1|0",
        "title": "2018 Honda Civic LX",
        "localizedAspects": [
            {"localizedAspectName": "Make", "localizedAspectValues": ["Honda"]},
            {"localizedAspectName": "Model", "localizedAspectValues": ["Civic"]},
            {"localizedAspectName": "Year", "localizedAspectValues": ["2018"]},
        ],
        "price": {"value": "16950", "currency": "USD"},
    }
    merged = merge_search_summary(search, detail)
    assert merged["brand"] == "Honda"
    assert merged["model"] == "Civic"
    assert float(merged["price"]) == 16950.0


def test_ebay_listing_dict_to_car_view_parses_title():
    item = {
        "external_listing_id": "v1|123|0",
        "title": "2019 Toyota Camry SE Sedan 4-Door",
        "price": 18500,
        "currency": "USD",
        "condition": "Used",
        "location": {"city": "Seattle", "region": "WA", "country": "United States"},
        "mileage": 42150,
        "vehicle_title": "Clean",
        "listing_format": "BUY_IT_NOW",
        "listing_url": "https://www.ebay.com/itm/123",
        "image_urls": ["https://i.ebayimg.com/sample.jpg"],
        "aspects_json": [
            {"localizedAspectName": "Drive Type", "localizedAspectValues": ["FWD"]},
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Sedan"]},
        ],
        "delivery": {"ship_to_home": True, "local_pickup": True, "in_store_pickup": False},
        "seller_username": "dealer1",
        "source": "ebay",
    }
    view = ebay_listing_dict_to_car_view(item, 1)
    assert view is not None
    assert view.brand == "Toyota"
    assert "Camry" in view.model
    assert view.year == 2019
    assert view.mileage == 42150
    assert view.vehicle_title == "Clean"
    assert view.external_seller.username == "dealer1"


def test_ebay_listing_dict_skips_error_rows():
    assert ebay_listing_dict_to_car_view({"error": "fail"}, 1) is None


def test_vehicle_filter_accepts_year_in_title_without_mileage_keyword():
    assert is_likely_vehicle_listing(
        {"title": "2009 Honda Accord LX", "price": 7500, "brand": "Honda", "model": "Accord"}
    )


def test_parse_mileage_ignores_year_and_engine_displacement():
    assert _parse_mileage("2019 Honda Accord 2.5L V6") is None
    assert _parse_mileage("1.5T turbo sedan") is None
    assert _parse_mileage("2018 Ford F-150 85,000 miles") == 85000
    assert _parse_mileage("42k miles") == 42000


def test_ebay_meta_uses_demo_catalog_slider_bounds():
    from types import SimpleNamespace

    from app.repositories.cars import _year_slider_bounds

    cars = [
        SimpleNamespace(price=5200.0, year=2009, mileage=None, id=1),
        SimpleNamespace(price=5300.0, year=2012, mileage=None, id=2),
    ]
    price_bounds, mileage_bounds = _demo_catalog_slider_bounds()
    assert price_bounds[0] == 0.0
    assert price_bounds[1] - price_bounds[0] > 5000
    assert _year_slider_bounds() == (2000, 2025)
    assert mileage_bounds[1] - mileage_bounds[0] >= 10000
    mi_lo, mi_hi = _resolve_mileage_meta_bounds(cars, inventory_source="ebay")
    assert mi_lo == mileage_bounds[0]
    assert mi_hi == mileage_bounds[1]


def test_resolve_mileage_meta_bounds_ignores_implausible_odometer():
    from types import SimpleNamespace

    cars = [
        SimpleNamespace(mileage=1500, id=1),
        SimpleNamespace(mileage=2500, id=2),
    ]
    lo, hi = _resolve_mileage_meta_bounds(cars, inventory_source="database")
    assert lo == _MILEAGE_BOUNDS_DEFAULT_MIN
    assert hi == _MILEAGE_BOUNDS_DEFAULT_MAX


def test_resolve_mileage_meta_bounds_falls_back_when_no_odometer():
    from types import SimpleNamespace

    cars = [
        SimpleNamespace(mileage=None, id=1),
        SimpleNamespace(mileage=None, id=2),
    ]
    lo, hi = _resolve_mileage_meta_bounds(cars, inventory_source="database")
    assert lo == _MILEAGE_BOUNDS_DEFAULT_MIN
    assert hi == _MILEAGE_BOUNDS_DEFAULT_MAX


def test_resolve_mileage_meta_bounds_uses_listing_values():
    from types import SimpleNamespace

    cars = [
        SimpleNamespace(mileage=9200, id=1),
        SimpleNamespace(mileage=141500, id=2),
    ]
    lo, hi = _resolve_mileage_meta_bounds(cars, inventory_source="database")
    assert lo == 9200
    assert hi == 141500


def test_resolve_listing_url_from_ebay_item_id():
    assert resolve_listing_url("v1|1234567890|0", None) == "https://www.ebay.com/itm/1234567890"
    assert resolve_listing_url(
        "v1|99|0",
        "https://www.ebay.com/itm/99",
    ) == "https://www.ebay.com/itm/99"
    assert (
        resolve_listing_url("v1|99|0", None, sandbox=True)
        == "https://sandbox.ebay.com/itm/99"
    )


def test_listing_ends_at_iso_accepts_string_and_datetime():
    iso = "2026-06-01T00:00:00+00:00"
    assert _listing_ends_at_iso(iso) == iso
    dt = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert _listing_ends_at_iso(dt) == dt.isoformat()


def test_apply_filters_handles_ebay_string_listing_ends_at():
    """eBay in-memory cars store listing_ends_at as ISO str, not datetime."""
    car = SimpleNamespace(
        brand="Toyota",
        model="Camry",
        year=2019,
        price=10000.0,
        repair_cost=800.0,
        resale_value=12000.0,
        mileage=50000,
        condition="Used",
        vehicle_title="Clean",
        listing_format="BUY_IT_NOW",
        listing_ends_at="2026-06-01T00:00:00+00:00",
        listing_terms=SimpleNamespace(
            ship_to_home=True, local_pickup=False, in_store_pickup=False
        ),
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
        source="ebay",
    )
    out = apply_filters(
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
        countries=["United States"],
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
    )
    assert len(out) == 1
    assert out[0]["listing_ends_at"] == "2026-06-01T00:00:00+00:00"
