from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.db import get_db
from app.integrations.ebay.client import get_ebay_client
from app.models.car import Car
from app.models.user import User
from app.repositories.cars import (
    _q_tokens,
    apply_filters,
    compute_inventory_meta,
    iter_cars,
    sort_car_dicts_inplace,
)
from app.services.ebay_sync import EbaySyncCooldownError, sync_ebay_inventory

router = APIRouter(tags=["cars"])

_DEFAULT_PAGE_SIZE = 30
_MAX_PAGE_SIZE = 50


def _resolve_data_mode(sync_ebay: bool, sync_stats: dict[str, Any] | None) -> str:
    if not sync_ebay:
        return "database"
    if sync_stats is None:
        return "database"
    if not sync_stats.get("configured"):
        return "database"
    if sync_stats.get("status") == "ok":
        return "ebay_refreshed"
    return "database"


@router.get("/cars/{car_id}/raw-listing")
def get_car_raw_listing(
    car_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    car = db.execute(select(Car).where(Car.id == car_id)).scalar_one_or_none()
    if car is None or not car.raw_listing_json:
        raise HTTPException(status_code=404, detail="raw_listing_not_found")
    return {"id": car.id, "raw_listing_json": car.raw_listing_json}


@router.get("/cars/meta")
def get_cars_meta(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    try:
        return compute_inventory_meta(db)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e


@router.get("/cars")
def get_cars(
    make: Optional[str] = Query(None),
    makes: Annotated[Optional[list[str]], Query()] = None,
    model: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    min_mileage: Optional[int] = Query(None),
    max_mileage: Optional[int] = Query(None),
    condition: Optional[str] = Query(None),
    conditions: Annotated[Optional[list[str]], Query()] = None,
    max_price: Optional[float] = Query(None),
    min_price: Optional[float] = Query(None),
    min_profit: Optional[float] = Query(None),
    min_roi: Optional[float] = Query(None),
    exclude_negative_roi: bool = Query(False),
    exclude_negative_profit: bool = Query(False),
    q: Optional[str] = Query(None),
    countries: Annotated[Optional[list[str]], Query()] = None,
    regions: Annotated[Optional[list[str]], Query()] = None,
    cities: Annotated[Optional[list[str]], Query()] = None,
    radius_km: Optional[float] = Query(None),
    radius_mi: Optional[float] = Query(None),
    anchor_lat: Optional[float] = Query(None),
    anchor_lng: Optional[float] = Query(None),
    listing_formats: Annotated[Optional[list[str]], Query()] = None,
    body_styles: Annotated[Optional[list[str]], Query()] = None,
    delivery_modes: Annotated[Optional[list[str]], Query()] = None,
    vehicle_titles: Annotated[Optional[list[str]], Query()] = None,
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    sync_ebay: bool = Query(False),
    limit: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync_stats: dict | None = None
    if sync_ebay:
        if not get_ebay_client().is_configured():
            sync_stats = {"synced": 0, "configured": False, "skipped": True}
        else:
            try:
                sync_stats = sync_ebay_inventory(
                    db,
                    user_id=int(current_user.id),
                    q=q,
                )
            except EbaySyncCooldownError as e:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "ebay_sync_cooldown",
                        "retry_after_sec": round(e.retry_after_sec, 1),
                    },
                ) from e
            except Exception as e:
                db.rollback()
                sync_stats = {
                    "synced": 0,
                    "configured": True,
                    "status": "failed",
                    "error": str(e)[:500],
                }

    try:
        rows = iter_cars(db, inventory_query=q)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e

    results = apply_filters(
        rows,
        make=make,
        makes=makes,
        model=model,
        min_year=min_year,
        max_year=max_year,
        min_mileage=min_mileage,
        max_mileage=max_mileage,
        condition=condition,
        conditions=conditions,
        max_price=max_price,
        min_price=min_price,
        min_profit=min_profit,
        min_roi=min_roi,
        q=q,
        countries=countries,
        regions=regions,
        cities=cities,
        radius_km=radius_km,
        radius_mi=radius_mi,
        anchor_lat=anchor_lat,
        anchor_lng=anchor_lng,
        listing_formats=listing_formats,
        body_styles=body_styles,
        delivery_modes=delivery_modes,
        vehicle_titles=vehicle_titles,
        exclude_negative_roi=exclude_negative_roi,
        exclude_negative_profit=exclude_negative_profit or exclude_negative_roi,
    )

    effective_sort = sort_by
    if not effective_sort and not _q_tokens(q):
        effective_sort = "roi"
    sort_car_dicts_inplace(results, effective_sort, sort_order)
    total = len(results)
    page = results[offset : offset + limit]
    payload: dict = {
        "items": page,
        "total": total,
        "inventory_source": "database",
        "data_mode": _resolve_data_mode(sync_ebay, sync_stats),
    }
    if sync_stats is not None:
        payload["ebay_sync"] = sync_stats
    return payload
