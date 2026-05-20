"""Map eBay Browse `getItem` JSON into fields used by the inventory UI."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from app.integrations.ebay.get_item_mapping import (
    ADDITIONAL_IMAGES_KEY,
    DELIVERY_OPTION_FLAGS,
    PRIMARY_IMAGE_KEY,
    SELLER_JSON_KEYS,
)

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
_MILEAGE_RE = re.compile(r"([\d,]+)")

_VEHICLE_TITLE_ASPECT_NAMES = frozenset(
    {
        "title",
        "title status",
        "vehicle title",
        "certificate of title",
    }
)

_MILEAGE_ASPECT_NAMES = frozenset({"mileage", "odometer"})


def _first_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list) and value:
        return _first_str(value[0])
    return None


def _aspect_value_map(localized_aspects: Any) -> dict[str, str]:
    if not isinstance(localized_aspects, list):
        return {}
    out: dict[str, str] = {}
    for entry in localized_aspects:
        if not isinstance(entry, dict):
            continue
        name = _first_str(entry.get("localizedAspectName") or entry.get("name"))
        if not name:
            continue
        vals = entry.get("localizedAspectValues") or entry.get("values")
        picked = _first_str(vals)
        if picked:
            out[name.strip().lower()] = picked
    return out


def _pick_aspect(amap: dict[str, str], names: tuple[str, ...]) -> Optional[str]:
    for n in names:
        v = amap.get(n.lower())
        if v:
            return v
    return None


def _parse_mileage(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    m = _MILEAGE_RE.search(raw.replace(" ", ""))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_year_from_title(title: str) -> Optional[int]:
    m = _YEAR_RE.search(title or "")
    return int(m.group(1)) if m else None


def _normalize_listing_format_from_options(options: Any) -> str:
    if not isinstance(options, list) or not options:
        return "BUY_IT_NOW"
    joined = " ".join(str(o).upper() for o in options)
    if "ACCEPT" in joined and "OFFER" in joined:
        return "ACCEPTS_OFFER"
    if "AUCTION" in joined and "FIXED" not in joined:
        return "AUCTION"
    if "AUCTION" in joined:
        return "AUCTION"
    if "CLASSIFIED" in joined:
        return "CLASSIFIED_AD"
    return "BUY_IT_NOW"


def _parse_item_location(item: dict[str, Any]) -> dict[str, Optional[str]]:
    loc = item.get("itemLocation") or {}
    addr = loc.get("address") if isinstance(loc.get("address"), dict) else loc
    if not isinstance(addr, dict):
        addr = {}
    country = _first_str(addr.get("country") or loc.get("country"))
    if country and len(country) == 2:
        country = "United States" if country.upper() == "US" else country
    region = _first_str(addr.get("stateOrProvince") or loc.get("stateOrProvince"))
    city = _first_str(addr.get("city") or loc.get("city"))
    postal = _first_str(loc.get("postalCode") or addr.get("postalCode"))
    postal_masked = None
    if postal and len(postal) > 2:
        postal_masked = postal[:2] + "**"
    return {
        "country": country or "United States",
        "region": region or "",
        "city": city or "",
        "postal_code_masked": postal_masked,
    }


def _parse_delivery_flags(item: dict[str, Any]) -> dict[str, bool]:
    flags = {k: False for k in DELIVERY_OPTION_FLAGS}
    options: set[str] = set()
    for avail in item.get("estimatedAvailabilities") or []:
        if not isinstance(avail, dict):
            continue
        for opt in avail.get("deliveryOptions") or []:
            if isinstance(opt, str):
                options.add(opt.upper())
    for ship in item.get("shippingOptions") or []:
        if isinstance(ship, dict):
            t = _first_str(ship.get("shippingCostType") or ship.get("type"))
            if t:
                options.add(t.upper())
    if not options and item.get("shipToLocations"):
        options.add("SHIP_TO_HOME")
    for flag, codes in DELIVERY_OPTION_FLAGS.items():
        if any(code in options for code in codes):
            flags[flag] = True
    if not any(flags.values()):
        flags["ship_to_home"] = True
    return flags


def _collect_image_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = item.get(PRIMARY_IMAGE_KEY) or {}
    if isinstance(primary, dict):
        u = primary.get("imageUrl")
        if u:
            urls.append(u)
    for extra in item.get(ADDITIONAL_IMAGES_KEY) or []:
        if isinstance(extra, dict) and extra.get("imageUrl"):
            urls.append(extra["imageUrl"])
    return urls


def _parse_listing_end(iso: Any) -> Optional[str]:
    if not iso or not isinstance(iso, str):
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        return iso


def parse_get_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized inventory fields from a getItem response body."""
    title = _first_str(item.get("title")) or ""
    aspects_raw = item.get("localizedAspects") or []
    amap = _aspect_value_map(aspects_raw)

    brand = _pick_aspect(amap, ("make",))
    model = _pick_aspect(amap, ("model",))
    year_raw = _pick_aspect(amap, ("year",))
    year = None
    if year_raw:
        ym = _YEAR_RE.search(year_raw)
        if ym:
            year = int(ym.group(1))
    if year is None:
        year = _parse_year_from_title(title)

    mileage = _parse_mileage(_pick_aspect(amap, tuple(_MILEAGE_ASPECT_NAMES)))
    vehicle_title = _pick_aspect(amap, tuple(_VEHICLE_TITLE_ASPECT_NAMES))

    cond = item.get("condition") or item.get("conditionDisplayName")
    if isinstance(cond, dict):
        condition = _first_str(cond.get("conditionDisplayName") or cond.get("condition"))
    else:
        condition = _first_str(cond)

    price_block = item.get("price") or {}
    price = None
    currency = None
    if isinstance(price_block, dict):
        price = price_block.get("value")
        currency = price_block.get("currency")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None

    loc = _parse_item_location(item)
    delivery = _parse_delivery_flags(item)
    images = _collect_image_urls(item)

    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    seller_username = None
    for key in SELLER_JSON_KEYS:
        seller_username = _first_str(seller.get(key))
        if seller_username:
            break

    return {
        "external_listing_id": item.get("itemId"),
        "title": title,
        "brand": brand,
        "model": model,
        "year": year,
        "price": price_f,
        "currency": currency,
        "condition": condition,
        "mileage": mileage,
        "vehicle_title": vehicle_title,
        "listing_format": _normalize_listing_format_from_options(item.get("buyingOptions")),
        "listing_url": item.get("itemWebUrl"),
        "image_urls": images,
        "image_url": images[0] if images else None,
        "location": loc,
        "delivery": delivery,
        "seller_username": seller_username,
        "bid_count": item.get("bidCount"),
        "listing_ends_at": _parse_listing_end(item.get("itemEndDate")),
        "description_summary": _first_str(item.get("shortDescription")) or title[:512],
        "aspects_json": aspects_raw,
        "source": "ebay",
    }


def merge_search_summary(
    search_row: dict[str, Any], detail: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Prefer getItem fields; fill gaps from item_summary search row."""
    merged = dict(search_row)
    if not detail:
        return merged
    parsed = parse_get_item(detail)
    for key, val in parsed.items():
        if val is None or val == "" or val == []:
            continue
        if key == "location" and isinstance(val, dict):
            prev = merged.get("location") if isinstance(merged.get("location"), dict) else {}
            merged["location"] = {**prev, **{k: v for k, v in val.items() if v}}
            continue
        merged[key] = val
    if not merged.get("title") and search_row.get("title"):
        merged["title"] = search_row["title"]
    if merged.get("price") is None and search_row.get("price") is not None:
        merged["price"] = search_row["price"]
    if not merged.get("image_url") and search_row.get("image_url"):
        merged["image_url"] = search_row["image_url"]
        merged.setdefault("image_urls", [search_row["image_url"]])
    return merged
