"""In-memory eBay listings for the main inventory API (never persisted to DB)."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.integrations.ebay.client import (
    _ebay_category_ids,
    _ebay_search_limit,
    _ebay_search_pages,
    ebay_fetch_cap,
    get_ebay_client,
)
from app.integrations.ebay.vehicle_filter import is_likely_vehicle_listing
from app.services.flip import estimate_flip_economics

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
    ext_id = (item.get("external_listing_id") or f"ebay-{index}").strip()
    year_econ: int | None = None
    if item.get("year") is not None:
        try:
            year_econ = int(item.get("year"))
        except (TypeError, ValueError):
            year_econ = None
    mileage_raw = item.get("mileage")
    mileage: int | None = None
    if mileage_raw is not None:
        try:
            mileage = int(mileage_raw)
        except (TypeError, ValueError):
            mileage = None
    cond_raw = item.get("condition")
    condition = (str(cond_raw).strip() if cond_raw is not None else None) or None
    vtitle_raw = item.get("vehicle_title")
    vehicle_title = (str(vtitle_raw).strip() if vtitle_raw is not None else None) or None
    econ = estimate_flip_economics(
        price,
        year=year_econ,
        mileage=mileage,
        condition=condition,
        vehicle_title=vehicle_title,
        listing_format=item.get("listing_format") or "BUY_IT_NOW",
        listing_id=ext_id,
        title_text=title,
    )
    repair = econ["repair_cost"]
    resale = econ["resale_value"]
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

    listing_ends_at_raw = item.get("listing_ends_at")
    listing_ends_at = None
    if isinstance(listing_ends_at_raw, datetime):
        listing_ends_at = listing_ends_at_raw
    elif isinstance(listing_ends_at_raw, str) and listing_ends_at_raw.strip():
        try:
            listing_ends_at = datetime.fromisoformat(listing_ends_at_raw.replace("Z", "+00:00"))
        except ValueError:
            listing_ends_at = None
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

    fetch_cap = ebay_fetch_cap()
    cat = (os.getenv("EBAY_CATEGORY_IDS") or "6001").strip()
    cache_key = f"{q.lower()}|cat={cat}|lim={_ebay_search_limit()}|p={_ebay_search_pages()}"
    now = time.time()
    cached = _ebay_cache.get(cache_key)
    if cached and cached[0] > now:
        return list(cached[1])

    raw = client.search_listings_enriched(query=q, limit=min(limit, fetch_cap))
    views: list[Any] = []
    idx = 0
    for item in raw:
        if not is_likely_vehicle_listing(item):
            continue
        idx += 1
        view = ebay_listing_dict_to_car_view(item, idx)
        if view is not None:
            views.append(view)

    logger.info(
        "eBay fetch query=%r category=%r raw=%d kept=%d",
        q,
        cat or "(none)",
        len(raw),
        len(views),
    )
    if views:
        _ebay_cache[cache_key] = (now + _CACHE_TTL_SEC, views)
    else:
        logger.warning(
            "eBay inventory fetch returned no usable listings for query=%r "
            "(raw=%d after sandbox/category settings)",
            q,
            len(raw),
        )
    return views


def probe_ebay_search(query: str | None = None, *, limit: int = 5) -> dict[str, Any]:
    """Diagnostic call for /api/ebay/health — does not use cache or vehicle filter."""
    client = get_ebay_client()
    if not client.is_configured():
        return {"configured": False, "raw_count": 0, "kept_count": 0, "sample": []}

    cap = max(1, min(int(limit or 5), 10))
    q = (query or _default_ebay_query()).strip() or _default_ebay_query()
    cat = _ebay_category_ids()
    attempts: list[dict[str, Any]] = []

    for label, attempt_q, attempt_cat in (
        ("category_and_query", q, cat),
        ("category_only", None, cat),
        ("query_no_category", q, None),
        ("make_model_query", "Toyota Camry", cat),
    ):
        if not attempt_q and not attempt_cat:
            continue
        diag = client._search_request(
            query=attempt_q,
            limit=cap,
            category_ids=attempt_cat,
        )
        rows = client._items_to_rows(diag.get("items") or [], cap)
        attempts.append(
            {
                "label": label,
                "query": attempt_q,
                "category_ids": attempt_cat,
                "http_status": diag.get("http_status"),
                "api_total": diag.get("total"),
                "raw_count": len(rows),
                "error": diag.get("error"),
                "filter": diag.get("filter"),
                "sample_titles": [(r.get("title") or "")[:80] for r in rows[:3]],
            }
        )
        if rows:
            summaries = rows
            break
    else:
        summaries = []

    kept = [s for s in summaries if is_likely_vehicle_listing(s)]
    sample = [
        {
            "title": (s.get("title") or "")[:140],
            "price": s.get("price"),
            "kept_by_filter": is_likely_vehicle_listing(s),
        }
        for s in summaries[:cap]
    ]
    return {
        "configured": True,
        "query": q,
        "raw_count": len(summaries),
        "kept_count": len(kept),
        "sample": sample,
        "attempts": attempts,
        "hint": (
            "Browse API returns only Buy-It-Now by default; we send "
            "filter=buyingOptions:{AUCTION|FIXED_PRICE} for vehicle listings."
        ),
    }
