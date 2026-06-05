"""Microsoft Entra ID (Azure AD) OAuth2 / OIDC helpers."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx
import jwt
from jwt import PyJWKClient

from app.services.profile_photo import fetch_profile_photo_from_graph

_oidc_cache: dict[str, Any] = {}
_oidc_cache_ts: float = 0.0
_OIDC_CACHE_TTL_SEC = 3600

_jwk_clients: dict[str, PyJWKClient] = {}

logger = logging.getLogger(__name__)

# Delegated scope for the signed-in user's own profile photo (Graph).
GRAPH_LOGIN_SCOPES = "openid profile email User.Read"


def _discovery_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"


def get_oidc_metadata(tenant_id: str) -> dict[str, Any]:
    global _oidc_cache, _oidc_cache_ts
    now = time.time()
    if _oidc_cache.get("tenant") == tenant_id and now - _oidc_cache_ts < _OIDC_CACHE_TTL_SEC:
        return _oidc_cache["data"]

    url = _discovery_url(tenant_id)
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()

    _oidc_cache = {"tenant": tenant_id, "data": data}
    _oidc_cache_ts = now
    return data


def get_jwks_client(jwks_uri: str) -> PyJWKClient:
    if jwks_uri not in _jwk_clients:
        _jwk_clients[jwks_uri] = PyJWKClient(jwks_uri, cache_keys=True)
    return _jwk_clients[jwks_uri]


def exchange_code_for_tokens(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    meta = get_oidc_metadata(tenant_id)
    token_url = meta["token_endpoint"]
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": GRAPH_LOGIN_SCOPES,
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        return r.json()


def decode_and_validate_id_token(
    tenant_id: str,
    client_id: str,
    id_token: str,
) -> dict[str, Any]:
    meta = get_oidc_metadata(tenant_id)
    issuer = meta["issuer"]
    jwks_uri = meta["jwks_uri"]

    jwks_client = get_jwks_client(jwks_uri)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)

    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=issuer,
        options={"require": ["exp", "sub", "aud", "iss"]},
    )
    return claims


def pick_email_claim(claims: dict[str, Any]) -> Optional[str]:
    email = claims.get("email") or claims.get("preferred_username")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def pick_display_name(claims: dict[str, Any]) -> Optional[str]:
    name = claims.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    given = claims.get("given_name")
    family = claims.get("family_name")
    parts = [p.strip() for p in (given, family) if isinstance(p, str) and p.strip()]
    if parts:
        return " ".join(parts)
    return None


def pick_profile_picture_url(claims: dict[str, Any]) -> Optional[str]:
    """Id token rarely includes ``picture`` for Entra; prefer Graph at login."""
    picture = claims.get("picture")
    if isinstance(picture, str) and picture.strip():
        return picture.strip()
    return None


def resolve_profile_picture_url(
    claims: dict[str, Any],
    tokens: dict[str, Any],
) -> Optional[str]:
    """Prefer Graph photo (packed storage); fall back to a ``picture`` claim if present."""
    access_token = tokens.get("access_token")
    if isinstance(access_token, str) and access_token.strip():
        graph_photo = fetch_profile_photo_from_graph(access_token)
        if graph_photo:
            return graph_photo
    else:
        logger.warning("OAuth token response missing access_token; cannot load Graph photo")
    from_token = pick_profile_picture_url(claims)
    if from_token:
        return from_token
    return None
