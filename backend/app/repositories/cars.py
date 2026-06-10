from __future__ import annotations

import difflib
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import in_memory_demo_enabled
from app.demo_seed import build_in_memory_demo_car_views, pick_media_urls_for_car
from app.integrations.ebay.client import get_ebay_client
from app.integrations.ebay.inventory import invalidate_ebay_inventory_cache, resolve_listing_url
from app.integrations.ebay.parse_item import (
    _coerce_listing_year,
    is_plausible_odometer,
    resolve_listing_mileage,
    resolve_vehicle_facets,
)
from app.models.car import Car
from app.services.flip import calculate_flip_score, flip_metrics_unknown
from app.services.geo import haversine_km, latlng_pair
from app.services.search_query import meaningful_query_tokens, normalize_search_key
from app.services.vehicle_aspects import (
    aspects_to_display_rows,
    extended_vehicle_fields_from_aspects_json,
)

_in_memory_demo_cache: list[Any] | None = None

# Used-car slider defaults when listings omit mileage (matches demo_seed.py span).
_MILEAGE_BOUNDS_DEFAULT_MIN = 8000
_MILEAGE_BOUNDS_DEFAULT_MAX = 145000
_YEAR_SLIDER_MIN = 2000
_YEAR_SLIDER_MAX = 2025
_PRICE_SLIDER_MIN = 0.0


def _year_slider_bounds() -> tuple[int, int]:
    return _YEAR_SLIDER_MIN, _YEAR_SLIDER_MAX


logger = logging.getLogger(__name__)


def _listing_mileage_mi(car: Any) -> int | None:
    """Plausible odometer from listing, or None when unknown."""
    mm = getattr(car, "mileage", None)
    if mm is None:
        return None
    try:
        mi = int(mm)
    except (TypeError, ValueError):
        return None
    if is_plausible_odometer(mi):
        return mi
    return None


def _raw_listing_dict(car: Any) -> dict[str, Any] | None:
    raw = getattr(car, "raw_listing_json", None)
    return raw if isinstance(raw, dict) else None


