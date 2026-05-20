"""eBay Browse/Buy APIs integration.

Fetches listing data from eBay and normalizes into our Car schema.
"""

import base64
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _ebay_sandbox_enabled() -> bool:
    return os.getenv("EBAY_SANDBOX", "true").strip().lower() == "true"


def _ebay_category_ids() -> str | None:
    """
    Cars & Trucks category (default 6001) — applied in **production** only.

    Sandbox Motors catalog is almost empty; passing `category_ids` there
    usually returns 0 results. Override with EBAY_FORCE_CATEGORY_IDS=true.
    """
    raw = (os.getenv("EBAY_CATEGORY_IDS") or "6001").strip()
    if not raw:
        return None
    if _ebay_sandbox_enabled():
        force = os.getenv("EBAY_FORCE_CATEGORY_IDS", "").strip().lower()
        if force not in ("1", "true", "yes", "on"):
            return None
    return raw


def _ebay_search_limit() -> int:
    """Per-page limit (eBay Browse allows up to 200)."""
    try:
        return max(1, min(int(os.getenv("EBAY_SEARCH_LIMIT", "50")), 200))
    except ValueError:
        return 50


def _ebay_search_pages() -> int:
    try:
        return max(1, min(int(os.getenv("EBAY_SEARCH_PAGES", "2")), 5))
    except ValueError:
        return 2


def ebay_fetch_cap() -> int:
    """Max distinct listings to pull per inventory refresh."""
    return _ebay_search_limit() * _ebay_search_pages()


def _search_filter_param(max_price: Optional[int] = None) -> str:
    """
    Browse search returns only FIXED_PRICE listings by default.
    Vehicles are mostly auctions — always request both formats.
    """
    parts = ["buyingOptions:{AUCTION|FIXED_PRICE}"]
    if max_price is not None and max_price > 0:
        parts.append(f"price:[..{int(max_price)}]")
    return ",".join(parts)


