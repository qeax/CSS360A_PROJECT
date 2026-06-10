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
) -> dict[str, Any]:
    """
    Estimate reconditioning cost and after-repair resale (ARV).

    Uses the existing heuristic model when sufficient data is present.
    Falls back to a transparent depreciation model when key signals are missing.
    """
    price = max(1.0, float(purchase_price))
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

        # Mileage adjustment (-$0.12/mile over 12k/yr average)
        expected_mileage = 12_000 * max(1, age)
        actual_mileage = signals.mileage if signals.mileage_known else expected_mileage
        mileage_diff = actual_mileage - expected_mileage
        mileage_adjustment = mileage_diff * -0.12
        mileage_adjustment = max(-price * 0.25, min(price * 0.25, mileage_adjustment))

        # Condition & Title multipliers
        cond = signals.condition if signals.condition_known else "used"
        title = signals.title if signals.title_known else "unknown"
        CONDITION_MAP = {
            "new": 1.15,
            "certified": 1.08,
            "used": 1.0,
            "salvage": 0.65,
            "fair": 0.85,
            "poor": 0.65,
        }
        TITLE_MAP = {"clean": 1.05, "rebuilt": 0.80, "salvage": 0.70, "risky": 0.75, "unknown": 1.0}
        condition_factor = CONDITION_MAP.get(cond, 1.0)
        title_factor = TITLE_MAP.get(title, 1.0)

        # Calculate estimated resale value
        estimated_value = price * age_factor * condition_factor * title_factor + mileage_adjustment
        estimated_value = max(price * 0.30, min(price * 1.20, estimated_value))

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
    )
    return econ["repair_cost"], econ["resale_value"]
