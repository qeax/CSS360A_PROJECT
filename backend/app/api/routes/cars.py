from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.repositories.cars import apply_filters, iter_cars

router = APIRouter(tags=["cars"])


@router.get("/cars")
def get_cars(
    make: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    min_year: Optional[int] = Query(None),
    max_year: Optional[int] = Query(None),
    condition: Optional[str] = Query(None),
    max_price: Optional[float] = Query(None),
    min_profit: Optional[float] = Query(None),
    min_roi: Optional[float] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("desc"),
    db: Session = Depends(get_db),
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
        model=model,
        min_year=min_year,
        max_year=max_year,
        condition=condition,
        max_price=max_price,
        min_profit=min_profit,
        min_roi=min_roi,
    )

    if sort_by:
        reverse_sort = sort_order == "desc"
        if sort_by == "net_profit":
            results.sort(key=lambda x: x["net_profit"], reverse=reverse_sort)
        elif sort_by == "price":
            results.sort(key=lambda x: x["price"], reverse=reverse_sort)
        elif sort_by == "roi":
            results.sort(key=lambda x: x["roi"], reverse=reverse_sort)

    return results
