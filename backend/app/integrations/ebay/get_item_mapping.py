"""
Maps eBay Browse API `getItem` JSON paths to our persistence layer.

Canonical payload stays in `cars.raw_listing_json`. Normalized columns and child
rows exist for querying, indexing, and UI without parsing JSON on every read.

References:
https://developer.ebay.com/api-docs/buy/browse/resources/item/methods/getItem
"""

from __future__ import annotations

# Root-level fields → cars.* columns (extract in EbayListingClient / sync job).
ROOT_COLUMN_TARGETS: dict[str, str] = {
    "itemId": "external_listing_id",
    "itemWebUrl": "listing_url",
    "bidCount": "bid_count",
    "itemEndDate": "listing_ends_at",  # parse ISO8601 → timezone-aware UTC
    "sellerItemRevision": "seller_item_revision",
    "shortDescription": "description_summary",
    "description": "description_full",
    # Buying format / listing type — normalize to listing_format (e.g. AUCTION, FIXED_PRICE).
    "buyingOptions": "listing_format",
}

# `fieldgroups=PRODUCT` / default payload helpers for core vehicle facets already on Car.
ASPECT_NAME_HINTS: dict[str, str] = {
    # Localized aspect "name" (locale-dependent) → cars column when unambiguous.
    "Make": "brand",
    "Model": "model",
    "Year": "year",
}

# itemLocation → car_locations row (one row per car when syncing).
ITEM_LOCATION_KEYS: tuple[str, ...] = (
    "country",
    "stateOrProvince",
    "city",
    "postalCode",
)

# estimatedAvailabilities[].deliveryOptions → car_listing_terms flags + delivery_options_raw JSON.
DELIVERY_OPTION_FLAGS: dict[str, tuple[str, ...]] = {
    "ship_to_home": ("SHIP_TO_HOME",),
    "local_pickup": ("SELLER_ARRANGED_LOCAL_PICKUP", "PICKUP_DROP_OFF"),
    "in_store_pickup": ("IN_STORE_PICKUP",),
}

# seller container → external_sellers row; link cars.seller_id.
SELLER_JSON_KEYS: tuple[str, ...] = (
    "username",
    "sellerAccountType",
)

# Prefer separate fieldgroups=ADDITIONAL_SELLER_DETAILS for stable seller user id when available.
SELLER_EXTERNAL_ID_KEYS: tuple[str, ...] = ("sellerUserId", "username")

# Full localizedAspects array → vehicle_aspect_snapshots.aspects_json (optional history).
ASPECTS_SNAPSHOT_SOURCE_KEY = "localizedAspects"

# Image gallery → car_media rows (image.imageUrl primary, then additionalImages[]).
PRIMARY_IMAGE_KEY = "image"
ADDITIONAL_IMAGES_KEY = "additionalImages"

# Leave inside raw_listing_json only (large / rare / debugging), not dedicated columns:
RAW_ONLY_HINTS: frozenset[str] = frozenset(
    {
        "shippingOptions",
        "returnPolicies",
        "sellerLegalInfo",
        "sellerCustomPolicies",
        "taxes",
        "localizedAspects",  # duplicated into aspects_json snapshot when syncing
        "qualifiedPrograms",
        "marketingPrice",
    }
)
