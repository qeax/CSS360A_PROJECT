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
    for key in (
        "AZURE_AD_TENANT_ID",
        "AZURE_AD_CLIENT_ID",
        "AZURE_AD_CLIENT_SECRET",
        "AZURE_AD_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)
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


def test_delete_car_requires_auth_without_override(monkeypatch):
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    with TestClient(app) as bare_client:
        response = bare_client.delete("/cars/1")
    assert response.status_code == 401


def test_delete_car_not_found(client):
    response = client.delete("/cars/999999999")
    assert response.status_code == 404


def test_delete_car_removes_row(client):
    list_resp = client.get("/cars", params={"limit": 1})
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    if not items:
        pytest.skip("no cars in inventory to delete")
    car_id = items[0]["id"]

    del_resp = client.delete(f"/cars/{car_id}")
    assert del_resp.status_code == 204

    again = client.get("/cars", params={"limit": 500})
    assert again.status_code == 200
    ids = {c["id"] for c in again.json()["items"]}
    assert car_id not in ids

    missing = client.delete(f"/cars/{car_id}")
    assert missing.status_code == 404


def test_refresh_car_ebay_not_found(client):
    response = client.post("/cars/999999999/ebay-refresh")
    assert response.status_code == 404


def test_refresh_car_ebay_bad_source(client, monkeypatch):
    from app.services.ebay_sync import EbayRefreshError

    def _raise(_db, _car_id):
        raise EbayRefreshError("not_ebay_listing")

    monkeypatch.setattr("app.api.routes.cars.refresh_car_from_ebay", _raise)
    response = client.post("/cars/1/ebay-refresh")
    assert response.status_code == 400
    assert response.json()["detail"] == "not_ebay_listing"


def test_refresh_car_ebay_success(client, monkeypatch):
    list_resp = client.get("/cars", params={"limit": 50})
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    ebay_item = next(
        (
            i
            for i in items
            if (i.get("source") or "").lower() == "ebay" and i.get("external_listing_id")
        ),
        None,
    )
    if not ebay_item:
        pytest.skip("no eBay listing in inventory")

    detail = {
        "itemId": ebay_item["external_listing_id"],
        "title": f"{ebay_item['brand']} {ebay_item['model']}",
        "price": {"value": str(ebay_item["price"]), "currency": "USD"},
        "localizedAspects": [
            {"name": "Make", "value": ebay_item["brand"]},
            {"name": "Model", "value": ebay_item["model"]},
            {"name": "Mileage", "value": "2896"},
            {"name": "VIN (Vehicle Identification Number)", "value": "TESTVIN123456789"},
        ],
        "buyingOptions": ["FIXED_PRICE"],
    }

    from app.integrations.ebay.client import GetItemResult

    class _FakeClient:
        def is_configured(self):
            return True

        def get_item(self, item_id):
            if item_id == ebay_item["external_listing_id"]:
                return GetItemResult.ok(detail)
            return GetItemResult.error()

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())

    response = client.post(f"/cars/{ebay_item['id']}/ebay-refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["item"]["id"] == ebay_item["id"]
    assert body["item"].get("vin") == "TESTVIN123456789"


def test_refresh_car_ebay_listing_gone(client, monkeypatch):
    list_resp = client.get("/cars", params={"limit": 50})
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    ebay_item = next(
        (
            i
            for i in items
            if (i.get("source") or "").lower() == "ebay" and i.get("external_listing_id")
        ),
        None,
    )
    if not ebay_item:
        pytest.skip("no eBay listing in inventory")

    from app.integrations.ebay.client import GetItemResult

    class _FakeClient:
        def is_configured(self):
            return True

        def get_item(self, item_id):
            if item_id == ebay_item["external_listing_id"]:
                return GetItemResult.not_found(404)
            return GetItemResult.error()

    monkeypatch.setattr("app.services.ebay_sync.get_ebay_client", lambda: _FakeClient())

    response = client.post(f"/cars/{ebay_item['id']}/ebay-refresh")
    assert response.status_code == 200
    body = response.json()
    assert body.get("deleted") is True
    assert body.get("id") == ebay_item["id"]

    again = client.get("/cars", params={"limit": 500})
    assert again.status_code == 200
    ids = {c["id"] for c in again.json()["items"]}
    assert ebay_item["id"] not in ids
