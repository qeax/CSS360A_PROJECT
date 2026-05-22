"""Store and serve Microsoft Graph profile photos."""

from __future__ import annotations

import base64
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STORE_PREFIX = "store:"
_DATA_URL_RE = re.compile(r"^data:(image/[^;]+);base64,(.+)$", re.DOTALL)

_GRAPH_PHOTO_PATHS = (
    "/v1.0/me/photos/96x96/$value",
    "/v1.0/me/photos/48x48/$value",
    "/v1.0/me/photo/$value",
)


def pack_profile_photo(content: bytes, content_type: str = "image/jpeg") -> str:
    """Persist photo in ``users.profile_picture_url`` (MEDIUMTEXT-safe)."""
    ctype = (content_type or "image/jpeg").split(";")[0].strip()
    if not ctype.startswith("image/"):
        ctype = "image/jpeg"
    encoded = base64.b64encode(content).decode("ascii")
    return f"{STORE_PREFIX}{ctype}:{encoded}"


def load_profile_photo_bytes(stored: str | None) -> tuple[bytes, str] | None:
    """Decode stored photo bytes for ``GET /auth/avatar``."""
    if not stored or not isinstance(stored, str):
        return None
    value = stored.strip()
    if not value:
        return None

    if value.startswith(STORE_PREFIX):
        payload = value[len(STORE_PREFIX) :]
        ctype, sep, b64 = payload.partition(":")
        if not sep or not b64:
            return None
        try:
            return base64.b64decode(b64, validate=True), ctype
        except (ValueError, TypeError):
            return None

    match = _DATA_URL_RE.match(value)
    if match:
        try:
            return base64.b64decode(match.group(2), validate=True), match.group(1)
        except (ValueError, TypeError):
            return None

    return None


def has_stored_profile_photo(stored: str | None) -> bool:
    return load_profile_photo_bytes(stored) is not None


def avatar_public_path() -> str:
    return "/api/auth/avatar"


def fetch_profile_photo_from_graph(access_token: str) -> Optional[str]:
    """Download photo from Graph and return packed storage string."""
    token = (access_token or "").strip()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=15.0) as client:
        for path in _GRAPH_PHOTO_PATHS:
            url = f"https://graph.microsoft.com{path}"
            try:
                response = client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("Graph photo request failed for %s: %s", path, exc)
                continue
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                logger.warning(
                    "Graph photo %s returned HTTP %s (check User.Read consent)",
                    path,
                    response.status_code,
                )
                continue
            content_type = (
                (response.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            )
            if not response.content:
                continue
            logger.info(
                "Graph profile photo loaded from %s (%s bytes)", path, len(response.content)
            )
            return pack_profile_photo(response.content, content_type)
    return None
