"""Generate realistic demo inventory (cars + locations + terms + media + aspects).

Same deterministic data can be:
- inserted into the DB (``insert_generated_demo_cars``) when explicitly enabled, or
- materialized as in-memory view objects for the API when the ``cars`` table is empty
  (see ``build_in_memory_demo_car_views`` and ``DEMO_IN_MEMORY_WHEN_EMPTY`` in ``repositories/cars``).
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.car import Car
from app.models.car_satellite import CarListingTerms, CarLocation, CarMedia, VehicleAspectSnapshot
from app.services.flip import estimate_flip_economics

_BRAND_MODEL = [
    ("Toyota", "Camry"),
    ("Toyota", "RAV4"),
    ("Honda", "Civic"),
    ("Honda", "Accord"),
    ("Ford", "F-150"),
    ("Ford", "Escape"),
    ("Chevrolet", "Silverado"),
    ("Chevrolet", "Equinox"),
    ("Nissan", "Altima"),
    ("Nissan", "Rogue"),
    ("BMW", "330i"),
    ("BMW", "X3"),
    ("Mercedes-Benz", "C300"),
    ("Audi", "A4"),
    ("Hyundai", "Elantra"),
    ("Kia", "Telluride"),
    ("Subaru", "Outback"),
    ("Volkswagen", "Jetta"),
    ("Mazda", "CX-5"),
    ("Jeep", "Grand Cherokee"),
    ("Tesla", "Model 3"),
    ("Volvo", "XC60"),
    ("Lexus", "RX 350"),
    ("GMC", "Sierra"),
    ("Ram", "1500"),
    ("Acura", "TLX"),
    ("Infiniti", "Q50"),
    ("Cadillac", "XT5"),
    ("Buick", "Enclave"),
    ("Chrysler", "Pacifica"),
    ("Dodge", "Charger"),
]

_BODY_TYPES = [
    "Commercial Vehicle",
    "Convertible",
    "Coupe",
    "Hatchback",
    "Minivan",
    "Sedan",
    "SUV",
    "Wagon",
    "Not Specified",
]

_CONDITIONS = ["New", "Pre-owned", "Used"]

_LISTING_FORMATS = ["AUCTION", "BUY_IT_NOW", "CLASSIFIED_AD", "ACCEPTS_OFFER"]

_VEHICLE_TITLES = [
    "Clean",
    "Finance Owing/Encumbered",
    "Flood/Water Damage",
    "Lemon & Manufacturer Buyback",
    "Rebuilt/Rebuildable & Reconstructed",
    "Salvage",
    "Not Specified",
]

_CITIES: list[tuple[str, str, str, float, float]] = [
    ("United States", "WA", "Seattle", 47.6062, -122.3321),
    ("United States", "WA", "Tacoma", 47.2529, -122.4443),
    ("United States", "OR", "Portland", 45.5152, -122.6784),
    ("United States", "CA", "San Francisco", 37.7749, -122.4194),
    ("United States", "CA", "Los Angeles", 34.0522, -118.2437),
    ("United States", "TX", "Austin", 30.2672, -97.7431),
    ("United States", "TX", "Dallas", 32.7767, -96.7970),
    ("United States", "FL", "Miami", 25.7617, -80.1918),
    ("United States", "NY", "Buffalo", 42.8864, -78.8784),
    ("United States", "IL", "Chicago", 41.8781, -87.6298),
    ("United States", "CO", "Denver", 39.7392, -104.9903),
    ("United States", "AZ", "Phoenix", 33.4484, -112.0740),
    ("United States", "GA", "Atlanta", 33.7490, -84.3880),
    ("United States", "MA", "Boston", 42.3601, -71.0589),
    ("United States", "MI", "Detroit", 42.3314, -83.0458),
]

_IMAGE_CATALOG: dict[str, list[str]] | None = None
_DEMO_AUCTION_BASE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _get_image_catalog() -> dict[str, list[str]]:
    global _IMAGE_CATALOG
    if _IMAGE_CATALOG is None:
        p = Path(__file__).resolve().parent / "data" / "demo_vehicle_images.json"
        if p.is_file():
            raw = json.loads(p.read_text(encoding="utf-8"))
            _IMAGE_CATALOG = {k: list(v) for k, v in raw.items() if isinstance(v, list)}
        else:
            _IMAGE_CATALOG = {}
    return _IMAGE_CATALOG


def _catalog_urls_for(brand: str, model: str, cat: dict[str, list[str]]) -> list[str] | None:
    key = f"{brand}|{model}"
    if key in cat and cat[key]:
        return list(cat[key])
    prefix = f"{brand}|"
    for k, urls in sorted(cat.items()):
        if k != "default" and k.startswith(prefix) and urls:
            return list(urls)
    default = cat.get("default")
    if default:
        return list(default)
    return None


def pick_media_urls_for_car(brand: str, model: str, index: int) -> list[str]:
    """Public helper for API layer to resolve demo vehicle photos."""
    return _pick_media_urls(brand, model, index)


def _stable_demo_photo_url(brand: str, model: str, index: int, slot: int) -> str:
    """Deterministic placeholder photo per vehicle (stable across reloads)."""
    seed = abs(hash(f"{brand}|{model}|{index}|{slot}")) % 2_147_483_647
    return f"https://picsum.photos/seed/css360-{seed}/800/600"


def _pick_media_urls(brand: str, model: str, index: int) -> list[str]:
    """Return 3–5 stable demo photo URLs (catalog Wikimedia URLs are not hotlink-safe)."""
    n_images = 3 + (index % 3)
    return [_stable_demo_photo_url(brand, model, index, j) for j in range(n_images)]


def clamped_demo_count(count: int | None = None) -> int:
    n = count if count is not None else int(os.environ.get("DEMO_SEED_COUNT", "100"))
    return max(1, min(n, 500))


def _jitter_coord(lat: float, lng: float, rng: random.Random) -> tuple[Decimal, Decimal]:
    return (
        Decimal(str(round(lat + rng.uniform(-0.08, 0.08), 5))),
        Decimal(str(round(lng + rng.uniform(-0.08, 0.08), 5))),
    )


def iter_demo_specs(n: int, rng: random.Random) -> Iterator[dict[str, Any]]:
    """Yield one spec dict per demo row (deterministic for a given ``n`` and ``rng`` seed)."""
    for i in range(n):
        brand, model = rng.choice(_BRAND_MODEL)
        year = rng.randint(2012, 2024)
        price = float(rng.randint(55, 420)) * 100 + rng.choice([0, 50, 95])
        mileage = rng.randint(8000, 145000)
        condition = rng.choice(_CONDITIONS)
        fmt = rng.choice(_LISTING_FORMATS)
        body = rng.choice(_BODY_TYPES)
        vtitle = rng.choice(_VEHICLE_TITLES)
        city_row = rng.choice(_CITIES)
        country, region, city, lat0, lng0 = city_row
        lat, lng = _jitter_coord(lat0, lng0, rng)
        ext_id = f"demo-{i + 1:04d}"
        summary = (
            f"{year} {brand} {model} — {mileage:,d} mi, {condition}. "
            f"{vtitle} title. {rng.choice(['One owner', 'Two owners', 'Fleet maintained'])}."
        )
        ship = rng.random() < 0.55
        local_pu = rng.random() < 0.72
        in_store = rng.random() < 0.15
        if not ship and not local_pu and not in_store:
            local_pu = True
        drive = rng.choice(["FWD", "AWD", "RWD", "4WD"])
        aspects: list[dict[str, Any]] = [
            {"localizedAspectName": "Body Type", "localizedAspectValues": [body]},
            {"localizedAspectName": "Drive Type", "localizedAspectValues": [drive]},
        ]
        urls = _pick_media_urls(brand, model, i)
        media = [{"sort_order": j, "url": u} for j, u in enumerate(urls)]

        bid_count = None
        listing_ends_at = None
        if fmt == "AUCTION":
            bid_count = rng.randint(1, 24)
            listing_ends_at = _DEMO_AUCTION_BASE + timedelta(hours=rng.randint(2, 72))

        econ = estimate_flip_economics(
            price,
            year=year,
            mileage=mileage,
            condition=condition,
            vehicle_title=vtitle,
            listing_format=fmt,
            listing_id=ext_id,
        )
        repair = econ["repair_cost"]
        resale = econ["resale_value"]

        yield {
            "index": i,
            "car_core": {
                "brand": brand,
                "model": model,
                "year": year,
                "price": price,
                "repair_cost": repair,
                "resale_value": float(f"{resale:.2f}"),
                "mileage": mileage,
                "condition": condition,
                "vehicle_title": vtitle,
                "image_url": urls[0],
                "source": "demo",
                "external_listing_id": ext_id,
                "listing_url": f"https://example.invalid/listings/{ext_id}",
                "listing_format": fmt,
                "bid_count": bid_count,
                "listing_ends_at": listing_ends_at,
                "description_summary": summary[:512],
            },
            "location": {
                "country": country,
                "region": region,
                "city": city,
                "postal_code_masked": f"{rng.randint(10000, 99999)}**",
                "latitude": lat,
                "longitude": lng,
            },
            "listing_terms": {
                "ship_to_home": ship,
                "local_pickup": local_pu,
                "in_store_pickup": in_store,
            },
            "aspects_json": aspects,
            "media": media,
        }


def build_in_memory_demo_car_views(count: int | None = None) -> list[Any]:
    """Car-like objects for ``apply_filters`` / meta (no SQLAlchemy session)."""
    n = clamped_demo_count(count)
    rng = random.Random(42)
    views: list[Any] = []
    for spec in iter_demo_specs(n, rng):
        i = spec["index"]
        loc = SimpleNamespace(**spec["location"])
        terms = SimpleNamespace(**spec["listing_terms"])
        media = [SimpleNamespace(**m) for m in spec["media"]]
        snap = SimpleNamespace(id=i + 1, captured_at=None, aspects_json=spec["aspects_json"])
        core = spec["car_core"]
        views.append(
            SimpleNamespace(
                id=i + 1,
                external_seller=None,
                location=loc,
                listing_terms=terms,
                media=media,
                aspect_snapshots=[snap],
                **core,
            )
        )
    return views


def insert_generated_demo_cars(db: Session, count: int | None = None) -> int:
    """Insert ``count`` demo cars with satellites. Deterministic for a given count."""
    n = clamped_demo_count(count)
    rng = random.Random(42)
    created = 0
    for spec in iter_demo_specs(n, rng):
        car = Car(**spec["car_core"])
        db.add(car)
        db.flush()

        loc = {**spec["location"], "car_id": car.id}
        db.add(CarLocation(**loc))

        lt = {**spec["listing_terms"], "car_id": car.id}
        db.add(CarListingTerms(**lt))

        db.add(VehicleAspectSnapshot(car_id=car.id, aspects_json=spec["aspects_json"]))

        for m in spec["media"]:
            db.add(CarMedia(car_id=car.id, sort_order=m["sort_order"], url=m["url"]))
        created += 1
    return created
