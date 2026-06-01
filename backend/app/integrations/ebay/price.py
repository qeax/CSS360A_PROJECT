"""Parse listing price from normalized eBay item dicts."""

from __future__ import annotations

from typing import Any


def parse_listing_price(value: Any) -> tuple[float, bool]:
    """
    Return (price, price_known).

    When eBay omits price, returns (0.0, False) — never fabricate $1 placeholders.
    """
    if value is None:
        return 0.0, False
    try:
        price = float(value)
    except (TypeError, ValueError):
        return 0.0, False
    if price <= 0:
        return 0.0, False
    return price, True
