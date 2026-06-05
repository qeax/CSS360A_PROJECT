from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.flip import estimate_flip_economics
from app.services.pricing.comparable_finder import find_comparables, weighted_trimmed_median
from app.services.pricing.interfaces import ResalePricingProvider
from app.services.pricing.segment_baseline import SegmentBaseline, get_segment_baseline
from app.services.pricing.types import ComparableCandidate, PricingInput, ResaleEstimate


def _apply_listing_haircut(price: float, listing_format: str | None) -> float:
    fmt = (listing_format or "").upper()
    if "AUCTION" in fmt:
        return price * 0.93
    return price * 0.96


def _title_adjustment(vehicle_title: str | None, base_price: float) -> float:
    t = (vehicle_title or "").strip().lower()
    if not t:
        return 0.0
    if any(x in t for x in ("salvage", "rebuilt", "flood", "junk", "parts")):
        return -base_price * 0.18
    if "clean" in t or "clear" in t:
        return base_price * 0.03
    return 0.0


def _condition_adjustment(condition: str | None, base_price: float) -> float:
    c = (condition or "").strip().lower()
    if not c:
        return 0.0
    if "new" in c:
        return base_price * 0.04
    if "cert" in c:
        return base_price * 0.025
    if any(x in c for x in ("salvage", "rebuilt", "parts")):
        return -base_price * 0.15
    return 0.0


def _mileage_adjustment(target_mileage: int | None, baseline_mileage: int | None) -> float:
    if target_mileage is None or baseline_mileage is None:
        return 0.0
    delta = int(target_mileage) - int(baseline_mileage)
    return -(delta / 1000.0) * 55.0


def _trim_engine_adjustment(
    target: PricingInput, comp: ComparableCandidate | None, base_price: float
) -> float:
    if comp is None:
        return 0.0
    adjust = 0.0
    if target.trim and comp.trim and target.trim.strip().lower() != comp.trim.strip().lower():
        adjust -= base_price * 0.04
    if (
        target.engine
        and comp.engine
        and target.engine.strip().lower() != comp.engine.strip().lower()
    ):
        adjust -= base_price * 0.03
    return adjust


def _confidence(comp_count: int, avg_similarity: float, recency_score: float) -> float:
    raw = (
        0.15
        + 0.45 * min(1.0, comp_count / 8.0)
        + 0.25 * max(0.0, min(1.0, avg_similarity))
        + 0.15 * max(0.0, min(1.0, recency_score))
    )
    return max(0.0, min(1.0, raw))


def _recency_score_from_candidates(candidates: list[ComparableCandidate]) -> float:
    if not candidates:
        return 0.0
    now = datetime.now(timezone.utc)
    vals: list[float] = []
    for c in candidates:
        if c.synced_at is None:
            vals.append(0.3)
            continue
        dt = c.synced_at if c.synced_at.tzinfo else c.synced_at.replace(tzinfo=timezone.utc)
        days = max(0.0, (now - dt).total_seconds() / 86400.0)
        vals.append(math.exp(-days / 45.0))
    return sum(vals) / len(vals)


class InternalCompsProvider(ResalePricingProvider):
    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate | None:
        comps = find_comparables(db, listing, limit=20)
        if len(comps) < 2:
            return None
        tight = [c for c in comps if c.similarity >= 0.62]
        chosen = tight if len(tight) >= 2 else comps[:8]
        base = weighted_trimmed_median([(c.price, c.similarity) for c in chosen], trim_ratio=0.1)
        if base is None:
            return None
        baseline_mileage = None
        known_miles = [c.mileage for c in chosen if c.mileage is not None]
        if known_miles:
            baseline_mileage = int(sorted(known_miles)[len(known_miles) // 2])
        top_comp = chosen[0] if chosen else None
        adjustments = {
            "mileage": _mileage_adjustment(listing.mileage, baseline_mileage),
            "condition": _condition_adjustment(listing.condition, base),
            "title": _title_adjustment(listing.vehicle_title, base),
            "trim_engine": _trim_engine_adjustment(listing, top_comp, base),
            "format_haircut": _apply_listing_haircut(base, listing.listing_format) - base,
            "fees": -(base * 0.022),
        }
        resale = base + sum(adjustments.values())
        resale = max(listing.purchase_price * 0.72, resale)
        avg_sim = sum(c.similarity for c in chosen) / len(chosen)
        conf = _confidence(len(chosen), avg_sim, _recency_score_from_candidates(chosen))
        method = "comps_tight" if len(tight) >= 5 else "comps_shrunk"
        return ResaleEstimate(
            resale_value=round(resale, 2),
            confidence=conf,
            method=method,
            comp_count=len(chosen),
            adjustments={k: round(v, 2) for k, v in adjustments.items()},
            debug={"comp_ids": [c.car_id for c in chosen[:10]]},
        )


class SegmentBaselineProvider(ResalePricingProvider):
    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate | None:
        baseline: SegmentBaseline | None = get_segment_baseline(db, listing)
        if baseline is None or baseline.sample_count < 2:
            return None
        base = baseline.median_price
        adjustments = {
            "mileage": _mileage_adjustment(listing.mileage, baseline.median_mileage),
            "condition": _condition_adjustment(listing.condition, base),
            "title": _title_adjustment(listing.vehicle_title, base),
            "format_haircut": _apply_listing_haircut(base, listing.listing_format) - base,
            "fees": -(base * 0.022),
        }
        resale = base + sum(adjustments.values())
        resale = max(listing.purchase_price * 0.7, resale)
        conf = max(0.35, min(0.72, 0.32 + min(0.4, baseline.sample_count / 40.0)))
        return ResaleEstimate(
            resale_value=round(resale, 2),
            confidence=conf,
            method="segment",
            comp_count=baseline.sample_count,
            segment_key=baseline.segment_key,
            adjustments={k: round(v, 2) for k, v in adjustments.items()},
        )


class HeuristicProvider(ResalePricingProvider):
    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate | None:
        del db
        econ = estimate_flip_economics(
            listing.purchase_price,
            year=listing.year,
            mileage=listing.mileage,
            condition=listing.condition,
            vehicle_title=listing.vehicle_title,
            listing_format=listing.listing_format,
            listing_id=listing.external_listing_id,
            title_text=listing.title_text,
        )
        return ResaleEstimate(
            resale_value=float(econ["resale_value"]),
            confidence=0.28,
            method="heuristic",
            comp_count=0,
            adjustments={},
        )


class ExternalPricingProvider(ResalePricingProvider):
    def estimate(self, listing: PricingInput, *, db: Session) -> ResaleEstimate | None:
        del listing, db
        return None
