"""Tests for GET /cars/{car_id} detail endpoint."""

from fastapi.testclient import TestClient


def _first_car_id(client: TestClient) -> int:
    res = client.get("/cars", params={"limit": 1})
    assert res.status_code == 200
    items = res.json()["items"]
    assert items, "expected at least one car in inventory"
    return int(items[0]["id"])


def test_car_detail_requires_auth(monkeypatch):
    monkeypatch.delenv("DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    from app.main import app

    with TestClient(app) as bare_client:
        response = bare_client.get("/cars/1")
    assert response.status_code == 401


def test_car_detail_returns_extended_fields(client):
    car_id = _first_car_id(client)
    response = client.get(f"/cars/{car_id}")
    assert response.status_code == 200
    data = response.json()
    assert "item" in data
    item = data["item"]
    assert item["id"] == car_id
    assert "description_html" in item
    assert "is_watched" in item
    assert isinstance(item["is_watched"], bool)
    assert "location" in item
    assert "listing_aspects" in item
    assert isinstance(item["listing_aspects"], list)


def test_car_detail_not_found(client):
    response = client.get("/cars/999999999")
    assert response.status_code == 404


def test_car_detail_sanitized_description(client):
    car_id = _first_car_id(client)
    response = client.get(f"/cars/{car_id}")
    assert response.status_code == 200
    html = response.json()["item"].get("description_html") or ""
    assert "<script" not in html.lower()
