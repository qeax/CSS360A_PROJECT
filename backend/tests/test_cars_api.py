from fastapi.testclient import TestClient

from app.main import app


def test_cars_requires_auth_without_override():
    """Real app without dependency overrides (does not use the ``client`` fixture)."""
    with TestClient(app) as bare_client:
        response = bare_client.get("/cars")
        assert response.status_code == 401


def test_cars_returns_list_with_auth(client):
    response = client.get("/cars")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_cars_sort_by_net_profit(client):
    response = client.get("/cars", params={"sort_by": "net_profit", "sort_order": "desc"})
    assert response.status_code == 200
    data = response.json()
    if len(data) >= 2:
        assert data[0]["net_profit"] >= data[1]["net_profit"]
