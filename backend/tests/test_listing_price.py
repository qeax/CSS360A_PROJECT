"""eBay listing price parsing and unknown-price flip metrics."""

from app.integrations.ebay.price import parse_listing_price
from app.repositories.cars import sort_car_dicts_inplace
from app.services.flip import calculate_flip_score, flip_metrics_unknown


def test_parse_listing_price_valid():
    assert parse_listing_price(18500) == (18500.0, True)
    assert parse_listing_price("12000.5") == (12000.5, True)


def test_parse_listing_price_missing_or_invalid():
    assert parse_listing_price(None) == (0.0, False)
    assert parse_listing_price(0) == (0.0, False)
    assert parse_listing_price(-1) == (0.0, False)
    assert parse_listing_price("n/a") == (0.0, False)


def test_flip_metrics_unknown_when_price_unknown():
    assert flip_metrics_unknown() == flip_metrics_unknown()


def test_sort_roi_desc_puts_unknown_price_last():
    rows = [
        {"price_known": False, "roi": None, "net_profit": None, "price": 0},
        {"price_known": True, "roi": 5.0, "net_profit": 100, "price": 10000},
        {"price_known": True, "roi": 15.0, "net_profit": 500, "price": 12000},
    ]
    sort_car_dicts_inplace(rows, "roi", "desc")
    assert rows[0]["roi"] == 15.0
    assert rows[1]["roi"] == 5.0
    assert rows[2]["price_known"] is False
