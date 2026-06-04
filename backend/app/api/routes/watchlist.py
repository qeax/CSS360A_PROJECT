"""Watchlist API — tracked listings (max 10 per user)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.db import get_db
from app.models.user import User
from app.services.watch_check import run_watch_check
from app.services.watchlist import (
    WATCHLIST_MAX,
    WatchlistLimitError,
    WatchlistNotFoundError,
    add_to_watchlist,
    list_watchlist_car_ids,
    list_watchlist_items,
    remove_from_watchlist,
)

router = APIRouter(tags=["watchlist"])


@router.get("/watchlist")
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        items = list_watchlist_items(db, int(current_user.id))
        return {"items": items, "total": len(items), "max": WATCHLIST_MAX}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.get("/watchlist/ids")
def get_watchlist_ids(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return {"ids": list_watchlist_car_ids(db, int(current_user.id))}
    except SQLAlchemyError as e:
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.post("/watchlist/check")
def post_watchlist_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return run_watch_check(db, int(current_user.id))
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.post("/watchlist/{car_id}")
def post_watchlist_item(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        add_to_watchlist(db, int(current_user.id), car_id)
        db.commit()
        return {"ok": True, "car_id": car_id}
    except WatchlistLimitError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": "watchlist_limit", "max": WATCHLIST_MAX},
        ) from e
    except WatchlistNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail="car_not_found") from e
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e


@router.delete("/watchlist/{car_id}", status_code=204)
def delete_watchlist_item(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        removed = remove_from_watchlist(db, int(current_user.id), car_id)
        if not removed:
            raise HTTPException(status_code=404, detail="not_watched")
        db.commit()
        return None
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "database_unavailable"}) from e
