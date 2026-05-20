from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import in_memory_demo_enabled
from app.demo_seed import build_in_memory_demo_car_views, pick_media_urls_for_car
from app.integrations.ebay.client import get_ebay_client
from app.integrations.ebay.inventory import (
    fetch_ebay_inventory_views,
    invalidate_ebay_inventory_cache,
    resolve_listing_url,
)
from app.integrations.ebay.parse_item import is_plausible_odometer
from app.models.car import Car
from app.services.body_style import (
    extract_body_style_from_aspects_json,
    extract_drive_type_from_aspects_json,
)
from app.services.flip import calculate_flip_score
from app.services.geo import haversine_km, latlng_pair

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


def _effective_mileage(car: Any) -> int:
    """Mileage used for filtering when listing data has no odometer."""
    mm = getattr(car, "mileage", None)
    if mm is not None:
        mi = int(mm)
        if is_plausible_odometer(mi):
            return mi
    car_id = getattr(car, "id", None) or 1
    return 75000 + (int(car_id) * 1500) % 90000


def _demo_catalog_slider_bounds() -> tuple[tuple[float, float], tuple[int, int]]:
    """Wide price/mileage spans for filter sliders; year range is fixed (_year_slider_bounds)."""
    demo = list(_get_cached_in_memory_cars())
    if not demo:
        return (_PRICE_SLIDER_MIN, 42500.0), (_MILEAGE_BOUNDS_DEFAULT_MIN, _MILEAGE_BOUNDS_DEFAULT_MAX)
    prices = [float(c.price) for c in demo]
    mileages = [
        int(c.mileage) for c in demo if getattr(c, "mileage", None) is not None
    ]
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
    return _demo_catalog_slider_bounds()[1]

_US_COUNTRY_ALIASES = frozenset({"united states", "us", "usa", "u.s.", "u.s.a."})


def _normalize_country_key(value: str) -> str:
    v = (value or "").strip().lower()
    if v in _US_COUNTRY_ALIASES:
        return "united states"
    return v


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


def _ebay_inventory_for_query(query: str | None) -> list[Any]:
    """Live eBay sandbox/prod listings in memory only (never written to DB)."""
    views = fetch_ebay_inventory_views(query)
    if views:
        return views
    if in_memory_demo_enabled():
        logger.info("eBay unavailable or empty; falling back to demo catalog")
        return list(_get_cached_in_memory_cars())
    logger.warning("eBay returned no vehicle listings (demo disabled); inventory will be empty")
    return []


def _cars_for_inventory(db: Session, *, inventory_query: str | None = None) -> list[Any]:
    if _stored_cars_exist(db):
        return db.scalars(
            select(Car)
            .options(
                joinedload(Car.external_seller),
                joinedload(Car.location),
                joinedload(Car.listing_terms),
                selectinload(Car.media),
                selectinload(Car.aspect_snapshots),
            )
            .order_by(Car.id)
        ).all()
    if get_ebay_client().is_configured():
        return _ebay_inventory_for_query(inventory_query)
    if in_memory_demo_enabled():
        if not get_ebay_client().is_configured():
            logger.warning("eBay credentials missing; serving in-memory demo catalog")
        return list(_get_cached_in_memory_cars())
    logger.warning("eBay not configured and demo disabled; inventory empty")
    return []


def iter_cars(db: Session, *, inventory_query: str | None = None):
    return _cars_for_inventory(db, inventory_query=inventory_query)


def _latest_aspects_json(car: Car) -> Any:
    snaps = car.aspect_snapshots
    if not snaps:
        return None
    return max(
        snaps, key=lambda s: (s.captured_at.timestamp() if s.captured_at else 0.0, s.id)
    ).aspects_json


def _body_style_for_car(car: Car) -> Optional[str]:
    return extract_body_style_from_aspects_json(_latest_aspects_json(car))


def _drive_type_for_car(car: Car) -> Optional[str]:
    return extract_drive_type_from_aspects_json(_latest_aspects_json(car))


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
    if not q or not isinstance(q, str):
        return []
    qn = unicodedata.normalize("NFKC", q).strip().lower()
    if not qn:
        return []
    return [t for t in re.split(r"\s+", qn) if t]


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
    if not tokens:
        return True
    haystack = " ".join(
        [
            brand.lower(),
            model.lower(),
            str(year),
            city.lower(),
            region.lower(),
            country.lower(),
            listing_format.lower(),
            condition.lower(),
            (body_style or "").lower(),
            vehicle_title.lower(),
            (drive_type or "").lower(),
            description_summary[:400].lower(),
        ]
    )
    full_phrase = " ".join(tokens)
    if full_phrase in haystack:
        return True
    if any(t in haystack for t in tokens):
        return True
    brand_model = f"{brand} {model}".lower()
    if difflib.SequenceMatcher(None, brand_model, full_phrase).ratio() >= 0.55:
        return True
    if difflib.SequenceMatcher(None, haystack[:240], full_phrase).ratio() >= 0.48:
        return True
    return False


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


