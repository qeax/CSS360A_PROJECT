"""Flip economics: repair/resale estimates and profit metrics."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Repair estimate is driven mainly by these three (weights re-normalize when unknown).
_REPAIR_WEIGHT_YEAR = 0.34
_REPAIR_WEIGHT_MILEAGE = 0.40
_REPAIR_WEIGHT_CONDITION = 0.26
_REPAIR_WEIGHT_TITLE_RISKY = 0.10  # only when title is known and risky

_REPAIR_PCT_FLOOR = 0.025
_REPAIR_PCT_SPAN = 0.36  # floor + span * score ≈ 2.5% … 38.5%

# Auction bid reliability thresholds (see resolve_effective_purchase_price).
_AUCTION_LOW_BID_THRESHOLD = 1000.0
_AUCTION_REFERENCE_RATIO = 0.20
_AUCTION_EARLY_BID_MAX = 5000.0

_STANDARD_BASELINES: dict[int, float] = {
    0: 26500,  # 0-3 years
    3: 19000,  # 4-6 years
    6: 12500,  # 7-10 years
    10: 7200,  # 11-15 years
    15: 3800,  # 16+ years
}
_COLLECTIBLE_BASELINES: dict[int, float] = {
    0: 45000,
    3: 38000,
    6: 32000,
    10: 28000,
    15: 22000,
}


@dataclass(frozen=True)
class _VehicleSignals:
    age: int | None
    age_known: bool
    mileage: int | None
    mileage_known: bool
    condition: str | None  # normalized: new | certified | used | salvage | None
    condition_known: bool
    title: str  # clean | risky | unknown
    title_known: bool


def _is_collectible_vehicle(title_text: str | None, year: int | None) -> bool:
    """
    Detect classic, rare, or enthusiast vehicles that don't follow normal depreciation.
    Analyzes title text and year to identify potential high-value collectibles.
    """
    text = (title_text or "").lower()

    # 1. Classic American Muscle (1960s-1970s)
    muscle_cars = [
        "mustang",
        "camaro",
        "corvette",
        "charger",
        "challenger",
        "chevelle",
        "firebird",
        "gto",
        "barracuda",
        "nova ss",
        "impala",
        "barracuda",
    ]
    if any(m in text for m in muscle_cars):
        if year and 1960 <= year <= 1979:
            return True
        if year and 1980 <= year <= 1995:  # Later muscle still holds value
            return True

    # 2. Japanese Sports Cars (JDM Legends)
    jdm_legends = [
        "supra",
        "skyline",
        "silvia",
        "rx-7",
        "nsx",
        "300zx",
        "celica",
        "mr2",
        "rx7",
        "s13",
        "s14",
    ]
    if any(m in text for m in jdm_legends):
        if year and 1985 <= year <= 2005:
            return True

    # 3. European Exotics/Sports
    exotic_brands = [
        "porsche",
        "ferrari",
        "lamborghini",
        "mclaren",
        "aston martin",
        "maserati",
        "lotus",
    ]
    if any(b in text for b in exotic_brands):
        return True

    # 4. German Performance (BMW M, Mercedes AMG, Audi RS)
    if any(x in text for x in ["m3", "m5", "m4", "amg", "c63", "e63", "rs4", "rs6", "rs7"]):
        return True

    # 5. Limited Editions/Special Trims
    special_trims = ["gt3", "gt500", "z06", "type r", "evo", "sti", "r34", "r32", "shelby"]
    if any(t in text for t in special_trims):
        return True

    return False


def _is_auction_format(listing_format: str | None) -> bool:
    return "AUCTION" in (listing_format or "").upper()


def _vehicle_age_from_year(year: int | None, title_text: str | None = None) -> int:
    model_year = _coerce_year(year) or _year_from_text(title_text)
    if model_year is None:
        return 7
    return max(0, datetime.now().year - model_year)


def _market_baseline_price(year: int | None, title_text: str | None) -> float:
    """Age-based private-party market baseline for unreliable auction bids."""
    model_year = _coerce_year(year) or _year_from_text(title_text)
    age = _vehicle_age_from_year(model_year, title_text)
    is_collectible = _is_collectible_vehicle(title_text, model_year)
    baselines = _COLLECTIBLE_BASELINES if is_collectible else _STANDARD_BASELINES
    baseline = 2500.0
    for age_threshold in sorted(baselines.keys()):
        if age <= age_threshold + 3:
            baseline = baselines[age_threshold]
            break
    return float(baseline)


def is_unreliable_auction_bid(
    price: float,
    listing_format: str | None,
    *,
    bid_count: int | None = None,
    reference_value: float | None = None,
) -> bool:
    """True when current auction bid is too low to use for ROI / repair math."""
    if not _is_auction_format(listing_format):
        return False
    if price < _AUCTION_LOW_BID_THRESHOLD:
        return True
    if (
        reference_value is not None
        and reference_value > 0
        and price < reference_value * _AUCTION_REFERENCE_RATIO
    ):
        return True
    if bid_count is not None and bid_count <= 1 and price < _AUCTION_EARLY_BID_MAX:
        return True
    return False


def resolve_effective_purchase_price(
    price: float,
    *,
    listing_format: str | None = None,
    bid_count: int | None = None,
    year: int | None = None,
    title_text: str | None = None,
    reference_value: float | None = None,
    segment_median: float | None = None,
) -> tuple[float, bool]:
    """
    Return (effective_price, is_estimated).

    For live auctions with unrealistically low bids, substitutes a market-based
    acquisition estimate instead of the current bid.
    """
    price = max(1.0, float(price))
    ref = segment_median if segment_median is not None else reference_value
    if not is_unreliable_auction_bid(
        price, listing_format, bid_count=bid_count, reference_value=ref
    ):
        return price, False

    if segment_median is not None and segment_median > 0:
        effective = segment_median
    else:
        baseline = _market_baseline_price(year, title_text)
        if baseline > 0:
            effective = baseline
        elif reference_value is not None and reference_value > 0:
            effective = reference_value * 0.75
        else:
            effective = price
    return round(max(effective, price), 2), True


def calculate_flip_score(
    purchase_price: float, resale_value: float, repair_cost: float = 0
) -> dict[str, Any]:
    net_profit = resale_value - purchase_price - repair_cost
    roi = (net_profit / purchase_price) * 100 if purchase_price > 0 else 0
    return {
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 1),
        "is_profitable": net_profit > 0,
    }


def calculate_flip_score_for_listing(
    price: float,
    resale_value: float,
    repair_cost: float = 0,
    *,
    listing_format: str | None = None,
    bid_count: int | None = None,
    year: int | None = None,
    title_text: str | None = None,
    segment_median: float | None = None,
) -> dict[str, Any]:
    """ROI metrics using effective purchase price when auction bid is unreliable."""
    effective, is_preliminary = resolve_effective_purchase_price(
        price,
        listing_format=listing_format,
        bid_count=bid_count,
        year=year,
        title_text=title_text,
        reference_value=resale_value,
        segment_median=segment_median,
    )
    score = calculate_flip_score(effective, resale_value, repair_cost)
    score["purchase_price_effective"] = effective
    score["roi_is_preliminary"] = is_preliminary
    return score


def flip_metrics_unknown() -> dict[str, Any]:
    """Return flip metrics when purchase price is unknown."""
    return {
        "net_profit": None,
        "roi": None,
        "is_profitable": False,
    }


def _stable_jitter(key: str | None, amplitude: float) -> float:
    if not key:
        return 0.0
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    unit = int(digest[:8], 16) / 0xFFFFFFFF
    return (unit - 0.5) * 2.0 * amplitude


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _coerce_year(year: int | None) -> int | None:
    if year is None:
        return None
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    current = datetime.now().year
    if y < 1980 or y > current + 1:
        return None
    return y


def _year_from_text(text: str | None) -> int | None:
    if not text:
        return None
    m = _YEAR_RE.search(text)
    if not m:
        return None
    return _coerce_year(int(m.group(1)))


def _coerce_mileage(mileage: int | None) -> int | None:
    if mileage is None:
        return None
    try:
        mi = int(mileage)
    except (TypeError, ValueError):
        return None
    if mi < 0 or mi > 1_500_000:
        return None
    return mi


def _is_blank(value: str | None) -> bool:
    return not (value or "").strip()


def _norm_condition(condition: str | None) -> str | None:
    """Return normalized condition, or None when listing did not specify it."""
    if _is_blank(condition):
        return None
    c = condition.strip().lower()
    if c in (
        "not specified",
        "unspecified",
        "unknown",
        "n/a",
        "na",
        "—",
        "-",
        "other",
    ):
        return None
    if "new" in c and "used" not in c:
        return "new"
    if "cert" in c or "cpo" in c:
        return "certified"
    if any(x in c for x in ("salvage", "rebuilt", "parts", "junk", "damaged")):
        return "salvage"
    return "used"


def _title_bucket(vehicle_title: str | None) -> tuple[str, bool]:
    """(bucket, is_known) — unknown bucket when title not provided."""
    if _is_blank(vehicle_title):
        return "unknown", False
    t = vehicle_title.strip().lower()
    if t in ("not specified", "unspecified", "unknown", "n/a", "na", "—", "-", "other"):
        return "unknown", False
    if any(
        x in t
        for x in (
            "salvage",
            "rebuilt",
            "flood",
            "lemon",
            "junk",
            "parts only",
            "certificate of destruction",
        )
    ):
        return "risky", True
    if any(x in t for x in ("clean", "clear", "lien-free", "lien free")):
        return "clean", True
    return "unknown", True


def _resolve_signals(
    *,
    year: int | None,
    mileage: int | None,
    condition: str | None,
    vehicle_title: str | None,
    title_text: str | None = None,
) -> _VehicleSignals:
    y = _coerce_year(year)
    if y is None:
        y = _year_from_text(title_text)

    age: int | None = None
    age_known = y is not None
    if y is not None:
        age = max(0, datetime.now().year - y)

    mi = _coerce_mileage(mileage)
    cond = _norm_condition(condition)
    title, title_known = _title_bucket(vehicle_title)

    return _VehicleSignals(
        age=age,
        age_known=age_known,
        mileage=mi,
        mileage_known=mi is not None,
        condition=cond,
        condition_known=cond is not None,
        title=title,
        title_known=title_known,
    )


def _default_mileage_for_age(age: int) -> int:
    return max(12_000, age * 12_000)


def _repair_year_score(age: int | None, age_known: bool) -> tuple[float, float]:
    """Wear score 0 (new) … 1 (high) and effective weight."""
    if age_known and age is not None:
        return _clamp01(age / 16.0), _REPAIR_WEIGHT_YEAR
    # Unknown year: neutral wear, reduced confidence
    return 0.42, _REPAIR_WEIGHT_YEAR * 0.45


def _repair_mileage_score(
    mileage: int | None,
    mileage_known: bool,
    age: int | None,
    age_known: bool,
) -> tuple[float, float]:
    if mileage_known and mileage is not None:
        if age_known and age is not None and age > 0:
            expected = _default_mileage_for_age(age)
            ratio = mileage / max(expected, 1)
            score = _clamp01((ratio - 0.55) / 1.35)
        else:
            score = _clamp01((mileage - 15_000) / 175_000)
        return score, _REPAIR_WEIGHT_MILEAGE

    if age_known and age is not None:
        # No odometer: infer from age (average ~12k mi/yr)
        implied_ratio = 1.0
        score = _clamp01((implied_ratio - 0.55) / 1.35)
        return score, _REPAIR_WEIGHT_MILEAGE * 0.65

    return 0.48, _REPAIR_WEIGHT_MILEAGE * 0.4


def _repair_condition_score(condition: str | None, condition_known: bool) -> tuple[float, float]:
    if condition_known and condition is not None:
        scores = {
            "new": 0.06,
            "certified": 0.18,
            "used": 0.38,
            "salvage": 0.88,
        }
        return scores.get(condition, 0.38), _REPAIR_WEIGHT_CONDITION

    return 0.34, _REPAIR_WEIGHT_CONDITION * 0.5


def _repair_pct(signals: _VehicleSignals, listing_id: str | None) -> float:
    """Repair % of purchase price — primarily year, mileage, condition."""
    parts: list[tuple[float, float]] = []

    y_score, y_w = _repair_year_score(signals.age, signals.age_known)
    parts.append((y_w, y_score))

    m_score, m_w = _repair_mileage_score(
        signals.mileage,
        signals.mileage_known,
        signals.age,
        signals.age_known,
    )
    parts.append((m_w, m_score))

    c_score, c_w = _repair_condition_score(signals.condition, signals.condition_known)
    parts.append((c_w, c_score))

    if signals.title_known and signals.title == "risky":
        parts.append((_REPAIR_WEIGHT_TITLE_RISKY, 0.92))
    elif signals.title_known and signals.title == "clean":
        parts.append((_REPAIR_WEIGHT_TITLE_RISKY * 0.5, 0.12))

    total_w = sum(w for w, _ in parts)
    if total_w <= 0:
        blended = 0.4
    else:
        blended = sum(w * s for w, s in parts) / total_w

    missing = sum(
        1
        for known in (
            signals.age_known,
            signals.mileage_known,
            signals.condition_known,
        )
        if not known
    )
    uncertainty = 0.008 * missing
    jitter = _stable_jitter(listing_id, 0.012)

    pct = _REPAIR_PCT_FLOOR + _REPAIR_PCT_SPAN * blended + uncertainty + jitter
    return max(0.015, min(0.42, pct))


def _mileage_ratio(signals: _VehicleSignals) -> float:
    age = signals.age if signals.age_known and signals.age is not None else 7
    expected = _default_mileage_for_age(age)
    mi = signals.mileage if signals.mileage_known and signals.mileage is not None else expected
    return mi / max(expected, 1)


def _margin_pct(
    signals: _VehicleSignals,
    listing_format: str | None,
    listing_id: str | None,
) -> float:
    """Resale margin (separate from repair); uses same signals when available."""
    age = signals.age if signals.age_known and signals.age is not None else 7
    cond = signals.condition if signals.condition_known else "used"
    title = signals.title if signals.title_known else "unknown"
    ratio = _mileage_ratio(signals)

    margin = 0.055
    if age <= 3:
        margin += 0.065 - age * 0.012
    elif age <= 8:
        margin += 0.028 - (age - 3) * 0.0045
    elif age <= 14:
        margin += 0.006 - (age - 8) * 0.0025
    else:
        margin -= 0.015 + min(0.04, (age - 14) * 0.003)

    if cond == "new":
        margin += 0.035
    elif cond == "certified":
        margin += 0.022
    elif cond == "salvage":
        margin -= 0.14

    if title == "clean":
        margin += 0.028
    elif title == "risky":
        margin -= 0.11

    if ratio < 0.75:
        margin += 0.038
    elif ratio > 1.4:
        margin -= min(0.09, (ratio - 1.4) * 0.07)

    fmt = (listing_format or "").upper()
    if "AUCTION" in fmt:
        margin += 0.042

    if not signals.age_known:
        margin -= 0.012
    if not signals.mileage_known:
        margin -= 0.008

    margin += _stable_jitter(listing_id, 0.028)
    return max(-0.09, min(0.24, margin))


def estimate_flip_economics(
    purchase_price: float,
    *,
    year: int | None = None,
    mileage: int | None = None,
    condition: str | None = None,
    vehicle_title: str | None = None,
    listing_format: str | None = None,
    listing_id: str | None = None,
    title_text: str | None = None,
    bid_count: int | None = None,
) -> dict[str, Any]:
    """
    Estimate reconditioning cost and after-repair resale (ARV).

    Uses the existing heuristic model when sufficient data is present.
    Falls back to a transparent depreciation model when key signals are missing.
    """
    price = max(1.0, float(purchase_price))
    price, _ = resolve_effective_purchase_price(
        price,
        listing_format=listing_format,
        bid_count=bid_count,
        year=year,
        title_text=title_text,
    )
    signals = _resolve_signals(
        year=year,
        mileage=mileage,
        condition=condition,
        vehicle_title=vehicle_title,
        title_text=title_text,
    )

    # Count how many core signals we actually have
    known_signals = sum(
        [
            signals.age_known,
            signals.mileage_known,
            signals.condition_known,
            signals.title_known,
        ]
    )

    # === FALLBACK: Transparent Depreciation Model (sparse data) ===
    if known_signals < 3:
        age = signals.age if signals.age_known else 7

        # Age factor (compounds annually)
        if age <= 1:
            age_factor = 0.85
        elif age <= 3:
            age_factor = 0.85 * (0.90 ** (age - 1))
        elif age <= 8:
            age_factor = 0.85 * (0.90**2) * (0.95 ** (age - 3))
        else:
            age_factor = max(0.25, 0.85 * (0.90**2) * (0.95**5) * (0.97 ** (age - 8)))

        # Mileage adjustment (-$0.18/mile over 12k/yr average)
        expected_mileage = 12_000 * max(1, age)
        actual_mileage = signals.mileage if signals.mileage_known else expected_mileage
        mileage_diff = actual_mileage - expected_mileage
        mileage_adjustment = mileage_diff * -0.18
        mileage_adjustment = max(-price * 0.25, min(price * 0.25, mileage_adjustment))

        # Condition & Title multipliers (Conservative for private sellers)
        cond = signals.condition if signals.condition_known else "used"
        title = signals.title if signals.title_known else "unknown"

        CONDITION_MAP = {
            "new": 1.05,  # -10%
            "certified": 0.95,  # -13%
            "used": 0.82,  # -18%
            "salvage": 0.55,  # -15%
            "fair": 0.70,  # -18%
            "poor": 0.50,  # -23%
        }
        TITLE_MAP = {"clean": 1.05, "rebuilt": 0.80, "salvage": 0.70, "risky": 0.75, "unknown": 1.0}

        condition_factor = CONDITION_MAP.get(cond, 1.0)
        title_factor = TITLE_MAP.get(title, 1.0)

        # Calculate estimated resale value
        estimated_value = price * age_factor * condition_factor * title_factor + mileage_adjustment

        # Private seller discount (12% less than dealer pricing)
        estimated_value = estimated_value * 0.88

        # Clamp bounds
        estimated_value = max(price * 0.25, min(price * 0.95, estimated_value))

        # Dynamic repair cost
        REPAIR_PCT = {
            "new": 0.04,
            "certified": 0.06,
            "used": 0.08,
            "salvage": 0.25,
            "fair": 0.12,
            "poor": 0.18,
        }
        repair_pct = REPAIR_PCT.get(cond, 0.08)
        repair_cost = round(max(200.0, estimated_value * repair_pct), 2)

        confidence = round(0.20 + (known_signals * 0.20), 2)
        return {
            "repair_cost": repair_cost,
            "resale_value": round(estimated_value, 2),
            "confidence": confidence,
            "breakdown": {
                "base_price": round(price, 2),
                "age_factor": round(age_factor, 3),
                "mileage_adjustment": round(mileage_adjustment, 2),
                "condition_factor": round(condition_factor, 3),
                "title_factor": round(title_factor, 3),
            },
        }

    # === PRIMARY: Existing Heuristic Model (sufficient data) ===
    repair_pct = _repair_pct(signals, listing_id)
    repair_cost = round(max(200.0, price * repair_pct), 2)

    margin_pct = _margin_pct(signals, listing_format, listing_id)
    recovery_rate = 0.52
    fees = round(price * 0.022, 2)
    resale_value = round(
        price * (1.0 + margin_pct) + repair_cost * recovery_rate - fees,
        2,
    )
    resale_value = max(round(price * 0.82, 2), resale_value)

    # Add transparency fields to primary model for UI consistency
    confidence = round(0.40 + (known_signals * 0.15), 2)
    return {
        "repair_cost": repair_cost,
        "resale_value": resale_value,
        "confidence": confidence,
        "breakdown": {
            "repair_pct": round(repair_pct, 4),
            "margin_pct": round(margin_pct, 4),
            "recovery_rate": recovery_rate,
            "fees": fees,
        },
    }


def economics_from_title(
    purchase_price: float,
    title: str,
    *,
    year_hint: int | None = None,
    listing_id: str | None = None,
) -> dict[str, float]:
    """Fallback when only title + price are known."""
    return estimate_flip_economics(
        purchase_price,
        year=year_hint,
        title_text=title,
        listing_id=listing_id,
    )


def estimate_flip_from_listing(
    price: float,
    *,
    year: int | None = None,
    mileage: int | None = None,
    condition: str | None = None,
    vehicle_title: str | None = None,
    listing_format: str | None = None,
    listing_id: str | None = None,
    title_text: str | None = None,
    bid_count: int | None = None,
) -> tuple[float, float]:
    """
    Back-compat tuple API for eBay inventory (wraps estimate_flip_economics).

    Pass None/omit for condition/title when the listing did not specify them;
    display defaults like \"Used\" belong in the UI layer, not here.
    """
    cond = condition
    if cond and cond.strip().lower() in (
        "not specified",
        "unspecified",
        "unknown",
        "n/a",
        "na",
    ):
        cond = None
    vtitle = vehicle_title
    if vtitle and vtitle.strip().lower() in (
        "not specified",
        "unspecified",
        "unknown",
        "n/a",
        "na",
    ):
        vtitle = None
    econ = estimate_flip_economics(
        price,
        year=year,
        mileage=mileage,
        condition=cond,
        vehicle_title=vtitle,
        listing_format=listing_format,
        listing_id=listing_id,
        title_text=title_text,
        bid_count=bid_count,
    )
    return econ["repair_cost"], econ["resale_value"]
