"""eBay Browse/Buy APIs integration.

Fetches listing data from eBay and normalizes into our Car schema.
"""

import base64
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_client: "EbayListingClient | None" = None


def get_ebay_client() -> "EbayListingClient":
    global _client
    if _client is None:
        _client = EbayListingClient()
    return _client


def reset_ebay_client() -> None:
    """Drop cached client (tests after env changes)."""
    global _client
    _client = None


class EbayListingClient:
    """Client for eBay Browse/Buy APIs with OAuth2 token management."""

    def __init__(self) -> None:
        """Initialize eBay client with environment credentials."""
        self.client_id = os.getenv("EBAY_CLIENT_ID")
        self.client_secret = os.getenv("EBAY_CLIENT_SECRET")
        self.sandbox = os.getenv("EBAY_SANDBOX", "true").lower() == "true"
        self.base_url = "https://api.sandbox.ebay.com" if self.sandbox else "https://api.ebay.com"
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

    def is_configured(self) -> bool:
        """Check if client has required credentials."""
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> Optional[str]:
        """Retrieve or refresh OAuth2 access token."""
        if not self.is_configured():
            return None
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token

        try:
            url = f"{self.base_url}/identity/v1/oauth2/token"
            credentials = f"{self.client_id}:{self.client_secret}"
            headers = {
                "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            }
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.token_expiry = datetime.now() + timedelta(seconds=token_data["expires_in"])
            return self.access_token
        except Exception as e:
            logger.warning("eBay token error: %s", e)
            return None

    def search_listings(
        self, query: str, max_price: Optional[int] = None, limit: int = 5
    ) -> List[Dict]:
        """Search eBay for listings and return normalized results (empty list on failure)."""
        if not self.is_configured():
            return []
        token = self._get_access_token()
        if not token:
            return []
        try:
            url = f"{self.base_url}/buy/browse/v1/item_summary/search"
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            params = {"q": query, "limit": limit}
            if max_price:
                params["filter"] = f"price:{{max:{max_price}}}"
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            items = response.json().get("itemSummaries", [])
            results: List[Dict] = []
            for item in items[:limit]:
                # Safe nested access with type checks
                p = item.get("price") or {}
                loc = item.get("location") or {}
                cond = item.get("condition") or {}
                img = item.get("image") or {}
                results.append(
                    {
                        "external_listing_id": item.get("itemId"),
                        "title": item.get("title"),
                        "price": p.get("value") if isinstance(p, dict) else None,
                        "currency": p.get("currency") if isinstance(p, dict) else None,
                        "condition": cond.get("displayName") if isinstance(cond, dict) else None,
                        "location_city": loc.get("city") if isinstance(loc, dict) else None,
                        "listing_url": item.get("itemWebUrl"),
                        "image_url": img.get("imageUrl") if isinstance(img, dict) else None,
                        "source": "ebay",
                    }
                )
            return results
        except Exception as e:
            logger.warning("eBay search failed: %s", e)
            return []

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full listing details (localizedAspects, delivery, seller, etc.)."""
        if not self.is_configured() or not item_id:
            return None
        token = self._get_access_token()
        if not token:
            return None
        try:
            encoded_id = quote(item_id, safe="")
            url = f"{self.base_url}/buy/browse/v1/item/{encoded_id}"
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            params = {"fieldgroups": "PRODUCT"}
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("eBay getItem failed for %s: %s", item_id, e)
            return None

    def search_listings_enriched(
        self, query: str, max_price: Optional[int] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search then hydrate rows with getItem (capped by EBAY_GET_ITEM_MAX)."""
        summaries = self.search_listings(query=query, max_price=max_price, limit=limit)
        if not summaries:
            return []
        try:
            enrich_max = int(os.getenv("EBAY_GET_ITEM_MAX", "20"))
        except ValueError:
            enrich_max = 20
        if enrich_max <= 0:
            return summaries

        from app.integrations.ebay.parse_item import merge_search_summary

        enriched: List[Dict[str, Any]] = []
        for row in summaries[:enrich_max]:
            item_id = row.get("external_listing_id")
            detail = self.get_item(item_id) if item_id else None
            enriched.append(merge_search_summary(row, detail))
        enriched.extend(summaries[enrich_max:])
        return enriched
