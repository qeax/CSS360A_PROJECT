"""Parse vehicle aspect snapshots (e.g. eBay localizedAspects) for UI filters."""

from __future__ import annotations

import re
from typing import Any, Optional

# Localized names seen in eBay US locale; extend as needed.
_BODY_STYLE_ASPECT_NAMES = frozenset(
    {
        "body type",
        "body style",
        "vehicle type",
        "type",
    }
)


def _normalize_aspect_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


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


def extract_body_style_from_aspects_json(aspects_json: Any) -> Optional[str]:
    """
    Return a display string for body style / vehicle type from snapshot JSON.

    Supports:
    - list of {localizedAspectName, localizedAspectValues} (eBay)
    - list of {name, value}
    - dict with key ``localizedAspects`` wrapping such a list
    """
    if not aspects_json:
        return None

    items: Any = aspects_json
    if isinstance(aspects_json, dict):
        items = (
            aspects_json.get("localizedAspects")
            or aspects_json.get("aspects")
            or aspects_json.get("items")
        )

    if not isinstance(items, list):
        return None

    for entry in items:
        if not isinstance(entry, dict):
            continue
        raw_name = (
            entry.get("localizedAspectName")
            or entry.get("name")
            or entry.get("aspectName")
            or entry.get("localizedLabel")
        )
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name_key = _normalize_aspect_name(raw_name)
        if name_key not in _BODY_STYLE_ASPECT_NAMES and not any(
            hint in name_key for hint in ("body", "vehicle type", "type of vehicle")
        ):
            continue
        vals = entry.get("localizedAspectValues") or entry.get("values") or entry.get("value")
        if isinstance(vals, str):
            picked = vals.strip() or None
        else:
            picked = _first_value(vals)
        if picked:
            return picked
    return None


_DRIVE_TYPE_ASPECT_NAMES = frozenset({"drive type", "drivetrain"})


def extract_drive_type_from_aspects_json(aspects_json: Any) -> Optional[str]:
    """Return drive type string (e.g. FWD, AWD) from snapshot JSON."""
    if not aspects_json:
        return None

    items: Any = aspects_json
    if isinstance(aspects_json, dict):
        items = (
            aspects_json.get("localizedAspects")
            or aspects_json.get("aspects")
            or aspects_json.get("items")
        )

    if not isinstance(items, list):
        return None

    for entry in items:
        if not isinstance(entry, dict):
            continue
        raw_name = (
            entry.get("localizedAspectName")
            or entry.get("name")
            or entry.get("aspectName")
            or entry.get("localizedLabel")
        )
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        name_key = _normalize_aspect_name(raw_name)
        if name_key not in _DRIVE_TYPE_ASPECT_NAMES and "drive" not in name_key:
            continue
        vals = entry.get("localizedAspectValues") or entry.get("values") or entry.get("value")
        if isinstance(vals, str):
            picked = vals.strip() or None
        else:
            picked = _first_value(vals)
        if picked:
            return picked
    return None
