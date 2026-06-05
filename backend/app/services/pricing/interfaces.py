from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.services.pricing.types import PricingInput, ResaleEstimate


class ResalePricingProvider(Protocol):
    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate | None: ...