class EbayListingClient:
    """Client for eBay Browse/Buy APIs with OAuth2 token management."""

    def __init__(self) -> None:
        """Initialize eBay client with environment credentials."""
        self.client_id = (os.getenv("EBAY_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("EBAY_CLIENT_SECRET") or "").strip()
        self.sandbox = os.getenv("EBAY_SANDBOX", "true").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._keys_look_sandbox = self._credentials_look_sandbox()
        if self._keys_look_sandbox and not self.sandbox:
            logger.error(
                "eBay App ID/secret look like SANDBOX (SBX) but EBAY_SANDBOX=false — "
                "use api.sandbox.ebay.com or production keys on api.ebay.com"
            )
        elif not self._keys_look_sandbox and self.sandbox and self.client_id:
            logger.warning("eBay keys do not look like SANDBOX (no SBX) but EBAY_SANDBOX=true")
        self.base_url = "https://api.sandbox.ebay.com" if self.sandbox else "https://api.ebay.com"
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.last_search_diagnostic: dict[str, Any] = {}

    def _credentials_look_sandbox(self) -> bool:
        cid = self.client_id.upper()
        sec = self.client_secret.upper()
        return "SBX" in cid or sec.startswith("SBX-")

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
            response = requests.post(url, headers=headers, data=data, timeout=8)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.token_expiry = datetime.now() + timedelta(seconds=token_data["expires_in"])
            return self.access_token
        except requests.HTTPError as e:
            body = e.response.text[:300] if e.response is not None else ""
            logger.warning("eBay token HTTP %s: %s", getattr(e.response, "status_code", "?"), body)
            return None
        except Exception as e:
            logger.warning("eBay token error: %s", e)
            return None

    def _search_request(
        self,
        *,
        query: str | None,
        limit: int,
        category_ids: str | None,
        max_price: Optional[int] = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Low-level search; returns API metadata for diagnostics."""
        diag: dict[str, Any] = {
            "query": query,
            "category_ids": category_ids,
            "http_status": None,
            "total": 0,
            "item_count": 0,
            "error": None,
            "filter": _search_filter_param(max_price),
        }
        if not self.is_configured():
            diag["error"] = "not_configured"
            return diag
        token = self._get_access_token()
        if not token:
            diag["error"] = "token_failed"
            return diag
        if not query and not category_ids:
            diag["error"] = "missing_query_and_category"
            return diag
        try:
            url = f"{self.base_url}/buy/browse/v1/item_summary/search"
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            params: dict[str, Any] = {
                "limit": min(limit, _ebay_search_limit()),
                "filter": diag["filter"],
            }
            if offset > 0:
                params["offset"] = offset
            if query:
                params["q"] = query
            if category_ids:
                params["category_ids"] = category_ids
            response = requests.get(url, headers=headers, params=params, timeout=10)
            diag["http_status"] = response.status_code
            response.raise_for_status()
            payload = response.json()
            items = payload.get("itemSummaries") or []
            diag["total"] = int(payload.get("total") or 0)
            diag["item_count"] = len(items)
            diag["items"] = items
            return diag
        except requests.HTTPError as e:
            body = e.response.text[:500] if e.response is not None else ""
            diag["http_status"] = getattr(e.response, "status_code", None)
            diag["error"] = body or str(e)
            logger.warning(
                "eBay search HTTP %s q=%r cat=%r: %s",
                diag["http_status"],
                query,
                category_ids,
                body,
            )
            return diag
        except Exception as e:
            diag["error"] = str(e)
            logger.warning("eBay search failed q=%r cat=%r: %s", query, category_ids, e)
            return diag

    def _items_to_rows(self, items: list, limit: int) -> List[Dict]:
        results: List[Dict] = []
        for item in items[:limit]:
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

    def _collect_search_rows(
        self, query: str, *, max_price: Optional[int] = None, limit: int | None = None
    ) -> List[Dict]:
        """Search one or more pages; dedupe by item id."""
        per_page = _ebay_search_limit()
        pages = _ebay_search_pages()
        cap = limit if limit is not None else per_page * pages
        cap = max(1, min(cap, per_page * pages))
        category_ids = _ebay_category_ids()
        seen: set[str] = set()
        rows: List[Dict] = []
        last_diag: dict[str, Any] = {}

        for page_idx in range(pages):
            if len(rows) >= cap:
                break
            need = min(per_page, cap - len(rows))
            offset = page_idx * per_page
            diag = self._search_request(
                query=query,
                limit=need,
                category_ids=category_ids,
                max_price=max_price,
                offset=offset,
            )
            last_diag = diag
            if diag.get("error"):
                break
            chunk = self._items_to_rows(diag.get("items") or [], need)
            for row in chunk:
                eid = row.get("external_listing_id")
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                rows.append(row)
            if len(diag.get("items") or []) < need:
                break

        self.last_search_diagnostic = {k: v for k, v in last_diag.items() if k != "items"}
        self.last_search_diagnostic["pages_fetched"] = min(
            pages, (len(rows) + per_page - 1) // per_page if rows else 0
        )
        self.last_search_diagnostic["collected"] = len(rows)
        return rows[:cap]

    def search_listings(
        self, query: str, max_price: Optional[int] = None, limit: int = 5
    ) -> List[Dict]:
        """Search eBay for listings and return normalized results (empty list on failure)."""
        return self._collect_search_rows(query, max_price=max_price, limit=limit)

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
            response = requests.get(url, headers=headers, params=params, timeout=6)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            logger.info(
                "eBay getItem HTTP %s for %s",
                getattr(e.response, "status_code", "?"),
                item_id,
            )
            return None
        except Exception as e:
            logger.info("eBay getItem failed for %s: %s", item_id, e)
            return None

    def search_listings_enriched(
        self, query: str, max_price: Optional[int] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search then hydrate rows with getItem (capped by EBAY_GET_ITEM_MAX)."""
        summaries = self.search_listings(query=query, max_price=max_price, limit=limit)
        if not summaries:
            return []
        try:
            enrich_max = int(os.getenv("EBAY_GET_ITEM_MAX", "12"))
        except ValueError:
            enrich_max = 12
        if enrich_max <= 0:
            return summaries

        from app.integrations.ebay.parse_item import merge_search_summary

        to_enrich = summaries[:enrich_max]
        tail = summaries[enrich_max:]

        def _enrich(row: Dict[str, Any]) -> Dict[str, Any]:
            item_id = row.get("external_listing_id")
            detail = self.get_item(item_id) if item_id else None
            return merge_search_summary(row, detail)

        enriched: List[Dict[str, Any]] = []
        workers = min(5, max(1, len(to_enrich)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_enrich, row) for row in to_enrich]
            for fut in as_completed(futures):
                try:
                    enriched.append(fut.result())
                except Exception as e:
                    logger.warning("eBay enrich row failed: %s", e)
        enriched.extend(tail)
        return enriched