def _description_from_raw_listing(raw: dict[str, Any]) -> str | None:
    for key in ("description", "Description"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _listing_description_full(car: Any) -> str | None:
    """Full HTML/text description — prefer the longest available source."""
    candidates: list[str] = []
    stored = getattr(car, "description_full", None)
    if isinstance(stored, str) and stored.strip():
        candidates.append(stored.strip())
    raw = _raw_listing_dict(car)
    if raw:
        raw_desc = _description_from_raw_listing(raw)
        if raw_desc:
            candidates.append(raw_desc)
        try:
            aspects_json = _latest_aspects_json(car)
            if not aspects_json:
                aspects_json = raw.get("localizedAspects") or raw.get("aspects_json")
            from app.services.vehicle_aspects import extract_aspect_value

            aspect_desc = extract_aspect_value(
                aspects_json,
                ("description", "item description", "seller's item description"),
            )
            if aspect_desc:
                candidates.append(aspect_desc)
        except Exception:
            pass
    if not candidates:
        return None
    return max(candidates, key=len)


def _listing_title(car: Any) -> str:
    raw = _raw_listing_dict(car)
    if raw:
        title = (raw.get("title") or "").strip()
        if title:
            return title
    return (getattr(car, "description_summary", None) or "").strip()


def _vehicle_display_fields(car: Any) -> tuple[str, str, int | None, int | None]:
    """Resolve brand/model/year/mileage for API output (DB + raw JSON + title)."""
    raw = _raw_listing_dict(car)
    title = _listing_title(car)
    aspects = raw.get("aspects_json") if raw else None
    facets = resolve_vehicle_facets(
        title,
        brand_hint=car.brand,
        model_hint=car.model,
        year_hint=car.year,
        aspects=aspects,
    )
    mileage = _listing_mileage_mi(car)
    if mileage is None:
        mileage = resolve_listing_mileage(
            title,
            mileage_hint=raw.get("mileage") if raw else None,
            aspects=aspects,
        )
    brand = facets["brand"] or car.brand
    model = facets["model"] or car.model
    year = facets["year"] if facets["year"] is not None else car.year
    if year is None and _coerce_listing_year(car.brand or ""):
        year = _coerce_listing_year(car.brand)
        if brand == str(year):
            brand = facets["brand"] or "Unknown"
    return brand, model, year, mileage


def _demo_catalog_slider_bounds() -> tuple[tuple[float, float], tuple[int, int]]:
    """Wide price/mileage spans for filter sliders; year range is fixed (_year_slider_bounds)."""
    demo = list(_get_cached_in_memory_cars())
    if not demo:
        return (_PRICE_SLIDER_MIN, 42500.0), (
            _MILEAGE_BOUNDS_DEFAULT_MIN,
            _MILEAGE_BOUNDS_DEFAULT_MAX,
        )
    prices = [float(c.price) for c in demo]
    mileages = [int(c.mileage) for c in demo if getattr(c, "mileage", None) is not None]
    price_bounds = (_PRICE_SLIDER_MIN, max(prices))
    if mileages:
        mileage_bounds = (min(mileages), max(mileages))
    else:
        mileage_bounds = (_MILEAGE_BOUNDS_DEFAULT_MIN, _MILEAGE_BOUNDS_DEFAULT_MAX)
    return price_bounds, mileage_bounds


def _resolve_mileage_meta_bounds(cars: list, *, inventory_source: str) -> tuple[int, int]:
    """Min/max mileage for filter sliders (real values, else demo catalog span)."""
    if inventory_source == "ebay":
        return _demo_catalog_slider_bounds()[1]
    values: list[int] = []
    for car in cars:
        mm = getattr(car, "mileage", None)
        if mm is None:
            continue
        mi = int(mm)
        if is_plausible_odometer(mi):
            values.append(mi)
    if len(values) >= 2 and max(values) > min(values):
        return min(values), max(values)
    return (_MILEAGE_BOUNDS_DEFAULT_MIN, _MILEAGE_BOUNDS_DEFAULT_MAX)


_US_COUNTRY_ALIASES = frozenset({"united states", "us", "usa", "u.s.", "u.s.a."})

LOCATION_NOT_SPECIFIED = "__not_specified__"


def _normalize_country_key(value: str) -> str:
    v = (value or "").strip().lower()
    if v in _US_COUNTRY_ALIASES:
        return "united states"
    return v


def _is_location_blank(value: Any) -> bool:
    if value is None:
        return True
    v = str(value).strip()
    return not v or v == "—" or v.lower() in ("not specified", "unknown")


def _country_is_unknown(car: Any) -> bool:
    loc = getattr(car, "location", None)
    return loc is None or _is_location_blank(loc.country)


def _region_is_unknown(car: Any) -> bool:
    loc = getattr(car, "location", None)
    if loc is None or _is_location_blank(loc.country):
        return False
    return _is_location_blank(loc.region)


def _city_is_unknown(car: Any) -> bool:
    loc = getattr(car, "location", None)
    if loc is None or _is_location_blank(loc.country) or _is_location_blank(loc.region):
        return False
    return _is_location_blank(loc.city)


def _wants_not_specified(values: list[str]) -> bool:
    return any(v == LOCATION_NOT_SPECIFIED or v == "__not_specified__" for v in values)


def _listing_ends_at_iso(value: Any) -> str | None:
    """Normalize listing end time for API JSON (DB rows use datetime; eBay uses ISO strings)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def invalidate_in_memory_demo_cache() -> None:
    """Clear cached in-memory catalog (e.g. after tests or process reload)."""
    global _in_memory_demo_cache
    _in_memory_demo_cache = None
    invalidate_ebay_inventory_cache()


def _stored_cars_exist(db: Session) -> bool:
    return db.execute(select(Car.id).limit(1)).first() is not None


def _get_cached_in_memory_cars() -> list[Any]:
    global _in_memory_demo_cache
    if _in_memory_demo_cache is None:
        _in_memory_demo_cache = build_in_memory_demo_car_views()
    return _in_memory_demo_cache


def load_inventory_cars_from_db(db: Session, *, search_key: str | None = None) -> list[Car]:
    """Load inventory rows from MySQL; optionally scope eBay rows to a search key."""
    stmt = (
        select(Car)
        .options(
            joinedload(Car.external_seller),
            joinedload(Car.location),
            joinedload(Car.listing_terms),
            selectinload(Car.media),
            selectinload(Car.aspect_snapshots),
            selectinload(Car.search_queries),
        )
        .order_by(Car.id)
    )
    if search_key:
        # Include legacy eBay rows (ingest_search_key NULL) — relevance via apply_filters text match.
        stmt = stmt.where(
            or_(
                Car.source != "ebay",
                Car.ingest_search_key == search_key,
                Car.ingest_search_key.is_(None),
            )
        )
    return list(db.scalars(stmt).all())


def load_car_by_id(db: Session, car_id: int) -> Car | None:
    """Load one car with satellites for API serialization."""
    return db.execute(
        select(Car)
        .where(Car.id == car_id)
        .options(
            joinedload(Car.external_seller),
            joinedload(Car.location),
            joinedload(Car.listing_terms),
            selectinload(Car.media),
            selectinload(Car.aspect_snapshots),
            selectinload(Car.search_queries),
        )
    ).scalar_one_or_none()


def car_to_api_item(car: Car) -> dict[str, Any] | None:
    """Serialize a single loaded Car to the same dict shape as GET /cars items."""
    return _build_car_api_dict(car)


def _build_car_api_dict(car: Car) -> dict[str, Any]:
    """Build inventory API dict for one car (no filter exclusions)."""
    ended = auction_has_ended(car)
    disp_brand, disp_model, disp_year, disp_mileage = _vehicle_display_fields(car)
    mi = disp_mileage
    price_known = bool(getattr(car, "price_known", True))
    if price_known:
        analysis = calculate_flip_score(
            car.price, car.resale_value, car.repair_cost or 0, price_known=True
        )
    else:
        analysis = flip_metrics_unknown()
    aspect_fields = _aspect_fields_for_car(car)
    body_style = aspect_fields.get("body_style")
    vt = (getattr(car, "vehicle_title", None) or "").strip()
    loc = car.location
    listing_terms = car.listing_terms
    delivery = None
    if listing_terms is not None:
        delivery = {
            "ship_to_home": listing_terms.ship_to_home,
            "local_pickup": listing_terms.local_pickup,
            "in_store_pickup": listing_terms.in_store_pickup,
        }
    location_out = None
    if loc is not None:
        location_out = {
            "country": loc.country,
            "region": loc.region,
            "city": loc.city,
            "postal_code_masked": loc.postal_code_masked,
        }
    seller_username = None
    es = car.external_seller
    if es is not None:
        seller_username = es.username
    listing_ends_at = _listing_ends_at_iso(car.listing_ends_at)
    image_urls = _image_urls_for_car(car)
    src = (car.source or "manual").strip().lower()
    ebay_sandbox = get_ebay_client().sandbox if src == "ebay" else False
    listing_url_out = resolve_listing_url(
        getattr(car, "external_listing_id", None),
        getattr(car, "listing_url", None),
        sandbox=ebay_sandbox,
    )
    listing_title = _listing_title(car)
    return {
        "id": car.id,
        "brand": disp_brand,
        "model": disp_model,
        "year": disp_year,
        "price": car.price,
        "price_known": price_known,
        "repair_cost": car.repair_cost,
        "resale_value": car.resale_value,
        "mileage": mi,
        "condition": car.condition,
        "vehicle_title": vt or None,
        "image_url": image_urls[0] if image_urls else car.image_url,
        "images": image_urls,
        "body_style": body_style,
        "drive_type": aspect_fields.get("drive_type"),
        "vin": aspect_fields.get("vin"),
        "transmission": aspect_fields.get("transmission"),
        "trim": aspect_fields.get("trim"),
        "engine": aspect_fields.get("engine"),
        "fuel_type": aspect_fields.get("fuel_type"),
        "fuel_city": aspect_fields.get("fuel_city"),
        "fuel_highway": aspect_fields.get("fuel_highway"),
        "source": car.source or "manual",
        "external_listing_id": car.external_listing_id,
        "listing_url": listing_url_out,
        "listing_ends_at": listing_ends_at,
        "auction_ended": ended,
        "bid_count": car.bid_count,
        "listing_format": _normalize_listing_format(car.listing_format) or car.listing_format,
        "description_summary": getattr(car, "description_summary", None),
        "listing_title": listing_title or None,
        "resale_method": getattr(car, "resale_method", None),
        "resale_confidence": getattr(car, "resale_confidence", None),
        "resale_comp_count": getattr(car, "resale_comp_count", None),
        "resale_segment_key": getattr(car, "resale_segment_key", None),
        "resale_estimated_at": _listing_ends_at_iso(getattr(car, "resale_estimated_at", None)),
        "seller_username": seller_username,
        "location": location_out,
        "delivery": delivery,
        **analysis,
    }


def car_to_detail_api_item(
    db: Session,
    car: Car,
    *,
    user_id: int | None = None,
    geocode: bool = True,
) -> dict[str, Any] | None:
    """Extended car payload for the detail page."""
    from app.services.geocode import ensure_car_location_coords
    from app.services.watchlist import is_car_watched

    item = car_to_api_item(car)
    if item is None:
        return None
    item["description_html"] = _listing_description_full(car)
    item["description_summary"] = getattr(car, "description_summary", None) or item.get(
        "description_summary"
    )
    try:
        aspects_json = _latest_aspects_json(car)
        if not aspects_json:
            raw = _raw_listing_dict(car)
            if raw:
                aspects_json = raw.get("localizedAspects") or raw.get("aspects_json")
        item["listing_aspects"] = aspects_to_display_rows(aspects_json)
    except Exception:
        item["listing_aspects"] = []
    item["is_watched"] = is_car_watched(db, user_id, int(car.id)) if user_id else False
    if car.location is not None:
        if geocode:
            try:
                item["location"] = ensure_car_location_coords(db, int(car.id), car.location)
            except Exception:
                loc = car.location
                item["location"] = {
                    "country": loc.country,
                    "region": loc.region,
                    "city": loc.city,
                    "postal_code_masked": loc.postal_code_masked,
                    "latitude": float(loc.latitude) if loc.latitude is not None else None,
                    "longitude": float(loc.longitude) if loc.longitude is not None else None,
                }
        else:
            loc = car.location
            item["location"] = {
                **(item.get("location") or {}),
                "country": loc.country,
                "region": loc.region,
                "city": loc.city,
                "postal_code_masked": loc.postal_code_masked,
                "latitude": float(loc.latitude) if loc.latitude is not None else None,
                "longitude": float(loc.longitude) if loc.longitude is not None else None,
            }
            boundary = getattr(loc, "boundary_geojson", None)
            if boundary:
                item["location"]["boundary_geojson"] = boundary
    return item


def load_inventory_for_request(db: Session, *, search_key: str | None = None) -> list:
    """DB inventory, or in-memory demo when the cars table is empty."""
    if _stored_cars_exist(db):
        return load_inventory_cars_from_db(db, search_key=search_key)
    if in_memory_demo_enabled():
        return list(_get_cached_in_memory_cars())
    return []


def iter_cars(db: Session, *, inventory_query: str | None = None):
    del inventory_query  # eBay ingest is explicit via sync_ebay_inventory
    return load_inventory_cars_from_db(db)


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


def is_auction_listing(car: Any) -> bool:
    fmt = _normalize_listing_format(getattr(car, "listing_format", None))
    return fmt == "AUCTION"


def auction_has_ended(car: Any, *, now: datetime | None = None) -> bool:
    if not is_auction_listing(car):
        return False
    ends = _parse_listing_ends_at(getattr(car, "listing_ends_at", None))
    if ends is None:
        return False
    ref = now or datetime.now(timezone.utc)
    return ends <= ref


def _listing_is_active(car: Any, *, now: datetime | None = None) -> bool:
    """True when listing_ends_at is unset or still in the future."""
    ends = _parse_listing_ends_at(getattr(car, "listing_ends_at", None))
    if ends is None:
        return True
    ref = now or datetime.now(timezone.utc)
    return ends > ref


def mark_expired_auctions(db: Session, *, now: datetime | None = None) -> int:
    """Set auction_ended_at on auction rows whose end time has passed."""
    ref = now or datetime.now(timezone.utc)
    stmt = (
        update(Car)
        .where(
            Car.listing_format.ilike("%AUCTION%"),
            Car.listing_ends_at.isnot(None),
            Car.listing_ends_at <= ref,
            Car.auction_ended_at.is_(None),
        )
        .values(auction_ended_at=ref)
    )
    result = db.execute(stmt)
    return int(result.rowcount or 0)


def _latest_aspects_json(car: Car) -> Any:
    snaps = car.aspect_snapshots
    if not snaps:
        return None
    return max(
        snaps, key=lambda s: (s.captured_at.timestamp() if s.captured_at else 0.0, s.id)
    ).aspects_json


def _aspect_fields_for_car(car: Car) -> dict[str, Optional[str]]:
    return extended_vehicle_fields_from_aspects_json(_latest_aspects_json(car))


def _body_style_for_car(car: Car) -> Optional[str]:
    return _aspect_fields_for_car(car).get("body_style")


def _drive_type_for_car(car: Car) -> Optional[str]:
    return _aspect_fields_for_car(car).get("drive_type")


def _is_demo_inventory_car(car: Any) -> bool:
    src = (getattr(car, "source", None) or "").strip().lower()
    if src == "demo":
        return True
    ext = (getattr(car, "external_listing_id", None) or "").strip()
    return ext.startswith("demo-")


def _image_urls_for_car(car: Car) -> list[str]:
    brand = getattr(car, "brand", "") or ""
    model = getattr(car, "model", "") or ""
    idx = max((getattr(car, "id", None) or 1) - 1, 0)

    def _catalog_urls() -> list[str]:
        return pick_media_urls_for_car(brand, model, idx)

    # Demo / legacy seed rows may still store picsum URLs in DB — always serve catalog photos.
    if _is_demo_inventory_car(car):
        catalog = _catalog_urls()
        if catalog:
            return catalog

    urls: list[str] = []
    if car.media:
        for m in sorted(car.media, key=lambda x: x.sort_order):
            if m.url:
                urls.append(m.url)
    if not urls and car.image_url:
        urls.append(car.image_url)
    if urls and all("picsum.photos" in u for u in urls):
        catalog = _catalog_urls()
        if catalog:
            return catalog
    return urls


def _normalize_listing_format(value: Optional[str]) -> str:
    if not value or not isinstance(value, str):
        return ""
    v = value.strip().upper().replace("-", "_").replace(" ", "_")
    # "ACCEPTS_OFFER" contains the substring "AUCTION" — check offers before auction.
    if v == "ACCEPTS_OFFER" or ("ACCEPT" in v and "OFFER" in v):
        return "ACCEPTS_OFFER"
    if "CLASSIFIED" in v:
        return "CLASSIFIED_AD"
    if "AUCTION" in v:
        return "AUCTION"
    if "FIXED" in v or "BUY_IT_NOW" in v or "BUYITNOW" in v or ("BUY" in v and "NOW" in v):
        return "BUY_IT_NOW"
    return v


def _q_tokens(q: Optional[str]) -> list[str]:
    """Raw lowercase tokens (used for default sort detection)."""
    from app.services.search_query import split_query_tokens

    return split_query_tokens(q)


def _car_matches_q_soft(
    *,
    brand: str,
    model: str,
    year: int,
    city: str,
    region: str,
    country: str,
    listing_format: str,
    condition: str,
    body_style: Optional[str],
    vehicle_title: str,
    drive_type: Optional[str],
    description_summary: str,
    tokens: list[str],
) -> bool:
    """Relevance match: phrase or all tokens (AND) in listing text fields."""
    if not tokens:
        return True
    haystack = " ".join(
        [
            brand.lower(),
            model.lower(),
            str(year),
            (body_style or "").lower(),
            vehicle_title.lower(),
            (drive_type or "").lower(),
            condition.lower(),
            listing_format.lower(),
            description_summary[:512].lower(),
            city.lower(),
            region.lower(),
            country.lower(),
        ]
    )
    full_phrase = " ".join(tokens)
    if full_phrase in haystack:
        return True
    vehicle_text = " ".join(
        [
            brand.lower(),
            model.lower(),
            (body_style or "").lower(),
            vehicle_title.lower(),
            (drive_type or "").lower(),
            description_summary[:512].lower(),
        ]
    )
    if all(t in vehicle_text for t in tokens):
        return True
    if all(t in haystack for t in tokens):
        return True
    if len(tokens) <= 2:
        brand_model = f"{brand} {model}".lower()
        if difflib.SequenceMatcher(None, brand_model, full_phrase).ratio() >= 0.58:
            return True
    return False


def _query_history_tokens(car: Any) -> list[str]:
    out: list[str] = []
    for row in getattr(car, "search_queries", []) or []:
        qk = (getattr(row, "query_key", None) or "").strip().lower()
        qt = (getattr(row, "query_text", None) or "").strip().lower()
        if qk:
            out.append(qk)
        if qt and qt != qk:
            out.append(qt)
    return out


def _car_search_score(
    *,
    car: Any,
    tokens: list[str],
    listing_title: str,
    brand: str,
    model: str,
    city: str,
    region: str,
    country: str,
    description_summary: str,
    aspect_fields: dict[str, Any],
) -> float:
    if not tokens:
        return 0.0
    score = 0.0
    t_title = listing_title.lower()
    t_brand = brand.lower()
    t_model = model.lower()
    t_desc = description_summary.lower()
    t_loc = " ".join([city.lower(), region.lower(), country.lower()]).strip()
    medium_fields = " ".join(
        [
            str(aspect_fields.get("trim") or "").lower(),
            str(aspect_fields.get("engine") or "").lower(),
            str(aspect_fields.get("transmission") or "").lower(),
            str(aspect_fields.get("fuel_type") or "").lower(),
            str(aspect_fields.get("body_style") or "").lower(),
            str(aspect_fields.get("drive_type") or "").lower(),
        ]
    )
    query_history = _query_history_tokens(car)
    for tok in tokens:
        if tok in t_title:
            score += 8.0
        if t_title.startswith(tok):
            score += 2.0
        if tok == t_brand or tok == t_model:
            score += 8.0
        elif tok in t_brand or tok in t_model:
            score += 5.0
        if tok in medium_fields:
            score += 3.0
        if tok in t_desc:
            score += 1.0
        if tok in t_loc:
            score += 1.0
        if any(tok in q for q in query_history):
            score += 6.0
    full_phrase = " ".join(tokens)
    if full_phrase:
        if full_phrase in t_title:
            score += 4.0
        if any(full_phrase in q for q in query_history):
            score += 4.0
    return score


def _delivery_matches_modes(listing_terms: Any, modes: list[str]) -> bool:
    if not modes:
        return True
    if listing_terms is None:
        return False
    mode_map = {
        "ship": listing_terms.ship_to_home,
        "local_pickup": listing_terms.local_pickup,
        "in_store": listing_terms.in_store_pickup,
    }
    return any(mode_map.get(m, False) for m in modes if m in mode_map)


def _location_within_radius(
    loc: Any,
    anchor_lat: float,
    anchor_lng: float,
    radius_km: float,
) -> bool:
    pair = latlng_pair(loc.latitude, loc.longitude) if loc else None
    if pair is None:
        return False
    lat, lon = pair
    return haversine_km(anchor_lat, anchor_lng, lat, lon) <= radius_km


def _effective_radius_km(radius_km: Optional[float], radius_mi: Optional[float]) -> Optional[float]:
    """Prefer miles when provided; else kilometers."""
    if radius_mi is not None and radius_mi > 0:
        return float(radius_mi) * 1.609344
    if radius_km is not None and radius_km > 0:
        return float(radius_km)
    return None


def _metrics_unavailable(item: dict[str, Any]) -> bool:
    """No purchase price → ROI/profit cannot be ranked (sort like zero / worst tier)."""
    return not item.get("price_known", True)


def _unknown_metrics_rank(item: dict[str, Any]) -> int:
    return 1 if _metrics_unavailable(item) else 0


def sort_car_dicts_inplace(
    results: list[dict[str, Any]], sort_by: Optional[str], sort_order: Optional[str]
) -> None:
    if not sort_by:
        return
    reverse_sort = (sort_order or "desc") == "desc"

    def _profit_value(x: dict[str, Any]) -> float:
        return float(x.get("net_profit") or 0.0)

    def _roi_value(x: dict[str, Any]) -> float:
        return float(x.get("roi") or 0.0)

    def _price_value(x: dict[str, Any]) -> float:
        return float(x.get("price") or 0.0)

    if sort_by == "net_profit":
        results.sort(
            key=lambda x: (
                _unknown_metrics_rank(x),
                -_profit_value(x) if reverse_sort else _profit_value(x),
            ),
        )
    elif sort_by == "price":
        results.sort(
            key=lambda x: (
                1 if not x.get("price_known", True) else 0,
                -_price_value(x) if reverse_sort else _price_value(x),
            ),
        )
    elif sort_by == "roi":
        results.sort(
            key=lambda x: (
                _unknown_metrics_rank(x),
                -_roi_value(x) if reverse_sort else _roi_value(x),
            ),
        )


def apply_filters(
    cars: list,
    make: Optional[str],
    makes: Optional[list[str]],
    model: Optional[str],
    min_year: Optional[int],
    max_year: Optional[int],
    min_mileage: Optional[int],
    max_mileage: Optional[int],
    condition: Optional[str],
    conditions: Optional[list[str]],
    max_price: Optional[float],
    min_price: Optional[float],
    min_profit: Optional[float],
    min_roi: Optional[float],
    q: Optional[str],
    countries: Optional[list[str]],
    regions: Optional[list[str]],
    cities: Optional[list[str]],
    radius_km: Optional[float],
    radius_mi: Optional[float],
    anchor_lat: Optional[float],
    anchor_lng: Optional[float],
    listing_formats: Optional[list[str]],
    body_styles: Optional[list[str]],
    delivery_modes: Optional[list[str]],
    vehicle_titles: Optional[list[str]],
    exclude_negative_roi: bool = False,
    exclude_negative_profit: bool = False,
    exclude_ended_auctions: bool = True,
    exclude_unknown_price: bool = False,
    skip_listing_activity_filter: bool = False,
) -> list:
    search_key = normalize_search_key(q)
    q_toks = meaningful_query_tokens(q)
    countries_l = [c.strip().lower() for c in (countries or []) if c and str(c).strip()]
    regions_l = [r.strip().lower() for r in (regions or []) if r and str(r).strip()]
    cities_l = [c.strip().lower() for c in (cities or []) if c and str(c).strip()]
    conditions_l = [c.strip().lower() for c in (conditions or []) if c and str(c).strip()]
    if condition and not conditions_l:
        conditions_l = [condition.strip().lower()]
    formats_l = [
        _normalize_listing_format(f) for f in (listing_formats or []) if f and str(f).strip()
    ]
    formats_l = [f for f in formats_l if f]
    body_l = [b.strip().lower() for b in (body_styles or []) if b and str(b).strip()]
    modes_l = [m.strip().lower() for m in (delivery_modes or []) if m and str(m).strip()]
    titles_l = [t.strip().lower() for t in (vehicle_titles or []) if t and str(t).strip()]
    titles_set = frozenset(titles_l)
    makes_l = [m.strip().lower() for m in (makes or []) if m and str(m).strip()]

    eff_radius_km = _effective_radius_km(radius_km, radius_mi)
    use_radius = eff_radius_km is not None and anchor_lat is not None and anchor_lng is not None

    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for car in cars:
        ended = auction_has_ended(car, now=now)
        if not skip_listing_activity_filter:
            active_by_date = _listing_is_active(car, now=now)
            if not active_by_date:
                if is_auction_listing(car) and ended and not exclude_ended_auctions:
                    pass
                else:
                    continue
            if exclude_ended_auctions and ended:
                continue
        disp_brand, disp_model, disp_year, disp_mileage = _vehicle_display_fields(car)
        if makes_l:
            if disp_brand.strip().lower() not in makes_l:
                continue
        elif make and make.lower() not in disp_brand.lower():
            continue
        if model and model.lower() not in disp_model.lower():
            continue

        if min_year is not None or max_year is not None:
            if disp_year is None:
                continue
            if min_year is not None and disp_year < min_year:
                continue
            if max_year is not None and disp_year > max_year:
                continue

        mi = disp_mileage
        if mi is not None:
            if min_mileage is not None and mi < min_mileage:
                continue
            if max_mileage is not None and mi > max_mileage:
                continue

        cond_value = (car.condition or "").strip().lower()
        if conditions_l:
            if not cond_value or cond_value not in conditions_l:
                continue
        elif condition and (not car.condition or condition.lower() not in cond_value):
            continue

        price_known = bool(getattr(car, "price_known", True))
        if exclude_unknown_price and not price_known:
            continue
        if max_price is not None or min_price is not None:
            if not price_known:
                continue
            if max_price is not None and car.price > max_price:
                continue
            if min_price is not None and car.price < min_price:
                continue

        loc = car.location
        if countries_l:
            want_unknown = _wants_not_specified(countries_l)
            allowed_countries = {
                _normalize_country_key(c)
                for c in countries_l
                if c not in (LOCATION_NOT_SPECIFIED, "__not_specified__")
            }
            is_unknown = _country_is_unknown(car)
            cc = "" if is_unknown else _normalize_country_key((loc.country or "") if loc else "")
            ok = bool(want_unknown and is_unknown)
            if not is_unknown and cc in allowed_countries:
                ok = True
            if not ok:
                continue
        if regions_l:
            want_unknown = _wants_not_specified(regions_l)
            allowed_regs = {
                r for r in regions_l if r not in (LOCATION_NOT_SPECIFIED, "__not_specified__")
            }
            is_unknown = _region_is_unknown(car)
            rr = (loc.region or "").strip().lower() if loc and not is_unknown else ""
            ok = bool(want_unknown and is_unknown)
            if not is_unknown and rr in allowed_regs:
                ok = True
            if not ok:
                continue
        if cities_l:
            want_unknown = _wants_not_specified(cities_l)
            allowed_cities = {
                c for c in cities_l if c not in (LOCATION_NOT_SPECIFIED, "__not_specified__")
            }
            is_unknown = _city_is_unknown(car)
            ci = (loc.city or "").strip().lower() if loc and not is_unknown else ""
            ok = bool(want_unknown and is_unknown)
            if not is_unknown and ci in allowed_cities:
                ok = True
            if not ok:
                continue

        if use_radius:
            if loc is None or not _location_within_radius(
                loc, anchor_lat, anchor_lng, eff_radius_km
            ):
                continue

        if formats_l:
            cf = _normalize_listing_format(car.listing_format)
            if not cf or cf not in formats_l:
                continue

        aspect_fields = _aspect_fields_for_car(car)
        body_style = aspect_fields.get("body_style")
        if body_l:
            bs = (body_style or "").strip().lower()
            if not bs or bs not in body_l:
                continue

        vt = (getattr(car, "vehicle_title", None) or "").strip()
        if titles_l:
            vtl = vt.lower()
            if not vtl or vtl not in titles_set:
                continue

        if modes_l and not _delivery_matches_modes(car.listing_terms, modes_l):
            continue

        if price_known:
            analysis = calculate_flip_score(car.price, car.resale_value, car.repair_cost or 0)
        else:
            analysis = flip_metrics_unknown()
        if (exclude_negative_roi or exclude_negative_profit) and analysis.get(
            "net_profit"
        ) is not None:
            if analysis["net_profit"] < 0:
                continue
        if min_profit is not None:
            if analysis.get("net_profit") is None or analysis["net_profit"] < min_profit:
                continue
        if min_roi is not None:
            if analysis.get("roi") is None or analysis["roi"] < min_roi:
                continue

        drive_type = aspect_fields.get("drive_type")

        city_s = (loc.city or "") if loc else ""
        region_s = (loc.region or "") if loc else ""
        country_s = (loc.country or "") if loc else ""

        lf_norm = (
            _normalize_listing_format(car.listing_format)
            or (car.listing_format or "").strip().lower()
        )
        listing_title = _listing_title(car)
        description_summary = getattr(car, "description_summary", None) or ""
        score = 0.0
        if q_toks:
            score = _car_search_score(
                car=car,
                tokens=q_toks,
                listing_title=listing_title,
                brand=disp_brand,
                model=disp_model,
                city=city_s,
                region=region_s,
                country=country_s,
                description_summary=description_summary,
                aspect_fields=aspect_fields,
            )
            if score <= 0.0 and not _car_matches_q_soft(
                brand=disp_brand,
                model=disp_model,
                year=disp_year,
                city=city_s,
                region=region_s,
                country=country_s,
                listing_format=lf_norm,
                condition=car.condition or "",
                body_style=body_style,
                vehicle_title=vt,
                drive_type=drive_type,
                description_summary=description_summary,
                tokens=q_toks,
            ):
                continue

        if search_key:
            src = (getattr(car, "source", None) or "").strip().lower()
            if src == "ebay":
                ingest_key = getattr(car, "ingest_search_key", None)
                if ingest_key and ingest_key != search_key:
                    has_query_match = any(
                        (getattr(row, "query_key", None) or "").strip().lower() == search_key
                        for row in (getattr(car, "search_queries", []) or [])
                    )
                    if not has_query_match:
                        continue

        item = _build_car_api_dict(car)
        if score > 0:
            item["_search_score"] = round(score, 3)
        results.append(item)
    if q_toks:
        results.sort(
            key=lambda x: (float(x.get("_search_score") or 0.0), float(x.get("net_profit") or 0.0)),
            reverse=True,
        )
    return results


def compute_inventory_meta(db: Session) -> dict[str, Any]:
    """Aggregate bounds and location hierarchy for filter UI (no auth logic here)."""
    if _stored_cars_exist(db):
        inventory_source = "database"
        cars = load_inventory_cars_from_db(db)
    elif get_ebay_client().is_configured():
        inventory_source = "database"
        cars = []
    elif in_memory_demo_enabled():
        inventory_source = "demo"
        cars = list(_get_cached_in_memory_cars())
    else:
        inventory_source = "empty"
        cars = []

    if not cars:
        (price_lo, price_hi), (mi_lo, mi_hi) = _demo_catalog_slider_bounds()
        year_lo, year_hi = _year_slider_bounds()
        return {
            "inventory_source": inventory_source,
            "min_price": price_lo,
            "max_price": price_hi,
            "min_year": year_lo,
            "max_year": year_hi,
            "min_mileage": mi_lo,
            "max_mileage": mi_hi,
            "countries": [],
            "regions_by_country": {},
            "cities_by_region": {},
            "location_anchors": [],
            "conditions": [],
            "body_styles": [],
            "listing_formats": [],
            "makes": [],
            "vehicle_titles": [],
            "location_not_specified": {"country": False, "region": False, "city": False},
        }

    year_values = [int(c.year) for c in cars if getattr(c, "year", None) is not None]
    if year_values:
        year_lo, year_hi = min(year_values), max(year_values)
    else:
        year_lo, year_hi = _year_slider_bounds()
    prices = [float(c.price) for c in cars]
    price_lo, price_hi = _PRICE_SLIDER_MIN, max(prices)
    mi_lo, mi_hi = _resolve_mileage_meta_bounds(cars, inventory_source=inventory_source)

    conditions_set: set[str] = set()
    body_styles_set: set[str] = set()
    formats_set: set[str] = set()
    titles_set: set[str] = set()
    makes_set: set[str] = set()
    countries: set[str] = set()
    regions_by_country: dict[str, set[str]] = {}
    cities_by_region: dict[str, set[str]] = {}
    anchors: dict[str, dict[str, Any]] = {}
    loc_ns = {"country": False, "region": False, "city": False}

    for car in cars:
        makes_set.add(car.brand.strip())
        if car.condition and str(car.condition).strip():
            conditions_set.add(str(car.condition).strip())
        bs = _body_style_for_car(car)
        if bs:
            body_styles_set.add(bs)
        if car.listing_format and str(car.listing_format).strip():
            nf = _normalize_listing_format(car.listing_format)
            if nf:
                formats_set.add(nf)
        vt = getattr(car, "vehicle_title", None)
        if vt and str(vt).strip():
            titles_set.add(str(vt).strip())

        if _country_is_unknown(car):
            loc_ns["country"] = True
            continue

        loc = car.location
        if not loc:
            loc_ns["country"] = True
            continue

        co = (loc.country or "").strip()
        if not co:
            loc_ns["country"] = True
            continue
        countries.add(co)

        if _is_location_blank(loc.region):
            loc_ns["region"] = True
            continue

        reg = (loc.region or "").strip()
        regions_by_country.setdefault(co, set()).add(reg)

        if _is_location_blank(loc.city):
            loc_ns["city"] = True
            continue

        city = (loc.city or "").strip()
        rkey = f"{co}|{reg}"
        cities_by_region.setdefault(rkey, set()).add(city)
        pair = latlng_pair(loc.latitude, loc.longitude)
        if pair:
            lat, lon = pair
            key = f"{co}|{reg}|{city}"
            anchors.setdefault(
                key,
                {
                    "country": co,
                    "region": reg,
                    "city": city,
                    "lat": lat,
                    "lng": lon,
                },
            )

    return {
        "inventory_source": inventory_source,
        "min_price": float(price_lo),
        "max_price": float(price_hi),
        "min_year": int(year_lo),
        "max_year": int(year_hi),
        "min_mileage": int(mi_lo),
        "max_mileage": int(mi_hi),
        "countries": sorted(countries, key=str.lower),
        "regions_by_country": {
            k: sorted(v, key=str.lower) for k, v in sorted(regions_by_country.items())
        },
        "cities_by_region": {
            k: sorted(v, key=str.lower) for k, v in sorted(cities_by_region.items())
        },
        "location_anchors": sorted(
            anchors.values(), key=lambda a: (a["country"], a["region"], a["city"])
        ),
        "conditions": sorted(conditions_set, key=str.lower),
        "body_styles": sorted(body_styles_set, key=str.lower),
        "listing_formats": sorted(formats_set, key=str.lower),
        "makes": sorted(makes_set, key=str.lower),
        "vehicle_titles": sorted(titles_set, key=str.lower),
        "location_not_specified": loc_ns,
    }
