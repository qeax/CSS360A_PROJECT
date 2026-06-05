"""Check tracked listings against eBay and emit notifications."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.ebay.client import get_ebay_client
from app.models.user import User
from app.models.user_watchlist import UserWatchlistItem
from app.repositories.cars import load_car_by_id
from app.services.ebay_sync import EbayRefreshError, refresh_car_from_ebay
from app.services.notifications import create_notification
from app.services.watchlist import build_watch_snapshot

logger = logging.getLogger(__name__)

URGENT_RECHECK_HOURS = 6
FULL_CHECK_INTERVAL_HOURS = 24
AUCTION_SOON_HOURS = 24


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def watch_check_due(
    user: User, items: list[UserWatchlistItem], *, now: datetime | None = None
) -> bool:
    ref = now or datetime.now(timezone.utc)
    last_full = _utc_aware(getattr(user, "watch_last_full_check_at", None))
    if last_full is None:
        return True
    if ref - last_full >= timedelta(hours=FULL_CHECK_INTERVAL_HOURS):
        return True
    soon = ref + timedelta(hours=AUCTION_SOON_HOURS)
    for item in items:
        car = item.car
        if car is None or not car.listing_ends_at:
            continue
        ends = _utc_aware(car.listing_ends_at)
        if ends and ends <= soon:
            checked = _utc_aware(item.last_checked_at)
            if checked is None or ref - checked >= timedelta(hours=URGENT_RECHECK_HOURS):
                return True
    return False


def _diff_and_notify(
    db: Session,
    *,
    user_id: int,
    car_id: int,
    before: dict[str, Any],
    after: dict[str, Any],
    car_label: str,
) -> None:
    if before.get("price") != after.get("price") or before.get("price_known") != after.get(
        "price_known"
    ):
        create_notification(
            db,
            user_id=user_id,
            car_id=car_id,
            ntype="price_changed",
            title=f"Price update: {car_label}",
            message=f"Price changed from {before.get('price')} to {after.get('price')}.",
            payload={"before": before.get("price"), "after": after.get("price")},
        )
    if before.get("description_hash") != after.get("description_hash") or (
        before.get("description_summary") != after.get("description_summary")
    ):
        create_notification(
            db,
            user_id=user_id,
            car_id=car_id,
            ntype="description_changed",
            title=f"Description updated: {car_label}",
            message="The listing description was updated on eBay.",
        )
    detail_keys = ("mileage", "condition", "bid_count", "listing_format")
    if any(before.get(k) != after.get(k) for k in detail_keys):
        create_notification(
            db,
            user_id=user_id,
            car_id=car_id,
            ntype="details_changed",
            title=f"Details updated: {car_label}",
            message="Listing details (mileage, condition, bids, etc.) changed.",
        )
    before_ends = _parse_iso(before.get("listing_ends_at"))
    after_ends = _parse_iso(after.get("listing_ends_at"))
    if before_ends and after_ends and after_ends > before_ends + timedelta(minutes=5):
        create_notification(
            db,
            user_id=user_id,
            car_id=car_id,
            ntype="auction_extended",
            title=f"Auction extended: {car_label}",
            message="The auction end time was moved later.",
        )
    if not before.get("auction_ended_at") and after.get("auction_ended_at"):
        create_notification(
            db,
            user_id=user_id,
            car_id=car_id,
            ntype="auction_ended",
            title=f"Auction ended: {car_label}",
            message="This auction has ended.",
        )


def run_watch_check(db: Session, user_id: int, *, force: bool = False) -> dict[str, Any]:
    """Refresh watched eBay listings when due; return summary."""
    user = db.get(User, user_id)
    if user is None:
        return {"status": "skipped", "reason": "user_not_found"}
    items = list(
        db.scalars(
            select(UserWatchlistItem)
            .where(UserWatchlistItem.user_id == user_id)
            .order_by(UserWatchlistItem.created_at)
        ).all()
    )
    if not items:
        return {"status": "skipped", "reason": "empty_watchlist", "checked": 0}

    now = datetime.now(timezone.utc)
    if not force and not watch_check_due(user, items, now=now):
        return {"status": "skipped", "reason": "not_due", "checked": 0}

    client = get_ebay_client()
    if not client.is_configured():
        return {"status": "skipped", "reason": "ebay_not_configured", "checked": 0}

    checked = 0
    notifications_created = 0
    for item in items:
        car = load_car_by_id(db, item.car_id)
        if car is None:
            db.delete(item)
            continue
        before = item.last_snapshot_json or build_watch_snapshot(car)
        car_label = f"{car.brand} {car.model}".strip() or f"Listing #{car.id}"
        src = (car.source or "").strip().lower()
        try:
            if src == "ebay" and car.external_listing_id:
                outcome = refresh_car_from_ebay(db, int(car.id))
                if outcome.deleted:
                    create_notification(
                        db,
                        user_id=user_id,
                        car_id=None,
                        ntype="listing_removed",
                        title=f"Listing removed: {car_label}",
                        message=outcome.message or "This listing is no longer on eBay.",
                        payload={"car_id": outcome.car_id},
                    )
                    db.delete(item)
                    notifications_created += 1
                    checked += 1
                    continue
            car = load_car_by_id(db, item.car_id)
            if car is None:
                continue
            after = build_watch_snapshot(car)
            _diff_and_notify(
                db,
                user_id=user_id,
                car_id=int(car.id),
                before=before,
                after=after,
                car_label=car_label,
            )
            ends = _utc_aware(car.listing_ends_at)
            if ends and ends <= now + timedelta(hours=AUCTION_SOON_HOURS) and ends > now:
                if not before.get("auction_ending_soon_notified"):
                    create_notification(
                        db,
                        user_id=user_id,
                        car_id=int(car.id),
                        ntype="auction_ending_soon",
                        title=f"Auction ending soon: {car_label}",
                        message="This auction ends in less than 24 hours.",
                    )
                    after["auction_ending_soon_notified"] = True
            item.last_snapshot_json = after
            item.last_checked_at = now
            checked += 1
        except EbayRefreshError as e:
            logger.info("Watch check refresh failed car_id=%s: %s", car.id, e)
        except Exception as e:
            logger.warning("Watch check error car_id=%s: %s", car.id, e)

    user.watch_last_full_check_at = now
    db.commit()
    return {
        "status": "ok",
        "checked": checked,
        "notifications_created": notifications_created,
    }
