"""Drop obvious non-vehicle listings that slip through keyword search."""

from __future__ import annotations

import os
import re
from typing import Any

_YEAR_IN_TITLE_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")

_NON_VEHICLE_MARKERS = frozenset(
    {
        "balenciaga",
        "gucci",
        "prada",
        "louis vuitton",
        "chanel",
        "nike",
        "adidas",
        "handbag",
        "purse",
        "wallet",
        "sneaker",
        "shirt",
        "dress",
        "jacket",
        "unused]",
        "new with tags",
        "fashion",
    }
)


def _strict_mode() -> bool:
    """
    Strict filter requires explicit vehicle signals (mileage / brand+model / hints).

    Default off in sandbox (data is too sparse), on in production unless a vehicle
    category filter is active (then trust eBay category + title blacklist only).
    Override with EBAY_STRICT_VEHICLE_FILTER=true/false.
    """
    raw = os.getenv("EBAY_STRICT_VEHICLE_FILTER", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    if _trust_marketplace_category():
        return False
    sandbox = os.getenv("EBAY_SANDBOX", "true").strip().lower() == "true"
    return not sandbox


def _trust_marketplace_category() -> bool:
    """Production search is scoped to EBAY_CATEGORY_IDS (default Cars & Trucks 6001)."""
    cat = (os.getenv("EBAY_CATEGORY_IDS") or "6001").strip()
    if not cat:
        return False
    sandbox = os.getenv("EBAY_SANDBOX", "true").strip().lower() == "true"
    if sandbox:
        force = os.getenv("EBAY_FORCE_CATEGORY_IDS", "").strip().lower()
        if force not in ("1", "true", "yes", "on"):
            return False
    return True


def is_likely_vehicle_listing(item: dict[str, Any]) -> bool:
    """Heuristic guard when marketplace category filter is ignored (e.g. sandbox)."""
    title = (item.get("title") or "").lower()
    if any(marker in title for marker in _NON_VEHICLE_MARKERS):
        return False

    if _trust_marketplace_category():
        return True

    brand = (item.get("brand") or "").strip().lower()
    if brand in _NON_VEHICLE_MARKERS:
        return False

    mileage = item.get("mileage")
    if mileage is not None:
        try:
            mi = int(mileage)
            if 500 <= mi <= 500_000:
                return True
        except (TypeError, ValueError):
            pass

    try:
        price = float(item.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0

    if price >= 1000:
        if _YEAR_IN_TITLE_RE.search(title):
            return True
        if _has_vehicle_title_hint(title):
            return True
        if brand and brand not in ("ebay", "unknown", "listing") and item.get("model"):
            return True

    if not _strict_mode():
        return True

    return False


def _has_vehicle_title_hint(title: str) -> bool:
    if _YEAR_IN_TITLE_RE.search(title):
        return True
    hints = (
        "car",
        "truck",
        "suv",
        "sedan",
        "coupe",
        "van",
        "pickup",
        "camry",
        "civic",
        "f-150",
        "motor",
        "vehicle",
        "automobile",
    )
    return any(h in title for h in hints)
