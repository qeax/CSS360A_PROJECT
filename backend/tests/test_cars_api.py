import pytest
from fastapi.testclient import TestClient

from app.integrations.ebay.client import reset_ebay_client
from app.main import app
from app.repositories.cars import _normalize_listing_format, invalidate_in_memory_demo_cache


def test_normalize_listing_format_accepts_offer_not_auction():
    """Regression: substring 'AUCTION' appears inside 'ACCEPTS_OFFER'."""
    assert _normalize_listing_format("ACCEPTS_OFFER") == "ACCEPTS_OFFER"
    assert _normalize_listing_format("accepts_offer") == "ACCEPTS_OFFER"


def test_cars_requires_auth_without_override(monkeypatch):
    """Real app without dependency overrides (does not use the ``client`` fixture)."""
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    with TestClient(app) as bare_client:
        response = bare_client.get("/cars")
    assert response.status_code == 401


def test_cars_allows_dev_auth_bypass(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    with TestClient(app) as bare_client:
        response = bare_client.get("/cars")
    assert response.status_code == 200


def test_cars_returns_paginated_payload_with_auth(client):
    response = client.get("/cars")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data and "total" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


def test_cars_sort_by_net_profit(client):
    response = client.get("/cars", params={"sort_by": "net_profit", "sort_order": "desc"})
    assert response.status_code == 200
    data = response.json()
    items = data["items"]
    if len(items) >= 2:
        assert items[0]["net_profit"] >= items[1]["net_profit"]


def test_cars_pagination_limit_offset(client):
    response = client.get("/cars", params={"limit": 5, "offset": 0})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5
    assert data["total"] >= len(data["items"])
    if data["total"] > 5:
        page2 = client.get("/cars", params={"limit": 5, "offset": 5})
        assert page2.status_code == 200
        d2 = page2.json()
        assert len(d2["items"]) <= 5


def test_cars_meta_returns_bounds(client):
    response = client.get("/cars/meta")
    assert response.status_code == 200
    data = response.json()
    assert "min_price" in data
    assert "max_price" in data
    assert "min_year" in data
    assert "max_year" in data
    assert "min_mileage" in data
    assert "max_mileage" in data
    assert "slider_defaults" in data
    assert data["max_year"] > data["min_year"]
    assert data["max_price"] > data["min_price"]
    assert data["max_mileage"] > data["min_mileage"]
    assert "makes" in data
    assert "vehicle_titles" in data
    assert "countries" in data
    assert "location_anchors" in data


def test_cars_q_extremely_unlikely_token(client):
    response = client.get("/cars", params={"q": "zzzzzznotfoundtoken99999"})
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_cars_items_include_vehicle_title_and_drive(client):
    response = client.get("/cars", params={"limit": 3})
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert "vehicle_title" in item
        assert "drive_type" in item


def test_cars_demo_images_present(client):
    response = client.get("/cars", params={"limit": 20})
    assert response.status_code == 200
    items = response.json()["items"]
    if not items:
        pytest.skip("no cars")
    for item in items:
        urls = item.get("images") or ([item["image_url"]] if item.get("image_url") else [])
        assert urls, f"car {item.get('id')} has no images"
        for url in urls:
            assert url.startswith("https://")


def test_cars_filter_makes(client):
    meta = client.get("/cars/meta").json()
    makes = meta.get("makes") or []
    if not makes:
        pytest.skip("no makes in meta")
    pick = next((m for m in makes if m.lower() == "toyota"), makes[0])
    response = client.get("/cars", params={"makes": [pick]})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["brand"].lower() == pick.lower()


def test_cars_filter_vehicle_titles(client):
    meta = client.get("/cars/meta").json()
    titles = meta.get("vehicle_titles") or []
    if not titles:
        pytest.skip("no vehicle_titles in meta")
    pick = titles[0]
    response = client.get("/cars", params={"vehicle_titles": [pick]})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert (item.get("vehicle_title") or "").lower() == pick.lower()


def test_cars_filter_mileage_narrows_results(client):
    one = client.get("/cars", params={"limit": 1}).json()
    if not one["items"]:
        pytest.skip("no cars")
    m = one["items"][0].get("mileage")
    if m is None:
        pytest.skip("car has no mileage")
    m = int(m)
    r = client.get("/cars", params={"min_mileage": m, "max_mileage": m})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item.get("mileage") is not None
        assert int(item["mileage"]) == m


def test_demo_auction_listing_has_bids_and_end_time(client):
    response = client.get("/cars", params={"listing_formats": ["AUCTION"], "limit": 5})
    assert response.status_code == 200
    items = response.json()["items"]
    if not items:
        pytest.skip("no auction listings in demo catalog")
    car = items[0]
    assert car.get("listing_format") == "AUCTION"
    assert car.get("bid_count") is not None
    assert car.get("listing_ends_at")


def test_cars_uses_demo_when_ebay_not_configured(client, monkeypatch):
    monkeypatch.setenv("INVENTORY_MODE", "auto")
    monkeypatch.setenv("DEMO_IN_MEMORY_WHEN_EMPTY", "true")
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    reset_ebay_client()
    invalidate_in_memory_demo_cache()
    response = client.get("/cars", params={"limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any((i.get("source") or "") == "demo" for i in data["items"])


def test_cars_empty_when_ebay_only_and_no_credentials(client, monkeypatch):
    monkeypatch.setenv("INVENTORY_MODE", "ebay_only")
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    reset_ebay_client()
    invalidate_in_memory_demo_cache()
    response = client.get("/cars", params={"limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_cars_q_soft_partial_brand_model(client):
    """Single typo in brand still matches via token OR fuzzy brand+model."""
    response = client.get("/cars", params={"q": "toyta camry"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(
        "toyota" in (i["brand"] or "").lower() and "camry" in (i["model"] or "").lower()
        for i in data["items"]
    )