def sort_car_dicts_inplace(
    results: list[dict[str, Any]], sort_by: Optional[str], sort_order: Optional[str]
) -> None:
    if not sort_by:
        return
    reverse_sort = (sort_order or "desc") == "desc"
    if sort_by == "net_profit":
        results.sort(key=lambda x: x["net_profit"], reverse=reverse_sort)
    elif sort_by == "price":
        results.sort(key=lambda x: x["price"], reverse=reverse_sort)
    elif sort_by == "roi":
        results.sort(key=lambda x: x["roi"], reverse=reverse_sort)


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
) -> list:
    q_toks = _q_tokens(q)
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
    for car in cars:
        if makes_l:
            if car.brand.strip().lower() not in makes_l:
                continue
        elif make and make.lower() not in car.brand.lower():
            continue
        if model and model.lower() not in car.model.lower():
            continue
        if min_year and car.year < min_year:
            continue
        if max_year and car.year > max_year:
            continue

        mi = _effective_mileage(car)
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

        if max_price is not None and car.price > max_price:
            continue
        if min_price is not None and car.price < min_price:
            continue

        loc = car.location
        if countries_l:
            cc = _normalize_country_key((loc.country or "") if loc else "")
            allowed_countries = {_normalize_country_key(c) for c in countries_l}
            if cc not in allowed_countries:
                continue
        if regions_l:
            rr = (loc.region or "").strip().lower() if loc else ""
            if rr not in regions_l:
                continue
        if cities_l:
            ci = (loc.city or "").strip().lower() if loc else ""
            if ci not in cities_l:
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

        body_style = _body_style_for_car(car)
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

        analysis = calculate_flip_score(car.price, car.resale_value, car.repair_cost or 0)
        if min_profit is not None and analysis["net_profit"] < min_profit:
            continue
        if min_roi is not None and analysis["roi"] < min_roi:
            continue

        mileage = mi
        drive_type = _drive_type_for_car(car)

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

        city_s = (loc.city or "") if loc else ""
        region_s = (loc.region or "") if loc else ""
        country_s = (loc.country or "") if loc else ""

        lf_norm = (
            _normalize_listing_format(car.listing_format)
            or (car.listing_format or "").strip().lower()
        )
        if not _car_matches_q_soft(
            brand=car.brand,
            model=car.model,
            year=car.year,
            city=city_s,
            region=region_s,
            country=country_s,
            listing_format=lf_norm,
            condition=car.condition or "",
            body_style=body_style,
            vehicle_title=vt,
            drive_type=drive_type,
            description_summary=car.description_summary or "",
            tokens=q_toks,
        ):
            continue

        image_urls = _image_urls_for_car(car)
        src = (car.source or "manual").strip().lower()
        ebay_sandbox = get_ebay_client().sandbox if src == "ebay" else False
        listing_url_out = resolve_listing_url(
            getattr(car, "external_listing_id", None),
            getattr(car, "listing_url", None),
            sandbox=ebay_sandbox,
        )
        results.append(
            {
                "id": car.id,
                "brand": car.brand,
                "model": car.model,
                "year": car.year,
                "price": car.price,
                "repair_cost": car.repair_cost,
                "resale_value": car.resale_value,
                "mileage": mileage,
                "condition": car.condition,
                "vehicle_title": vt or None,
                "image_url": image_urls[0] if image_urls else car.image_url,
                "images": image_urls,
                "body_style": body_style,
                "drive_type": drive_type,
                "source": car.source or "manual",
                "external_listing_id": car.external_listing_id,
                "listing_url": listing_url_out,
                "listing_ends_at": listing_ends_at,
                "bid_count": car.bid_count,
                "listing_format": _normalize_listing_format(car.listing_format)
                or car.listing_format,
                "description_summary": car.description_summary,
                "seller_username": seller_username,
                "location": location_out,
                "delivery": delivery,
                **analysis,
            }
        )
    return results


def compute_inventory_meta(db: Session) -> dict[str, Any]:
    """Aggregate bounds and location hierarchy for filter UI (no auth logic here)."""
    inventory_source = "empty"
    if _stored_cars_exist(db):
        inventory_source = "database"
        cars = _cars_for_inventory(db, inventory_query=None)
    elif get_ebay_client().is_configured():
        inventory_source = "ebay"
        cars = fetch_ebay_inventory_views(None)
        if not cars and in_memory_demo_enabled():
            inventory_source = "demo"
            cars = list(_get_cached_in_memory_cars())
    elif in_memory_demo_enabled():
        inventory_source = "demo"
        cars = list(_get_cached_in_memory_cars())
    else:
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
        }

    year_lo, year_hi = _year_slider_bounds()
    if inventory_source == "ebay":
        (price_lo, price_hi), (mi_lo, mi_hi) = _demo_catalog_slider_bounds()
    else:
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

        loc = car.location
        if not loc:
            continue
        co = (loc.country or "").strip()
        reg = (loc.region or "").strip()
        city = (loc.city or "").strip()
        if co:
            countries.add(co)
        if co and reg:
            regions_by_country.setdefault(co, set()).add(reg)
        if reg and city:
            rkey = f"{co}|{reg}"
            cities_by_region.setdefault(rkey, set()).add(city)
        pair = latlng_pair(loc.latitude, loc.longitude)
        if pair and co and reg and city:
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
    }
