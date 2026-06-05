from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.pricing.providers import (
    ExternalPricingProvider,
    HeuristicProvider,
    InternalCompsProvider,
    SegmentBaselineProvider,
)
from app.services.pricing.types import PricingInput, ResaleEstimate


@dataclass
class ResalePricingService:
    comp_threshold: float = 0.45
    segment_threshold: float = 0.35

    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate:
        providers = (
            InternalCompsProvider(),
            SegmentBaselineProvider(),
            HeuristicProvider(),
            ExternalPricingProvider(),
        )
        fallback: ResaleEstimate | None = None
        for provider in providers:
            estimate = provider.estimate(listing, db=db)
            if estimate is None:
                continue
            if estimate.method.startswith("comps") and estimate.confidence >= self.comp_threshold:
                return estimate
            if estimate.method == "segment" and estimate.confidence >= self.segment_threshold:
                return estimate
            if estimate.method == "heuristic":
                fallback = estimate
            else:
                fallback = fallback or estimate
        if fallback is not None:
            return fallback
        return ResaleEstimate(
            resale_value=listing.purchase_price,
            confidence=0.1,
            method="heuristic",
            comp_count=0,
            adjustments={},
        )
