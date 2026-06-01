"""Normalize user search text and tokenize for DB relevance matching."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Generic terms that should not alone match unrelated inventory.
_SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "for",
        "and",
        "or",
        "of",
        "in",
        "on",
        "to",
        "car",
        "cars",
        "vehicle",
        "vehicles",
        "auto",
        "automotive",
        "automobile",
        "used",
        "sale",
        "buy",
        "listing",
        "ebay",
    }
)


def normalize_search_key(q: Optional[str]) -> Optional[str]:
    """Stable key for cache + ingest tagging (lowercase, collapsed whitespace)."""
    if not q or not isinstance(q, str):
        return None
    qn = unicodedata.normalize("NFKC", q).strip().lower()
    qn = re.sub(r"\s+", " ", qn)
    return qn[:128] if qn else None


def split_query_tokens(q: Optional[str]) -> list[str]:
    if not q or not isinstance(q, str):
        return []
    qn = unicodedata.normalize("NFKC", q).strip().lower()
    if not qn:
        return []
    return [t for t in re.split(r"\s+", qn) if t]


def meaningful_query_tokens(q: Optional[str]) -> list[str]:
    """Tokens used for relevance; drops generic vehicle words like 'cars'."""
    raw = split_query_tokens(q)
    meaningful = [t for t in raw if t not in _SEARCH_STOPWORDS and len(t) > 1]
    return meaningful if meaningful else raw
