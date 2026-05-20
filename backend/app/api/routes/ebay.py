from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import get_inventory_mode, in_memory_demo_enabled
from app.db import SessionLocal
from app.integrations.ebay.client import get_ebay_client
from app.repositories.cars import _stored_cars_exist

router = APIRouter(prefix="/ebay", tags=["eBay"])


@router.get("/search")
async def search_ebay_cars(
    query: str = Query(..., min_length=3, description="Search query (e.g., 'Toyota Camry')"),
    max_price: Optional[int] = Query(None, ge=0, description="Maximum price filter"),
    limit: int = Query(5, ge=1, le=20, description="Number of results (1-20)"),
):
    """Debug endpoint: direct eBay search (main UI uses GET /cars)."""
    client = get_ebay_client()
    if not client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="eBay API credentials missing. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in .env",
        )

    results = client.search_listings_enriched(query=query, max_price=max_price, limit=limit)
    if not results:
        raise HTTPException(status_code=502, detail="eBay search returned no results")
    return {"success": True, "count": len(results), "results": results}


@router.get("/health")
async def health_check():
    """Check eBay API configuration and inventory mode (debug deploy issues)."""
    client = get_ebay_client()
    db_has_cars = False
    with SessionLocal() as db:
        db_has_cars = _stored_cars_exist(db)
    return {
        "service": "eBay API",
        "configured": client.is_configured(),
        "sandbox": client.sandbox,
        "base_url": client.base_url,
        "inventory_mode": get_inventory_mode(),
        "in_memory_demo_enabled": in_memory_demo_enabled(),
        "database_has_cars": db_has_cars,
    }
