from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import get_inventory_mode, in_memory_demo_enabled
from app.db import SessionLocal
from app.integrations.ebay.client import _ebay_category_ids, get_ebay_client
from app.integrations.ebay.inventory import probe_ebay_search
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
async def health_check(
    probe: bool = Query(False, description="Run a real eBay search and return counts"),
    probe_query: str = Query("car", min_length=3, description="Query for probe"),
):
    """Check eBay configuration and (optionally) sample sandbox/prod response."""
    client = get_ebay_client()
    db_has_cars = False
    with SessionLocal() as db:
        db_has_cars = _stored_cars_exist(db)
    payload = {
        "service": "eBay API",
        "configured": client.is_configured(),
        "sandbox": client.sandbox,
        "keys_look_sandbox": client._keys_look_sandbox,
        "sandbox_env_matches_keys": client.sandbox == client._keys_look_sandbox,
        "base_url": client.base_url,
        "category_ids_in_effect": _ebay_category_ids(),
        "inventory_mode": get_inventory_mode(),
        "in_memory_demo_enabled": in_memory_demo_enabled(),
        "database_has_cars": db_has_cars,
    }
    if probe and client.is_configured():
        payload["probe"] = probe_ebay_search(probe_query, limit=5)
    if client.last_search_diagnostic:
        payload["last_search"] = client.last_search_diagnostic
    return payload
