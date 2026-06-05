"""Tests for watchlist API."""

from fastapi.testclient import TestClient

from app.services.watchlist import WATCHLIST_MAX


def _car_ids(client: TestClient, limit: int) -> list[int]:
    res = client.get("/cars", params={"limit": limit})
    assert res.status_code == 200
    return [int(c["id"]) for c in res.json()["items"]]


def test_watchlist_ids_empty_initially(client):
    res = client.get("/watchlist/ids")
    assert res.status_code == 200
    assert res.json() == {"ids": []}


def test_watchlist_check_route(client):
    """POST /watchlist/check must not match POST /watchlist/{car_id} with car_id='check'."""
    res = client.post("/watchlist/check")
    assert res.status_code == 200
    assert res.status_code != 422
    assert res.json().get("status") in ("ok", "skipped")


def test_watchlist_add_remove(client):
    car_id = _car_ids(client, 1)[0]

    add = client.post(f"/watchlist/{car_id}")
    assert add.status_code == 200

    ids = client.get("/watchlist/ids").json()["ids"]
    assert car_id in ids

    listing = client.get("/watchlist")
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] >= 1
    assert any(item["id"] == car_id for item in data["items"])

    delete = client.delete(f"/watchlist/{car_id}")
    assert delete.status_code == 204

    ids_after = client.get("/watchlist/ids").json()["ids"]
    assert car_id not in ids_after


def test_watchlist_limit_enforced(client):
    ids = _car_ids(client, WATCHLIST_MAX + 2)
    if len(ids) < WATCHLIST_MAX + 1:
        return  # not enough inventory to test limit

    added = []
    for car_id in ids:
        res = client.post(f"/watchlist/{car_id}")
        if res.status_code == 200:
            added.append(car_id)
        elif res.status_code == 409:
            break
        else:
            raise AssertionError(f"unexpected status {res.status_code}")

    assert len(added) <= WATCHLIST_MAX
    if len(ids) > WATCHLIST_MAX:
        extra = next(i for i in ids if i not in added)
        conflict = client.post(f"/watchlist/{extra}")
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["error"] == "watchlist_limit"

    for car_id in added:
        client.delete(f"/watchlist/{car_id}")
