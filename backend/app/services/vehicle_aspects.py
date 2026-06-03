"""Extract normalized vehicle fields from eBay localizedAspects snapshots."""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.body_style import (
    extract_body_style_from_aspects_json,
    extract_drive_type_from_aspects_json,
)

_ASPECT_NAME_NORMALIZE = re.compile(r"\s+")


def _normalize_aspect_name(name: str) -> str:
    return _ASPECT_NAME_NORMALIZE.sub(" ", name.strip().lower())


def _first_value(values: Any) -> Optional[str]:
    if values is None:
        return None
    if isinstance(values, str) and values.strip():
        return values.strip()
    if isinstance(values, list) and values:
        v0 = values[0]
        if isinstance(v0, str) and v0.strip():
            return v0.strip()
    return None


def _aspect_entries(aspects_json: Any) -> list[dict[str, Any]]:
    if not aspects_json:
        return []
    items: Any = aspects_json
    if isinstance(aspects_json, dict):
        items = (
            aspects_json.get("localizedAspects")
            or aspects_json.get("aspects")
            or aspects_json.get("items")
        )
    if not isinstance(items, list):
        return []
    return [e for e in items if isinstance(e, dict)]


def extract_aspect_value(aspects_json: Any, aspect_names: tuple[str, ...]) -> Optional[str]:
    """Return first matching aspect value (case-insensitive name match)."""
    if not aspect_names:
        return None
    wanted = {_normalize_aspect_name(n) for n in aspect_names}
    for entry in _aspect_entries(aspects_json):
        raw_name = (
            entry.get("localizedAspectName")
            or entry.get("name")
            or entry.get("aspectName")
            or entry.get("localizedLabel")
        )
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        if _normalize_aspect_name(raw_name) not in wanted:
            continue
        vals = entry.get("localizedAspectValues") or entry.get("values") or entry.get("value")
        if isinstance(vals, str):
            picked = vals.strip() or None
        else:
            picked = _first_value(vals)
        if picked:
            return picked
    return None


def extract_vin_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(
        aspects_json,
        ("vin", "vin (vehicle identification number)", "vehicle identification number"),
    )


def extract_transmission_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("transmission",))


def extract_trim_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("trim",))


def extract_engine_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("engine",))


def extract_fuel_type_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("fuel type",))


def extract_fuel_city_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("fuel city",))


def extract_fuel_highway_from_aspects_json(aspects_json: Any) -> Optional[str]:
    return extract_aspect_value(aspects_json, ("fuel highway",))


def extended_vehicle_fields_from_aspects_json(aspects_json: Any) -> dict[str, Optional[str]]:
    """All aspect-derived display fields for API/UI."""
    return {
        "body_style": extract_body_style_from_aspects_json(aspects_json),
        "drive_type": extract_drive_type_from_aspects_json(aspects_json),
        "vin": extract_vin_from_aspects_json(aspects_json),
        "transmission": extract_transmission_from_aspects_json(aspects_json),
        "trim": extract_trim_from_aspects_json(aspects_json),
        "engine": extract_engine_from_aspects_json(aspects_json),
        "fuel_type": extract_fuel_type_from_aspects_json(aspects_json),
        "fuel_city": extract_fuel_city_from_aspects_json(aspects_json),
        "fuel_highway": extract_fuel_highway_from_aspects_json(aspects_json),
    }
