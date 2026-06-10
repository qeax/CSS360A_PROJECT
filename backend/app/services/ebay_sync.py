"""Persist eBay Browse listings into MySQL (upsert by source + external_listing_id)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.ebay.client import (
    ebay_batch_size,
    ebay_wave_size,
    get_ebay_client,
)
from app.integrations.ebay.inventory import (
    _default_ebay_query,
    resolve_listing_url,
)
from app.integrations.ebay.parse_item import (
    merge_search_summary,
    resolve_listing_mileage,
    resolve_vehicle_facets,
)
from app.integrations.ebay.price import parse_listing_price
from app.integrations.ebay.vehicle_filter import is_likely_vehicle_listing
from app.models.car import Car
from app.models.car_satellite import (
    CarListingTerms,
    CarLocation,
    CarMedia,
    VehicleAspectSnapshot,
)
from app.models.car_search_query import CarSearchQuery
from app.models.ebay_sync_batch import EbaySyncBatch
from app.models.external_seller import ExternalSeller
from app.repositories.cars import (
    car_to_api_item,
    invalidate_in_memory_demo_cache,
    load_car_by_id,
    mark_expired_auctions,
)
from app.services.flip import estimate_flip_from_listing
from app.services.pricing import PricingInput, ResalePricingService, rebuild_vehicle_price_segments
from app.services.search_query import normalize_search_key
from app.services.vehicle_aspects import extended_vehicle_fields_from_aspects_json

logger = logging.getLogger(__name__)

# MySQL TEXT is ~64 KiB; oversized bodies stay in raw_listing_json.description.
_MAX_DESCRIPTION_FULL_BYTES = 65000


def _description_full_for_storage(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if len(text.encode("utf-8")) > _MAX_DESCRIPTION_FULL_BYTES:
        return None
    return text


_last_sync_by_user: dict[int, float] = {}
_last_segment_rebuild_at: float = 0.0


class EbaySyncCooldownError(Exception):
    """Raised when sync_ebay is requested before the cooldown elapses."""

    def __init__(self, retry_after_sec: float) -> None:
        self.retry_after_sec = retry_after_sec
        super().__init__(f"eBay sync cooldown ({retry_after_sec:.0f}s remaining)")


def _sync_min_interval_sec() -> float:
    try:
        return max(0.0, float(os.getenv("EBAY_SYNC_MIN_INTERVAL_SEC", "10")))
    except ValueError:
        return 10.0


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


def _maybe_refresh_segment_baselines(db: Session) -> None:
    global _last_segment_rebuild_at
    now = time.monotonic()
    if now - _last_segment_rebuild_at < 3600:
        return
    rebuild_vehicle_price_segments(db)
    _last_segment_rebuild_at = now


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


def _utc_aware(dt: datetime | None) -> datetime | None:
    """Normalize DB/API datetimes for comparison with UTC-aware `now`."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def _upsert_car_search_query(
    db: Session,
    *,
    car_id: int,
    query_text: str | None,
    source: str = "ebay",
) -> None:
    text = (query_text or "").strip()
    if not text:
        return
    key = normalize_search_key(text)
    if not key:
        return
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(CarSearchQuery).where(
            CarSearchQuery.car_id == car_id,
            CarSearchQuery.query_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(
            CarSearchQuery(
                car_id=car_id,
                query_text=text[:256],
                query_key=key[:128],
                source=source[:32],
                hit_count=1,
                last_seen_at=now,
            )
        )
        return
    row.query_text = text[:256]
    row.source = source[:32]
    row.hit_count = int(row.hit_count or 0) + 1
    row.last_seen_at = now


def upsert_ebay_listing(
    db: Session,
    item: dict[str, Any],
    *,
    ingest_search_key: str | None = None,
    search_query_text: str | None = None,
) -> Car | None:
    """Insert or update one normalized eBay listing row and satellites."""
    if item.get("error"):
        return None
    ext_id = (item.get("external_listing_id") or "").strip()
    if not ext_id or ext_id.startswith("ebay-"):
        return None
    car = db.execute(
        select(Car).where(Car.source == "ebay", Car.external_listing_id == ext_id)
    ).scalar_one_or_none()
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
        region = None
        loc_in = item.get("location") if isinstance(item.get("location"), dict) else {}
        if loc_in:
            region = loc_in.get("region")
        aspect_fields = extended_vehicle_fields_from_aspects_json(item.get("aspects_json"))
        pricing_input = PricingInput(
            external_listing_id=ext_id,
            source="ebay",
            purchase_price=float(price),
            brand=brand,
            model=model,
            year=year_econ,
            mileage=mileage_for_flip,
            condition=condition_econ,
            vehicle_title=vehicle_title_econ,
            listing_format=item.get("listing_format") or "BUY_IT_NOW",
            region=region,
            synced_at=datetime.now(timezone.utc),
            trim=aspect_fields.get("trim"),
            engine=aspect_fields.get("engine"),
            body_style=aspect_fields.get("body_style"),
            title_text=title,
            car_id=int(car.id) if car is not None else None,
        )
        estimate = ResalePricingService().estimate(pricing_input, db=db)
        resale = float(estimate.resale_value)
    else:
        repair, resale = 0.0, 0.0
        estimate = None

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
        "description_full": _description_full_for_storage(item.get("description_full")),
        "api_synced_at": now,
        "seller_item_revision": item.get("seller_item_revision"),
        "resale_method": estimate.method if estimate else None,
        "resale_confidence": float(estimate.confidence) if estimate else None,
        "resale_comp_count": int(estimate.comp_count) if estimate else None,
        "resale_segment_key": estimate.segment_key if estimate else None,
        "resale_estimated_at": datetime.now(timezone.utc) if estimate else None,
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
    _upsert_car_search_query(
        db,
        car_id=int(car.id),
        query_text=search_query_text or ingest_search_key,
        source="ebay",
    )
    return car


class EbayRefreshError(Exception):
    """Single-listing eBay refresh failed (not configured, not found, or API error)."""


@dataclass
class RefreshCarOutcome:
    deleted: bool = False
    car: Car | None = None
    car_id: int | None = None
    message: str | None = None


def refresh_car_from_ebay(db: Session, car_id: int) -> RefreshCarOutcome:
    """
    Re-fetch one eBay listing via getItem and upsert into DB.
    Does not use per-user sync cooldown.
    """
    car = db.execute(select(Car).where(Car.id == car_id)).scalar_one_or_none()
    if car is None:
        raise EbayRefreshError("car_not_found")
    src = (car.source or "").strip().lower()
    if src != "ebay":
        raise EbayRefreshError("not_ebay_listing")
    ext_id = (car.external_listing_id or "").strip()
    if not ext_id:
        raise EbayRefreshError("missing_external_listing_id")

    client = get_ebay_client()
    if not client.is_configured():
        raise EbayRefreshError("ebay_not_configured")

    result = client.get_item(ext_id)
    if result.status == "not_found":
        deleted_id = int(car.id)
        db.delete(car)
        try:
            db.commit()
            invalidate_in_memory_demo_cache()
        except Exception as e:
            db.rollback()
            raise EbayRefreshError(f"commit_failed: {e}") from e
        return RefreshCarOutcome(
            deleted=True,
            car_id=deleted_id,
            message="This listing is no longer available on eBay and was removed from your inventory.",
        )
    if result.status != "ok" or not result.detail:
        status = result.http_status
        if status == 429:
            raise EbayRefreshError("ebay_rate_limited")
        raise EbayRefreshError(f"ebay_get_item_failed:{status or 'unknown'}")

    detail = result.detail
    raw = car.raw_listing_json if isinstance(car.raw_listing_json, dict) else {}
    raw_title = (raw.get("title") or "").strip() if raw else ""
    summary = {
        "external_listing_id": ext_id,
        "title": (
            raw_title
            or (getattr(car, "description_summary", None) or f"{car.brand} {car.model}").strip()
        ),
        "source": "ebay",
        "brand": car.brand,
        "model": car.model,
        "year": car.year,
    }
    merged = merge_search_summary(summary, detail)
    merged["raw_listing_json"] = detail
    if detail.get("sellerItemRevision"):
        merged["seller_item_revision"] = detail.get("sellerItemRevision")

    updated = upsert_ebay_listing(
        db,
        merged,
        ingest_search_key=getattr(car, "ingest_search_key", None),
        search_query_text=getattr(car, "ingest_search_key", None),
    )
    if updated is None:
        raise EbayRefreshError("upsert_failed")
    try:
        db.commit()
        invalidate_in_memory_demo_cache()
    except Exception as e:
        db.rollback()
        raise EbayRefreshError(f"commit_failed: {e}") from e
    db.refresh(updated)
    return RefreshCarOutcome(deleted=False, car=updated)


def _batch_ttl_hours() -> int:
    try:
        return max(1, int(os.getenv("EBAY_BATCH_TTL_HOURS", "24")))
    except ValueError:
        return 24


def _get_active_batch(db: Session, user_id: int, search_key: str | None) -> EbaySyncBatch | None:
    if not search_key:
        return None
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(EbaySyncBatch).where(
            EbaySyncBatch.user_id == user_id,
            EbaySyncBatch.search_key == search_key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    expires_at = _utc_aware(row.expires_at)
    if expires_at and expires_at < now:
        db.execute(delete(EbaySyncBatch).where(EbaySyncBatch.id == row.id))
        db.flush()
        return None
    return row


def ebay_batch_payload(batch: EbaySyncBatch | None) -> dict[str, Any]:
    if batch is None:
        return {
            "pending_in_batch": 0,
            "batch_size": 0,
            "wave_size": ebay_wave_size(),
            "batch_exhausted": True,
            "can_fetch_new_batch": True,
        }
    summaries = batch.summaries_json if isinstance(batch.summaries_json, list) else []
    total = len(summaries)
    pending = max(0, total - int(batch.cursor or 0))
    return {
        "pending_in_batch": pending,
        "batch_size": total,
        "wave_size": ebay_wave_size(),
        "batch_exhausted": pending == 0,
        "can_fetch_new_batch": pending == 0,
    }


def search_listings_batch(*, query: str) -> list[dict[str, Any]]:
    """Search-only eBay listings (vehicle filter), up to EBAY_BATCH_SIZE."""
    client = get_ebay_client()
    if not client.is_configured():
        return []
    raw = client.search_listings(query=query, limit=ebay_batch_size())
    out: list[dict[str, Any]] = []
    for item in raw:
        if not is_likely_vehicle_listing(item):
            continue
        row = dict(item)
        row.setdefault("source", "ebay")
        out.append(row)
    return out


def _upsert_enriched_wave(
    db: Session,
    *,
    batch: EbaySyncBatch,
    ingest_search_key: str | None,
) -> dict[str, Any]:
    """getItem + DB upsert for the next wave slice; advance batch cursor."""
    client = get_ebay_client()
    summaries = batch.summaries_json if isinstance(batch.summaries_json, list) else []
    wave = ebay_wave_size()
    start = int(batch.cursor or 0)
    end = min(start + wave, len(summaries))
    slice_rows = summaries[start:end]

    enriched_list = client.enrich_summaries(slice_rows) if slice_rows else []

    synced = 0
    skipped = 0
    synced_car_ids: list[int] = []
    wave_items: list[dict[str, Any]] = []

    for merged in enriched_list:
        if merged is None:
            skipped += 1
            continue
        try:
            with db.begin_nested():
                car = upsert_ebay_listing(
                    db,
                    merged,
                    ingest_search_key=ingest_search_key,
                    search_query_text=batch.search_query,
                )
            if car is None:
                skipped += 1
                continue
            synced += 1
            synced_car_ids.append(int(car.id))
        except Exception as e:
            logger.warning(
                "eBay upsert failed for %s: %s",
                merged.get("external_listing_id"),
                e,
            )
            skipped += 1

    batch.cursor = end
    db.add(batch)

    for car_id in synced_car_ids:
        loaded = load_car_by_id(db, car_id)
        if loaded is None:
            continue
        item = car_to_api_item(loaded)
        if item is not None:
            wave_items.append(item)

    return {
        "synced": synced,
        "skipped": skipped,
        "wave_items": wave_items,
        "synced_car_ids": synced_car_ids,
        "summaries_searched": len(slice_rows),
    }


def _save_batch(
    db: Session,
    *,
    user_id: int,
    search_key: str | None,
    search_query: str,
    summaries: list[dict[str, Any]],
) -> EbaySyncBatch:
    if not search_key:
        search_key = ""
    expires = datetime.now(timezone.utc) + timedelta(hours=_batch_ttl_hours())

    # Robustly clear any existing batch for this user/search_key combo
    db.execute(
        delete(EbaySyncBatch).where(
            EbaySyncBatch.user_id == user_id,
            EbaySyncBatch.search_key == search_key,
        )
    )
    db.flush()

    batch = EbaySyncBatch(
        user_id=user_id,
        search_key=search_key,
        search_query=search_query,
        summaries_json=summaries,
        cursor=0,
        expires_at=expires,
    )
    db.add(batch)
    db.flush()
    return batch


def _finalize_sync_commit(db: Session, *, user_id: int, enforce_cooldown: bool) -> None:
    _maybe_refresh_segment_baselines(db)
    mark_expired_auctions(db)
    db.commit()
    invalidate_in_memory_demo_cache()
    if enforce_cooldown:
        mark_sync_completed(user_id)


def start_ebay_batch(
    db: Session,
    *,
    user_id: int,
    q: Optional[str] = None,
    enforce_cooldown: bool = True,
) -> dict[str, Any]:
    """
    Search up to EBAY_BATCH_SIZE summaries, persist batch, enrich+upsert first wave only.
    """
    client = get_ebay_client()
    if not client.is_configured():
        return {
            "synced": 0,
            "skipped": 0,
            "configured": False,
            "status": "not_configured",
            "query": None,
            "ebay_batch": ebay_batch_payload(None),
        }

    search_key = normalize_search_key(q)
    if enforce_cooldown:
        check_sync_cooldown(user_id)

    search_q = build_ebay_search_query(q=q)
    try:
        summaries = search_listings_batch(query=search_q)
        batch = _save_batch(
            db,
            user_id=user_id,
            search_key=search_key or "",
            search_query=search_q,
            summaries=summaries,
        )
        wave_stats = _upsert_enriched_wave(db, batch=batch, ingest_search_key=search_key)
        _finalize_sync_commit(db, user_id=user_id, enforce_cooldown=enforce_cooldown)
        db.refresh(batch)

        last_diag = getattr(client, "last_search_diagnostic", None) or {}
        token_failed = last_diag.get("error") == "token_failed"
        sync_status = "failed" if token_failed else "ok"
        sync_error = None
        if token_failed:
            token_diag = getattr(client, "last_token_diagnostic", None) or {}
            sync_error = (
                "eBay OAuth token failed"
                + (f" (HTTP {token_diag['http_status']})" if token_diag.get("http_status") else "")
                + ". Check EBAY_CLIENT_ID / EBAY_CLIENT_SECRET and EBAY_SANDBOX in .env."
            )

        return {
            "synced": wave_stats["synced"],
            "skipped": wave_stats["skipped"],
            "configured": True,
            "status": sync_status,
            "error": sync_error,
            "query": search_q,
            "query_key": search_key,
            "api_rows": len(summaries),
            "wave_items": wave_stats["wave_items"],
            "ebay_batch": ebay_batch_payload(batch),
        }
    except Exception as e:
        db.rollback()
        logger.error("eBay batch start failed query=%r: %s", search_q, e)
        return {
            "synced": 0,
            "skipped": 0,
            "configured": True,
            "status": "failed",
            "query": search_q,
            "error": str(e)[:500],
            "api_rows": 0,
            "wave_items": [],
            "ebay_batch": ebay_batch_payload(_get_active_batch(db, user_id, search_key)),
        }


def continue_ebay_batch(
    db: Session,
    *,
    user_id: int,
    q: Optional[str] = None,
) -> dict[str, Any]:
    """
    Enrich the next wave from the active batch; if exhausted, start a new batch (new search).
    No per-user cooldown.
    """
    client = get_ebay_client()
    if not client.is_configured():
        return {
            "synced": 0,
            "skipped": 0,
            "configured": False,
            "status": "not_configured",
            "query": None,
            "ebay_batch": ebay_batch_payload(None),
            "wave_items": [],
        }

    search_key = normalize_search_key(q)
    search_q = build_ebay_search_query(q=q)
    batch = _get_active_batch(db, user_id, search_key)
    summaries = batch.summaries_json if batch and isinstance(batch.summaries_json, list) else []
    if batch is None or int(batch.cursor or 0) >= len(summaries):
        stats = start_ebay_batch(db, user_id=user_id, q=q, enforce_cooldown=False)
        stats["new_batch"] = True
        return stats

    try:
        wave_stats = _upsert_enriched_wave(db, batch=batch, ingest_search_key=search_key)
        _finalize_sync_commit(db, user_id=user_id, enforce_cooldown=False)
        db.refresh(batch)
        return {
            "synced": wave_stats["synced"],
            "skipped": wave_stats["skipped"],
            "configured": True,
            "status": "ok",
            "query": search_q,
            "query_key": search_key,
            "wave_items": wave_stats["wave_items"],
            "new_batch": False,
            "ebay_batch": ebay_batch_payload(batch),
        }
    except Exception as e:
        db.rollback()
        logger.error("eBay batch continue failed: %s", e)
        return {
            "synced": 0,
            "skipped": 0,
            "configured": True,
            "status": "failed",
            "query": search_q,
            "error": str(e)[:500],
            "wave_items": [],
            "ebay_batch": ebay_batch_payload(_get_active_batch(db, user_id, search_key)),
        }


def sync_ebay_inventory(
    db: Session,
    *,
    user_id: int,
    q: Optional[str] = None,
    enforce_cooldown: bool = True,
) -> dict[str, Any]:
    """Start a new eBay batch (search + first enrich wave)."""
    return start_ebay_batch(db, user_id=user_id, q=q, enforce_cooldown=enforce_cooldown)
