"""In-app notifications API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.services.notifications import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_count,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def get_notifications(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        items = list_notifications(db, int(current_user.id), limit=limit)
        return {"items": items, "unread_count": unread_count(db, int(current_user.id))}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.get("/notifications/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return {"unread_count": unread_count(db, int(current_user.id))}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.patch("/notifications/{notification_id}/read")
def patch_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        ok = mark_notification_read(db, int(current_user.id), notification_id)
        if not ok:
            raise HTTPException(status_code=404, detail="notification_not_found")
        db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.post("/notifications/test-preview")
def post_notifications_test_preview(
    current_user: User = Depends(get_current_user),
):
    """Return a sample notification for UI testing; nothing is persisted."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "item": {
            "id": None,
            "car_id": None,
            "type": "test_preview",
            "title": "Test notification",
            "message": "This is a preview only — it was not saved to the database.",
            "payload": None,
            "read_at": None,
            "created_at": now,
            "ephemeral": True,
        },
    }


@router.post("/notifications/read-all")
def post_notifications_read_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        count = mark_all_notifications_read(db, int(current_user.id))
        db.commit()
        return {"ok": True, "marked": count}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e
