"""Drop obvious non-vehicle listings that slip through keyword search."""

from __future__ import annotations

from typing import Any

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


def is_likely_vehicle_listing(item: dict[str, Any]) -> bool:
    """Heuristic guard when marketplace category filter is ignored (e.g. sandbox)."""
    title = (item.get("title") or "").lower()
    if any(marker in title for marker in _NON_VEHICLE_MARKERS):
        return False

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
    if price >= 1_000 and _has_vehicle_title_hint(title):
        return True

    if brand and brand not in ("ebay", "unknown", "listing") and item.get("model"):
        return True

    return False


def _has_vehicle_title_hint(title: str) -> bool:
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
