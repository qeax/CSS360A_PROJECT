"""Flip profit / ROI helpers and listing-based resale estimates."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def calculate_flip_score(
    purchase_price: float, resale_value: float, repair_cost: float = 0
) -> dict:
    net_profit = resale_value - purchase_price - repair_cost
    roi = (net_profit / purchase_price) * 100 if purchase_price > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 1),
        "is_profitable": net_profit > 0,
    }


def estimate_flip_from_listing(
    price: float,
    *,
    year: Optional[int] = None,
    mileage: Optional[int] = None,
    condition: Optional[str] = None,
    vehicle_title: Optional[str] = None,
) -> tuple[float, float]:
    """
    Heuristic repair and resale for eBay rows (no external valuation API).

    Uses age, mileage vs expected, condition, and title status. Intended for
    **relative ranking** of listings (ROI est.), not verified market value.
    """
    if price <= 0:
        return 0.0, 0.0

    current_year = datetime.now().year
    model_year = year if year and 1980 <= year <= current_year + 1 else current_year - 8
    age_years = max(0, min(30, current_year - model_year))

    expected_miles = age_years * 12_000 if age_years > 0 else 45_000
    odometer = mileage if mileage is not None and mileage > 0 else expected_miles
    excess_miles = max(0, odometer - expected_miles)
    mileage_penalty = min(0.22, excess_miles / 180_000)

    age_resale_factor = max(0.78, 1.0 - age_years * 0.011)

    cond = (condition or "used").strip().lower()
    condition_factor = 1.04 if cond == "new" else 0.98 if "pre" in cond else 1.0

    title = (vehicle_title or "not specified").strip().lower()
    if any(k in title for k in ("salvage", "flood", "rebuilt", "lemon", "manufacturer buyback")):
        title_factor = 0.80
    elif "clean" in title:
        title_factor = 1.04
    elif "finance" in title or "encumbered" in title:
        title_factor = 0.94
    else:
        title_factor = 0.97

    resale_multiplier = 1.14 * age_resale_factor * condition_factor * title_factor
    resale_multiplier *= 1.0 - mileage_penalty
    resale_multiplier = max(0.88, min(1.32, resale_multiplier))

    repair_rate = 0.05
    repair_rate += min(0.09, age_years * 0.004)
    repair_rate += min(0.08, excess_miles / 160_000)
    if title_factor <= 0.85:
        repair_rate += 0.06
    elif title_factor < 0.95:
        repair_rate += 0.02

    repair_cost = round(price * repair_rate, 2)
    resale_value = round(price * resale_multiplier, 2)
    return repair_cost, resale_value
