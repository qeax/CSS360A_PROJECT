import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    invalidate_in_memory_demo_cache,
    load_car_by_id,
    load_inventory_for_request,
    sort_car_dicts_inplace,
)
from app.services.ebay_sync import (
    EbayRefreshError,
    EbaySyncCooldownError,
    _get_active_batch,
    continue_ebay_batch,
    ebay_batch_payload,
    refresh_car_from_ebay,
    start_ebay_batch,
)
from app.services.pricing import refresh_car_resale_estimate, refresh_resale_api_items
from app.services.search_query import normalize_search_key

router = APIRouter(tags=["cars"])
logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 50


def _resolve_data_mode(sync_ebay: bool, sync_stats: dict[str, Any] | None) -> str:
    if not sync_ebay:
        return "database"
    if sync_stats is None:
        return "database"
    if sync_stats is None:
        return "database"
    if not sync_stats.get("configured"):
        return "database"
    if sync_stats.get("status") == "ok":
        return "ebay_refreshed"
    return "database"


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


@router.get("/cars/{car_id}")
def get_car_detail(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.repositories.cars import car_to_detail_api_item

    car = load_car_by_id(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    try:
        item = car_to_detail_api_item(db, car, user_id=int(current_user.id), geocode=False)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "car_detail_failed", "message": str(e)},
        ) from e
    if item is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    return {"item": item}


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


@router.post("/cars/{car_id}/ebay-refresh")
def refresh_car_ebay(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.repositories.cars import car_to_detail_api_item

    try:
        outcome = refresh_car_from_ebay(db, car_id)
    except EbayRefreshError as e:
        code = str(e)
        if code == "car_not_found":
            raise HTTPException(status_code=404, detail="car_not_found") from e
        if code in ("not_ebay_listing", "missing_external_listing_id"):
            raise HTTPException(status_code=400, detail=code) from e
        if code == "ebay_not_configured":
            raise HTTPException(status_code=503, detail="ebay_not_configured") from e
        if code == "ebay_rate_limited":
            raise HTTPException(status_code=429, detail=code) from e
        if code.startswith("ebay_get_item_failed"):
            raise HTTPException(status_code=503, detail=code) from e
        raise HTTPException(status_code=503, detail=code) from e
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e

    if outcome.deleted:
        return {
            "deleted": True,
            "id": outcome.car_id,
            "message": outcome.message,
        }

    car = load_car_by_id(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    try:
        item = car_to_detail_api_item(db, car, user_id=int(current_user.id), geocode=False)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e
    if item is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    return {"item": item}


@router.post("/cars/{car_id}/resale-refresh")
def refresh_car_resale(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.repositories.cars import car_to_detail_api_item

    car = load_car_by_id(db, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    try:
        refresh_car_resale_estimate(db, car)
        db.commit()
        item = car_to_detail_api_item(db, car, user_id=int(current_user.id), geocode=False)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e
    if item is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    return {"item": item}


@router.delete("/cars/{car_id}", status_code=204)
def delete_car(
    car_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    car = db.execute(select(Car).where(Car.id == car_id)).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=404, detail="car_not_found")
    try:
        db.delete(car)
        db.commit()
        invalidate_in_memory_demo_cache()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e
    return Response(status_code=204)


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
    exclude_ended_auctions: bool = Query(True),
    exclude_unknown_price: bool = Query(False),
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
    ebay_batch_continue: bool = Query(False),
    limit: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync_stats: dict | None = None
    user_id = int(current_user.id)
    search_key = normalize_search_key(q)

    if ebay_batch_continue:
        if not get_ebay_client().is_configured():
            sync_stats = {
                "synced": 0,
                "configured": False,
                "skipped": True,
                "status": "not_configured",
                "wave_items": [],
                "ebay_batch": ebay_batch_payload(None),
            }
        else:
            try:
                sync_stats = continue_ebay_batch(db, user_id=user_id, q=q)
            except Exception as e:
                db.rollback()
                sync_stats = {
                    "synced": 0,
                    "configured": True,
                    "status": "failed",
                    "error": str(e)[:500],
                    "wave_items": [],
                    "ebay_batch": ebay_batch_payload(_get_active_batch(db, user_id, search_key)),
                }
    elif sync_ebay:
        if not get_ebay_client().is_configured():
            sync_stats = {
                "synced": 0,
                "configured": False,
                "skipped": True,
                "status": "not_configured",
                "wave_items": [],
                "ebay_batch": ebay_batch_payload(None),
            }
        else:
            try:
                sync_stats = start_ebay_batch(
                    db,
                    user_id=user_id,
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
                    "wave_items": [],
                    "ebay_batch": ebay_batch_payload(_get_active_batch(db, user_id, search_key)),
                }

    try:
        rows = load_inventory_for_request(db, search_key=search_key)
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
        exclude_ended_auctions=exclude_ended_auctions,
        exclude_unknown_price=exclude_unknown_price,
    )

    effective_sort = sort_by
    if not effective_sort and not _q_tokens(q):
        effective_sort = "roi"
    sort_car_dicts_inplace(results, effective_sort, sort_order)
    total = len(results)
    page = results[offset : offset + limit]
    try:
        page = refresh_resale_api_items(db, page)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": "database_unavailable", "message": str(e)},
        ) from e
    except Exception as e:
        db.rollback()
        logger.warning("resale refresh for page failed: %s", e)
    data_mode = _resolve_data_mode(sync_ebay or ebay_batch_continue, sync_stats)
    payload: dict = {
        "items": page,
        "total": total,
        "inventory_source": "database",
        "data_mode": data_mode,
    }
    if sync_stats is not None:
        payload["ebay_sync"] = sync_stats
        if sync_stats.get("ebay_batch") is not None:
            payload["ebay_batch"] = sync_stats["ebay_batch"]
    else:
        batch = _get_active_batch(db, user_id, search_key)
        if batch is not None:
            payload["ebay_batch"] = ebay_batch_payload(batch)

    return payload
