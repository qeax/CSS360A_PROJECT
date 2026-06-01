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
_MILEAGE_WITH_UNIT_RE = re.compile(
    r"([\d,]+)\s*(?:,\d{3})*\s*(?:mi|miles|mile)\b",
    re.IGNORECASE,
)
_K_MILES_RE = re.compile(
    r"([\d,.]+)\s*k\s*(?:mi|miles|mile)?\b",
    re.IGNORECASE,
)
_DIGITS_RE = re.compile(r"([\d,]+)")

# Typical US used-car odometer range; excludes model years and engine sizes (e.g. 1.5L → 1500).
MIN_PLAUSIBLE_ODOMETER_MI = 5000
MAX_PLAUSIBLE_ODOMETER_MI = 350000

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


def is_plausible_odometer(value: int) -> bool:
    """Reject model years and engine-displacement numbers mistaken for mileage."""
    if 1980 <= value <= 2039:
        return False
    return MIN_PLAUSIBLE_ODOMETER_MI <= value <= MAX_PLAUSIBLE_ODOMETER_MI


def _parse_mileage(raw: Optional[str]) -> Optional[int]:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None

    m = _MILEAGE_WITH_UNIT_RE.search(text)
    if m:
        try:
            value = int(m.group(1).replace(",", ""))
            if is_plausible_odometer(value):
                return value
        except ValueError:
            pass

    km = _K_MILES_RE.search(text)
    if km:
        try:
            value = int(float(km.group(1).replace(",", "")) * 1000)
            if is_plausible_odometer(value):
                return value
        except ValueError:
            pass

    candidates: list[int] = []
    for match in _DIGITS_RE.finditer(text):
        try:
            value = int(match.group(1).replace(",", ""))
        except ValueError:
            continue
        if is_plausible_odometer(value):
            candidates.append(value)
    if not candidates:
        return None
    return max(candidates)


def _parse_year_from_title(title: str) -> Optional[int]:
    m = _YEAR_RE.search(title or "")
    return int(m.group(1)) if m else None


def _coerce_listing_year(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        y = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        m = _YEAR_RE.search(text)
        if not m:
            return None
        y = int(m.group(1))
    else:
        try:
            y = int(value)
        except (TypeError, ValueError):
            return None
    if 1900 <= y <= 2039:
        return y
    return None


def resolve_listing_year(
    title: str | None,
    *,
    year_hint: Any = None,
    aspects: Any = None,
) -> Optional[int]:
    """Best-effort model year; returns None instead of a placeholder when unknown."""
    amap = _aspect_value_map(aspects) if aspects else {}
    year_raw = _pick_aspect(amap, ("year",))
    y = _coerce_listing_year(year_raw)
    if y is not None:
        return y
    y = _coerce_listing_year(year_hint)
    if y is not None:
        return y
    t = (title or "").strip()
    if not t:
        return None
    parts = t.split()
    if parts and _YEAR_RE.match(parts[0]):
        return int(parts[0])
    years = [int(m.group(1)) for m in _YEAR_RE.finditer(t)]
    years = [yr for yr in years if 1900 <= yr <= 2039]
    if not years:
        return None
    return min(years)


def resolve_vehicle_facets(
    title: str | None,
    *,
    brand_hint: Any = None,
    model_hint: Any = None,
    year_hint: Any = None,
    aspects: Any = None,
) -> dict[str, Optional[str]]:
    """
    Normalize brand, model, year from aspects and title.

    eBay sometimes puts the model year in the Make aspect; relocate to year.
    """
    from app.integrations.ebay.inventory import _parse_brand_model

    amap = _aspect_value_map(aspects) if aspects else {}
    make_raw = _pick_aspect(amap, ("make",))
    model_raw = _pick_aspect(amap, ("model",))

    year = resolve_listing_year(title, year_hint=year_hint, aspects=aspects)

    brand: Optional[str] = None
    if make_raw and not _coerce_listing_year(make_raw):
        brand = make_raw.strip()

    model: Optional[str] = None
    if model_raw and not _coerce_listing_year(model_raw):
        model = model_raw.strip()

    year_from_make = _coerce_listing_year(make_raw) if make_raw else None
    if year_from_make is not None:
        year = year or year_from_make
        brand = None

    year_from_model = _coerce_listing_year(model_raw) if model_raw else None
    if year_from_model is not None:
        year = year or year_from_model
        model = None

    if brand_hint and not _coerce_listing_year(str(brand_hint)):
        hint = str(brand_hint).strip()
        if not brand:
            brand = hint

    if model_hint and not _coerce_listing_year(str(model_hint)):
        hint = str(model_hint).strip()
        if not model:
            model = hint

    if not brand or not model:
        pb, pm = _parse_brand_model(title or "", brand, model)
        if not brand:
            brand = pb
        if not model:
            model = pm

    if brand and _coerce_listing_year(brand):
        year = year or _coerce_listing_year(brand)
        brand = None
        if not model:
            _, pm = _parse_brand_model(title or "", None, None)
            model = pm

    return {
        "brand": (brand or "Unknown")[:100],
        "model": (model or "Listing")[:100],
        "year": year,
    }


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
        "country": country,
        "region": region,
        "city": city,
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

    facets = resolve_vehicle_facets(
        title,
        aspects=aspects_raw,
    )
    brand = facets["brand"]
    model = facets["model"]
    year = facets["year"]

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
