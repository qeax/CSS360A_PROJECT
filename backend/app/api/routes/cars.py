from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.repositories.cars import (
    apply_filters,
    compute_inventory_meta,
    iter_cars,
    sort_car_dicts_inplace,
)

router = APIRouter(tags=["cars"])

_DEFAULT_PAGE_SIZE = 30
_MAX_PAGE_SIZE = 50


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
    limit: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    try:
        rows = iter_cars(db)
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
    )

    sort_car_dicts_inplace(results, sort_by, sort_order)
    total = len(results)
    page = results[offset : offset + limit]
    return {"items": page, "total": total}
