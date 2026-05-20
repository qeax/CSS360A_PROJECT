"""In-memory eBay listings for the main inventory API (never persisted to DB)."""

from __future__ import annotations

import logging
import os
import re
import time
from types import SimpleNamespace
from typing import Any

from app.integrations.ebay.client import get_ebay_client

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 300
_ebay_cache: dict[str, tuple[float, list[Any]]] = {}

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


def invalidate_ebay_inventory_cache() -> None:
    """Clear cached eBay inventory (tests)."""
    _ebay_cache.clear()


def _default_ebay_query() -> str:
    return (os.getenv("EBAY_DEFAULT_QUERY") or "car").strip() or "car"


def _parse_year(title: str, year_hint: Any = None) -> int:
    if year_hint is not None:
        try:
            return int(year_hint)
        except (TypeError, ValueError):
            pass
    m = _YEAR_RE.search(title or "")
    if m:
        return int(m.group(1))
    return 2018


def _parse_brand_model(
    title: str, brand_hint: str | None, model_hint: str | None
) -> tuple[str, str]:
    if brand_hint and model_hint:
        return brand_hint[:64], model_hint[:128]
    t = (title or "").strip()
    if not t:
        return "Unknown", "Listing"
    parts = t.split()
    if len(parts) >= 3 and _YEAR_RE.match(parts[0]):
        brand = parts[1]
        model = " ".join(parts[2:6])
        return brand[:64], model[:128]
    if len(parts) >= 2:
        return parts[0][:64], " ".join(parts[1:6])[:128]
    return "eBay", t[:128]


def _flip_estimates(price: float) -> tuple[float, float]:
    repair = round(price * 0.08, 2)
    resale = round(price * 1.12, 2)
    return repair, resale


def ebay_listing_dict_to_car_view(item: dict[str, Any], index: int) -> SimpleNamespace | None:
    """Map normalized eBay row (search + optional getItem) to a demo-compatible car view."""
    if item.get("error"):
        return None
    title = (item.get("title") or "").strip()
    if not title:
        return None
    try:
        price = float(item.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        price = 1.0

    brand, model = _parse_brand_model(title, item.get("brand"), item.get("model"))
    year = _parse_year(title, item.get("year"))
    repair, resale = _flip_estimates(price)
    ext_id = (item.get("external_listing_id") or f"ebay-{index}").strip()
    listing_url = item.get("listing_url") or f"https://www.ebay.com/itm/{ext_id}"

    loc_in = item.get("location") if isinstance(item.get("location"), dict) else {}
    city = (loc_in.get("city") or item.get("location_city") or "").strip() or "—"
    loc = SimpleNamespace(
        country=loc_in.get("country") or "United States",
        region=loc_in.get("region") or "",
        city=city,
        postal_code_masked=loc_in.get("postal_code_masked"),
        latitude=None,
        longitude=None,
    )

    delivery_in = item.get("delivery") if isinstance(item.get("delivery"), dict) else {}
    terms = SimpleNamespace(
        ship_to_home=bool(delivery_in.get("ship_to_home", True)),
        local_pickup=bool(delivery_in.get("local_pickup", False)),
        in_store_pickup=bool(delivery_in.get("in_store_pickup", False)),
    )

    image_urls = item.get("image_urls") if isinstance(item.get("image_urls"), list) else []
    image_url = item.get("image_url") or (image_urls[0] if image_urls else None)
    media = [SimpleNamespace(sort_order=i, url=url) for i, url in enumerate(image_urls) if url]

    aspects = item.get("aspects_json")
    if not isinstance(aspects, list) or not aspects:
        aspects = [
            {"localizedAspectName": "Body Style", "localizedAspectValues": ["Not Specified"]},
        ]
    snap = SimpleNamespace(id=index, captured_at=None, aspects_json=aspects)

    seller_username = item.get("seller_username")
    external_seller = SimpleNamespace(username=seller_username) if seller_username else None

    listing_ends_at = item.get("listing_ends_at")
    bid_count = item.get("bid_count")
    try:
        bid_count = int(bid_count) if bid_count is not None else None
    except (TypeError, ValueError):
        bid_count = None

    return SimpleNamespace(
        id=index,
        external_seller=external_seller,
        location=loc,
        listing_terms=terms,
        media=media,
        aspect_snapshots=[snap],
        brand=brand,
        model=model,
        year=year,
        price=price,
        repair_cost=repair,
        resale_value=resale,
        mileage=item.get("mileage"),
        condition=(item.get("condition") or "Used").strip(),
        vehicle_title=(item.get("vehicle_title") or "Not Specified").strip(),
        image_url=image_url,
        source="ebay",
        external_listing_id=ext_id,
        listing_url=listing_url,
        listing_format=item.get("listing_format") or "BUY_IT_NOW",
        bid_count=bid_count,
        listing_ends_at=listing_ends_at,
        description_summary=(item.get("description_summary") or title)[:512],
    )


def fetch_ebay_inventory_views(query: str | None = None, *, limit: int = 50) -> list[Any]:
    """Fetch eBay listings (search + getItem) as car-like views; never persisted."""
    client = get_ebay_client()
    if not client.is_configured():
        return []

    q = (query or _default_ebay_query()).strip()
    if len(q) < 3:
        q = _default_ebay_query()

    cache_key = q.lower()
    now = time.time()
    cached = _ebay_cache.get(cache_key)
    if cached and cached[0] > now:
        return list(cached[1])

    raw = client.search_listings_enriched(query=q, limit=min(limit, 50))
    views: list[Any] = []
    for i, item in enumerate(raw, start=1):
        view = ebay_listing_dict_to_car_view(item, i)
        if view is not None:
            views.append(view)

    if views:
        _ebay_cache[cache_key] = (now + _CACHE_TTL_SEC, views)
    else:
        logger.warning("eBay inventory fetch returned no listings for query=%r", q)
    return views
