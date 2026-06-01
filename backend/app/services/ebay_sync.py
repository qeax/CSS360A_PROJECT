"""Persist eBay Browse listings into MySQL (upsert by source + external_listing_id)."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.ebay.client import ebay_fetch_cap, get_ebay_client
from app.integrations.ebay.inventory import (
    _default_ebay_query,
    resolve_listing_url,
)
from app.integrations.ebay.parse_item import resolve_listing_mileage, resolve_vehicle_facets
from app.integrations.ebay.price import parse_listing_price
from app.integrations.ebay.vehicle_filter import is_likely_vehicle_listing
from app.models.car import Car
from app.models.car_satellite import (
    CarListingTerms,
    CarLocation,
    CarMedia,
    VehicleAspectSnapshot,
)
from app.models.external_seller import ExternalSeller
from app.repositories.cars import mark_expired_auctions
from app.services.flip import estimate_flip_from_listing
from app.services.search_query import normalize_search_key

logger = logging.getLogger(__name__)

_last_sync_by_user: dict[int, float] = {}


class EbaySyncCooldownError(Exception):
    """Raised when sync_ebay is requested before the cooldown elapses."""

    def __init__(self, retry_after_sec: float) -> None:
        self.retry_after_sec = retry_after_sec
        super().__init__(f"eBay sync cooldown ({retry_after_sec:.0f}s remaining)")


def _sync_min_interval_sec() -> float:
    try:
        return max(0.0, float(os.getenv("EBAY_SYNC_MIN_INTERVAL_SEC", "60")))
    except ValueError:
        return 60.0


def check_sync_cooldown(user_id: int) -> None:
    """Raise EbaySyncCooldownError if this user synced too recently."""
    interval = _sync_min_interval_sec()
    if interval <= 0:
        return
    last = _last_sync_by_user.get(user_id)
    if last is None:
        return
    elapsed = time.monotonic() - last
    if elapsed < interval:
        raise EbaySyncCooldownError(interval - elapsed)


def mark_sync_completed(user_id: int) -> None:
    _last_sync_by_user[user_id] = time.monotonic()


def reset_sync_cooldown_for_tests() -> None:
    _last_sync_by_user.clear()


def build_ebay_search_query(*, q: Optional[str]) -> str:
    """Compose Browse API `q` from search text only (filters apply to DB after ingest)."""
    text = (q or "").strip()
    if text and len(text) >= 3:
        return text
    return _default_ebay_query()


def _parse_listing_ends_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None
    return None


def _seller_external_id(item: dict[str, Any]) -> str | None:
    username = (item.get("seller_username") or "").strip()
    if username:
        return username
    return None


def _upsert_external_seller(db: Session, item: dict[str, Any]) -> int | None:
    ext_id = _seller_external_id(item)
    if not ext_id:
        return None
    row = db.execute(
        select(ExternalSeller).where(
            ExternalSeller.platform == "ebay",
            ExternalSeller.external_seller_id == ext_id,
        )
    ).scalar_one_or_none()
    username = (item.get("seller_username") or ext_id).strip()
    now = datetime.now(timezone.utc)
    if row is None:
        row = ExternalSeller(
            platform="ebay",
            external_seller_id=ext_id,
            username=username,
            synced_at=now,
        )
        db.add(row)
        db.flush()
    else:
        row.username = username
        row.synced_at = now
    return row.id


def _replace_car_children(db: Session, car: Car, item: dict[str, Any]) -> None:
    if car.location:
        db.delete(car.location)
    if car.listing_terms:
        db.delete(car.listing_terms)
    for m in list(car.media):
        db.delete(m)
    for snap in list(car.aspect_snapshots):
        db.delete(snap)

    loc_in = item.get("location") if isinstance(item.get("location"), dict) else {}
    country = (loc_in.get("country") or "").strip() or None
    region = (loc_in.get("region") or "").strip() or None
    city = (loc_in.get("city") or item.get("location_city") or "").strip() or None
    if city == "—":
        city = None
    db.add(
        CarLocation(
            car_id=car.id,
            country=country,
            region=region,
            city=city,
            postal_code_masked=loc_in.get("postal_code_masked"),
            latitude=loc_in.get("latitude"),
            longitude=loc_in.get("longitude"),
        )
    )

    delivery_in = item.get("delivery") if isinstance(item.get("delivery"), dict) else {}
    db.add(
        CarListingTerms(
            car_id=car.id,
            ship_to_home=bool(delivery_in.get("ship_to_home", True)),
            local_pickup=bool(delivery_in.get("local_pickup", False)),
            in_store_pickup=bool(delivery_in.get("in_store_pickup", False)),
            delivery_options_raw=delivery_in or None,
        )
    )

    image_urls = item.get("image_urls") if isinstance(item.get("image_urls"), list) else []
    if not image_urls and item.get("image_url"):
        image_urls = [item["image_url"]]
    for i, url in enumerate(image_urls):
        if url:
            db.add(CarMedia(car_id=car.id, sort_order=i, url=str(url)[:2048]))

    aspects = item.get("aspects_json")
    if isinstance(aspects, list) and aspects:
        db.add(VehicleAspectSnapshot(car_id=car.id, aspects_json=aspects))


def upsert_ebay_listing(
    db: Session, item: dict[str, Any], *, ingest_search_key: str | None = None
) -> Car | None:
    """Insert or update one normalized eBay listing row and satellites."""
    if item.get("error"):
        return None
    ext_id = (item.get("external_listing_id") or "").strip()
    if not ext_id or ext_id.startswith("ebay-"):
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None

    price, price_known = parse_listing_price(item.get("price"))

    facets = resolve_vehicle_facets(
        title,
        brand_hint=item.get("brand"),
        model_hint=item.get("model"),
        year_hint=item.get("year"),
        aspects=item.get("aspects_json"),
    )
    brand = facets["brand"] or "Unknown"
    model = facets["model"] or "Listing"
    year = facets["year"]
    year_econ = year

    mileage_for_flip = resolve_listing_mileage(
        title,
        mileage_hint=item.get("mileage"),
        aspects=item.get("aspects_json"),
    )

    cond_raw = item.get("condition")
    condition_econ = (str(cond_raw).strip() if cond_raw is not None else None) or None
    vtitle_raw = item.get("vehicle_title")
    vehicle_title_econ = (str(vtitle_raw).strip() if vtitle_raw is not None else None) or None

    if price_known:
        repair, resale = estimate_flip_from_listing(
            price,
            year=year_econ,
            mileage=mileage_for_flip,
            condition=condition_econ,
            vehicle_title=vehicle_title_econ,
            listing_format=item.get("listing_format") or "BUY_IT_NOW",
            listing_id=ext_id,
            title_text=title,
        )
    else:
        repair, resale = 0.0, 0.0

    client = get_ebay_client()
    listing_url = resolve_listing_url(
        ext_id,
        item.get("listing_url"),
        sandbox=client.sandbox,
    )
    now = datetime.now(timezone.utc)
    listing_ends = _parse_listing_ends_at(item.get("listing_ends_at"))

    bid_count = item.get("bid_count")
    try:
        bid_count_int = int(bid_count) if bid_count is not None else None
    except (TypeError, ValueError):
        bid_count_int = None

    seller_id = _upsert_external_seller(db, item)

    car = db.execute(
        select(Car).where(Car.source == "ebay", Car.external_listing_id == ext_id)
    ).scalar_one_or_none()

    core = {
        "brand": brand[:100],
        "model": model[:100],
        "year": year,
        "price": price,
        "price_known": price_known,
        "repair_cost": repair,
        "resale_value": resale,
        "mileage": mileage_for_flip,
        "condition": condition_econ or "Used",
        "vehicle_title": vehicle_title_econ or "Not Specified",
        "image_url": (item.get("image_url") or "")[:512] or None,
        "source": "ebay",
        "external_listing_id": ext_id,
        "listing_url": listing_url,
        "raw_listing_json": item.get("raw_listing_json") or item,
        "seller_id": seller_id,
        "listing_ends_at": listing_ends,
        "bid_count": bid_count_int,
        "listing_format": (item.get("listing_format") or "BUY_IT_NOW")[:50],
        "description_summary": ((item.get("description_summary") or title)[:512]),
        "api_synced_at": now,
        "seller_item_revision": item.get("seller_item_revision"),
    }
    if listing_ends is not None and listing_ends > now:
        core["auction_ended_at"] = None
    if ingest_search_key:
        core["ingest_search_key"] = ingest_search_key[:128]

    if car is None:
        car = Car(**core)
        db.add(car)
        db.flush()
    else:
        for key, val in core.items():
            setattr(car, key, val)

    _replace_car_children(db, car, item)
    return car


def fetch_ebay_listings_for_sync(*, query: str) -> list[dict[str, Any]]:
    """Call Browse API and return vehicle listings ready for upsert."""
    client = get_ebay_client()
    if not client.is_configured():
        return []
    cap = ebay_fetch_cap()
    raw = client.search_listings_enriched(query=query, limit=cap)
    out: list[dict[str, Any]] = []
    for item in raw:
        if not is_likely_vehicle_listing(item):
            continue
        row = dict(item)
        row.setdefault("source", "ebay")
        out.append(row)
    return out


def sync_ebay_inventory(
    db: Session,
    *,
    user_id: int,
    q: Optional[str] = None,
    enforce_cooldown: bool = True,
) -> dict[str, Any]:
    """
    Fetch listings from eBay, upsert into DB, return sync stats.

    Raises EbaySyncCooldownError when called too soon for the same user.
    On API/upsert failures returns status=failed without raising (caller serves DB inventory).
    """
    client = get_ebay_client()
    if not client.is_configured():
        return {
            "synced": 0,
            "skipped": 0,
            "configured": False,
            "status": "not_configured",
            "query": None,
        }

    search_key = normalize_search_key(q)
    if enforce_cooldown:
        check_sync_cooldown(user_id)

    search_q = build_ebay_search_query(q=q)
    try:
        listings = fetch_ebay_listings_for_sync(query=search_q)
        synced = 0
        skipped = 0
        for item in listings:
            try:
                with db.begin_nested():
                    if upsert_ebay_listing(db, item, ingest_search_key=search_key) is not None:
                        synced += 1
                    else:
                        skipped += 1
            except Exception as e:
                logger.warning(
                    "eBay upsert failed for %s: %s",
                    item.get("external_listing_id"),
                    e,
                )
                skipped += 1

        try:
            mark_expired_auctions(db)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("eBay sync commit failed: %s", e)
            return {
                "synced": 0,
                "skipped": skipped,
                "configured": True,
                "status": "failed",
                "query": search_q,
                "error": str(e),
                "api_rows": len(listings),
            }

        if enforce_cooldown:
            mark_sync_completed(user_id)

        logger.info(
            "eBay sync user=%s query=%r key=%r: %d upserted, %d skipped (api rows=%d)",
            user_id,
            search_q,
            search_key,
            synced,
            skipped,
            len(listings),
        )
        return {
            "synced": synced,
            "skipped": skipped,
            "configured": True,
            "status": "ok",
            "query": search_q,
            "query_key": search_key,
            "api_rows": len(listings),
        }
    except Exception as e:
        db.rollback()
        logger.error("eBay sync failed query=%r: %s", search_q, e)
        return {
            "synced": 0,
            "skipped": 0,
            "configured": True,
            "status": "failed",
            "query": search_q,
            "error": str(e)[:500],
            "api_rows": 0,
        }
