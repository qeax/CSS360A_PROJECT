"""Watchlist CRUD and snapshot helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.user_watchlist import UserWatchlistItem
from app.repositories.cars import car_to_api_item, load_car_by_id

WATCHLIST_MAX = 10


class WatchlistLimitError(Exception):
    """User already has the maximum number of tracked listings."""


class WatchlistNotFoundError(Exception):
    pass


def build_watch_snapshot(car: Car) -> dict[str, Any]:
    """Serializable baseline for change detection."""
    return {
        "price": car.price,
        "price_known": bool(car.price_known),
        "description_summary": getattr(car, "description_summary", None),
        "description_hash": hash(getattr(car, "description_full", None) or ""),
        "mileage": car.mileage,
        "condition": car.condition,
        "bid_count": car.bid_count,
        "listing_ends_at": (car.listing_ends_at.isoformat() if car.listing_ends_at else None),
        "auction_ended_at": (car.auction_ended_at.isoformat() if car.auction_ended_at else None),
        "listing_format": car.listing_format,
    }


def list_watchlist_car_ids(db: Session, user_id: int) -> list[int]:
    rows = db.scalars(
        select(UserWatchlistItem.car_id)
        .where(UserWatchlistItem.user_id == user_id)
        .order_by(UserWatchlistItem.created_at.desc())
    ).all()
    return list(rows)


def is_car_watched(db: Session, user_id: int, car_id: int) -> bool:
    row = db.execute(
        select(UserWatchlistItem.id).where(
            UserWatchlistItem.user_id == user_id,
            UserWatchlistItem.car_id == car_id,
        )
    ).scalar_one_or_none()
    return row is not None


def watchlist_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(UserWatchlistItem)
            .where(UserWatchlistItem.user_id == user_id)
        )
        or 0
    )


def add_to_watchlist(db: Session, user_id: int, car_id: int) -> UserWatchlistItem:
    car = load_car_by_id(db, car_id)
    if car is None:
        raise WatchlistNotFoundError("car_not_found")
    existing = db.execute(
        select(UserWatchlistItem).where(
            UserWatchlistItem.user_id == user_id,
            UserWatchlistItem.car_id == car_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    if watchlist_count(db, user_id) >= WATCHLIST_MAX:
        raise WatchlistLimitError()
    row = UserWatchlistItem(
        user_id=user_id,
        car_id=car_id,
        last_snapshot_json=build_watch_snapshot(car),
        last_checked_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def remove_from_watchlist(db: Session, user_id: int, car_id: int) -> bool:
    row = db.execute(
        select(UserWatchlistItem).where(
            UserWatchlistItem.user_id == user_id,
            UserWatchlistItem.car_id == car_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def list_watchlist_items(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(UserWatchlistItem)
        .where(UserWatchlistItem.user_id == user_id)
        .order_by(UserWatchlistItem.created_at.desc())
    ).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        car = row.car
        if car is None:
            continue
        api = car_to_api_item(car)
        if api:
            api["is_watched"] = True
            items.append(api)
    return items
