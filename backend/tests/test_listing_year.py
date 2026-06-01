"""Tests for eBay listing year resolution."""

from app.integrations.ebay.parse_item import resolve_listing_year


def test_resolve_listing_year_classic_from_title():
    y = resolve_listing_year("1967 Ford Mustang Fastback")
    assert y == 1967


def test_resolve_listing_year_no_false_2018_default():
    y = resolve_listing_year("Ford Mustang classic restoration")
    assert y is None


def test_resolve_listing_year_from_aspect():
    aspects = [{"localizedAspectName": "Year", "localizedAspectValues": ["2015"]}]
    y = resolve_listing_year("Used sedan", aspects=aspects)
    assert y == 2015
