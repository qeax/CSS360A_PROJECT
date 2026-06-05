"""Geocode listing locations via OpenStreetMap Nominatim (cached on car_locations)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.models.car_satellite import CarLocation

logger = logging.getLogger(__name__)

_last_nominatim_at: float = 0.0
_MIN_INTERVAL_SEC = 1.05


def _nominatim_user_agent() -> str:
    return (os.getenv("NOMINATIM_USER_AGENT") or "css360-car-flip/1.0").strip()


def _rate_limit() -> None:
    global _last_nominatim_at
    elapsed = time.monotonic() - _last_nominatim_at
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_nominatim_at = time.monotonic()


def geocode_query(
    city: str | None, region: str | None, country: str | None
) -> dict[str, Any] | None:
    """Resolve city/region/country via Nominatim; return lat/lng and optional boundary."""
    parts = [p.strip() for p in (city, region, country) if p and str(p).strip()]
    if not parts:
        return None
    q = ", ".join(parts)
    _rate_limit()
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "json",
                "limit": 1,
                "polygon_geojson": 1,
            },
            headers={"User-Agent": _nominatim_user_agent()},
            timeout=8,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        lat = float(row["lat"])
        lng = float(row["lon"])
        out: dict[str, Any] = {
            "latitude": lat,
            "longitude": lng,
            "boundingbox": row.get("boundingbox"),
        }
        geojson = row.get("geojson")
        if geojson:
            out["boundary_geojson"] = geojson
        return out
    except Exception as e:
        logger.info("Nominatim geocode failed for %r: %s", q, e)
        return None


def ensure_car_location_coords(
    db: Session, car_id: int, loc: CarLocation | None
) -> dict[str, Any] | None:
    """Return location dict with lat/lng and boundary, geocoding and persisting when missing."""
    if loc is None:
        return None
    out: dict[str, Any] = {
        "country": loc.country,
        "region": loc.region,
        "city": loc.city,
        "postal_code_masked": loc.postal_code_masked,
    }
    lat = loc.latitude
    lng = loc.longitude
    boundary = getattr(loc, "boundary_geojson", None)

    if lat is not None and lng is not None:
        out["latitude"] = float(lat)
        out["longitude"] = float(lng)
        if boundary:
            out["boundary_geojson"] = boundary
            return out
        result = geocode_query(loc.city, loc.region, loc.country)
        if result and result.get("boundary_geojson"):
            loc.boundary_geojson = result["boundary_geojson"]
            out["boundary_geojson"] = result["boundary_geojson"]
            if result.get("boundingbox"):
                out["boundingbox"] = result["boundingbox"]
            db.flush()
        return out

    result = geocode_query(loc.city, loc.region, loc.country)
    if result is None:
        return out

    lat = result["latitude"]
    lng = result["longitude"]
    loc.latitude = lat
    loc.longitude = lng
    if result.get("boundary_geojson"):
        loc.boundary_geojson = result["boundary_geojson"]
        out["boundary_geojson"] = result["boundary_geojson"]
    if result.get("boundingbox"):
        out["boundingbox"] = result["boundingbox"]
    db.flush()
    out["latitude"] = lat
    out["longitude"] = lng
    return out
