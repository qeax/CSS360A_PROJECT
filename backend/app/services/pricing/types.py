from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PricingInput:
    external_listing_id: str | None
    source: str
    purchase_price: float
    brand: str
    model: str
    year: int | None
    mileage: int | None
    condition: str | None
    vehicle_title: str | None
    listing_format: str | None
    region: str | None
    synced_at: datetime | None
    trim: str | None = None
    engine: str | None = None
    body_style: str | None = None
    title_text: str | None = None
    car_id: int | None = None
    raw_listing_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class ComparableCandidate:
    car_id: int
    price: float
    brand: str
    model: str
    year: int | None
    mileage: int | None
    condition: str | None
    vehicle_title: str | None
    listing_format: str | None
    region: str | None
    synced_at: datetime | None
    trim: str | None
    engine: str | None
    body_style: str | None
    source: str
    similarity: float


@dataclass
class ResaleEstimate:
    resale_value: float
    confidence: float
    method: str
    comp_count: int = 0
    segment_key: str | None = None
    adjustments: dict[str, float] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)
