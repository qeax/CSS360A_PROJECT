"""Tests for vehicle aspect extraction from eBay localizedAspects snapshots."""

from app.integrations.ebay.parse_item import resolve_listing_mileage
from app.services.vehicle_aspects import (
    aspects_to_display_rows,
    extended_vehicle_fields_from_aspects_json,
    extract_vin_from_aspects_json,
)

MCLAREN_ASPECTS = [
    {"type": "STRING", "name": "Year", "value": "2018"},
    {"type": "STRING", "name": "VIN (Vehicle Identification Number)", "value": "SBM14DCA3JW000312"},
    {"type": "STRING", "name": "Mileage", "value": "2896"},
    {"type": "STRING", "name": "Body Type", "value": "2dr Car"},
    {"type": "STRING", "name": "Drive Type", "value": "RWD"},
    {"type": "STRING", "name": "Engine", "value": "Twin Turbo Premium Unleaded V-8 4.0 L/244"},
    {"type": "STRING", "name": "Fuel Highway", "value": "22"},
    {"type": "STRING", "name": "Fuel City", "value": "15"},
    {"type": "STRING", "name": "Fuel Type", "value": "Gasoline Fuel"},
    {"type": "STRING", "name": "Make", "value": "McLaren"},
    {"type": "STRING", "name": "Model", "value": "720S"},
    {"type": "STRING", "name": "Transmission", "value": "Automatic"},
    {"type": "STRING", "name": "Trim", "value": "LAUNCH EDITION!! Glacier White paint"},
    {"type": "STRING", "name": "Vehicle Title", "value": "Clean"},
]


def test_aspects_to_display_rows_sorted_and_deduped():
    rows = aspects_to_display_rows(MCLAREN_ASPECTS)
    names = [r["name"] for r in rows]
    assert names == sorted(names, key=str.lower)
    assert any(r["name"] == "VIN (Vehicle Identification Number)" for r in rows)
    assert len(rows) == len(MCLAREN_ASPECTS)


def test_extract_vin_from_aspects():
    assert extract_vin_from_aspects_json(MCLAREN_ASPECTS) == "SBM14DCA3JW000312"


def test_extended_vehicle_fields_from_mclaren_example():
    fields = extended_vehicle_fields_from_aspects_json(MCLAREN_ASPECTS)
    assert fields["vin"] == "SBM14DCA3JW000312"
    assert fields["transmission"] == "Automatic"
    assert fields["trim"] == "LAUNCH EDITION!! Glacier White paint"
    assert fields["engine"] == "Twin Turbo Premium Unleaded V-8 4.0 L/244"
    assert fields["fuel_type"] == "Gasoline Fuel"
    assert fields["fuel_city"] == "15"
    assert fields["fuel_highway"] == "22"
    assert fields["drive_type"] == "RWD"
    assert fields["body_style"] == "2dr Car"


def test_resolve_listing_mileage_accepts_low_aspect_mileage():
    assert resolve_listing_mileage(None, aspects=MCLAREN_ASPECTS) == 2896
