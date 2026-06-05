"""In-app notifications for watchlist changes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.user_notification import UserNotification

NOTIFICATION_TTL_DAYS = 7


def _utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def purge_old_notifications(db: Session, user_id: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=NOTIFICATION_TTL_DAYS)
    stale_ids = [
        row.id
        for row in db.scalars(
            select(UserNotification).where(UserNotification.user_id == user_id)
        ).all()
        if row.created_at is not None and _utc_aware(row.created_at) < cutoff
    ]
    if not stale_ids:
        return 0
    result = db.execute(delete(UserNotification).where(UserNotification.id.in_(stale_ids)))
    return int(result.rowcount or 0)


def create_notification(
    db: Session,
    *,
    user_id: int,
    car_id: int | None,
    ntype: str,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> UserNotification:
    row = UserNotification(
        user_id=user_id,
        car_id=car_id,
        type=ntype,
        title=title[:255],
        message=message,
        payload_json=payload,
    )
    db.add(row)
    db.flush()
    return row


def unread_count(db: Session, user_id: int) -> int:
    purge_old_notifications(db, user_id)
    return int(
        db.scalar(
            select(func.count())
            .select_from(UserNotification)
            .where(
                UserNotification.user_id == user_id,
                UserNotification.read_at.is_(None),
            )
        )
        or 0
    )


def list_notifications(db: Session, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
    purge_old_notifications(db, user_id)
    rows = db.scalars(
        select(UserNotification)
        .where(UserNotification.user_id == user_id)
        .order_by(UserNotification.created_at.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "car_id": row.car_id,
                "type": row.type,
                "title": row.title,
                "message": row.message,
                "payload": row.payload_json,
                "read_at": row.read_at.isoformat() if row.read_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def mark_notification_read(db: Session, user_id: int, notification_id: int) -> bool:
    row = db.execute(
        select(UserNotification).where(
            UserNotification.id == notification_id,
            UserNotification.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.flush()
    return True


def mark_all_notifications_read(db: Session, user_id: int) -> int:
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(UserNotification).where(
            UserNotification.user_id == user_id,
            UserNotification.read_at.is_(None),
        )
    ).all()
    for row in rows:
        row.read_at = now
    db.flush()
    return len(rows)
