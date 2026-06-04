"""Tests for notifications API and purge behavior."""

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.services.notifications import (
    NOTIFICATION_TTL_DAYS,
    create_notification,
    list_notifications,
    purge_old_notifications,
    unread_count,
)


def test_create_and_list_notifications():
    with SessionLocal() as db:
        row = create_notification(
            db,
            user_id=1,
            car_id=None,
            ntype="price_changed",
            title="Test",
            message="Price changed",
        )
        db.commit()
        nid = row.id

        items = list_notifications(db, 1, limit=5)
        assert any(n["id"] == nid for n in items)
        assert unread_count(db, 1) >= 1


def test_purge_old_notifications():
    with SessionLocal() as db:
        row = create_notification(
            db,
            user_id=1,
            car_id=None,
            ntype="details_changed",
            title="Old",
            message="Stale",
        )
        row.created_at = datetime.now(timezone.utc) - timedelta(days=NOTIFICATION_TTL_DAYS + 1)
        db.commit()

        purged = purge_old_notifications(db, 1)
        db.commit()
        assert purged >= 1


def test_notifications_api(client):
    res = client.get("/notifications", params={"limit": 5})
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "unread_count" in data

    read_all = client.post("/notifications/read-all")
    assert read_all.status_code == 200

    count_res = client.get("/notifications/unread-count")
    assert count_res.status_code == 200
    assert "unread_count" in count_res.json()

    preview = client.post("/notifications/test-preview")
    assert preview.status_code == 200
    item = preview.json()["item"]
    assert item["id"] is None
    assert item["type"] == "test_preview"
    assert item.get("ephemeral") is True
    assert item["read_at"] is None
    assert "created_at" in item
