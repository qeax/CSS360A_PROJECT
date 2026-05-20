from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.integrations.ebay.client import EbayListingClient

router = APIRouter(prefix="/ebay", tags=["eBay"])
ebay_client = EbayListingClient()

@router.get("/search")
async def search_ebay_cars(
    query: str = Query(..., min_length=3, description="Search query (e.g., 'Toyota Camry')"),
    max_price: Optional[int] = Query(None, ge=0, description="Maximum price filter"),
    limit: int = Query(5, ge=1, le=20, description="Number of results (1-20)")
):
    """Search eBay for car listings"""
    if not ebay_client.is_configured():
        raise HTTPException(
            status_code=503, 
            detail="eBay API credentials missing. Add EBAY_CLIENT_ID to .env"
        )
    
    results = ebay_client.search_listings(query=query, max_price=max_price, limit=limit)
    return {"success": True, "count": len(results), "results": results}

@router.get("/health")
async def health_check():
    """Check eBay API configuration status"""
    return {
        "service": "eBay API",
        "configured": ebay_client.is_configured(),
        "sandbox": ebay_client.sandbox,
        "base_url": ebay_client.base_url
    }