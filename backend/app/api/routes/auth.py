"""Microsoft Entra ID OAuth2 login, logout, and session introspection."""

from __future__ import annotations

import secrets
from urllib.parse import quote, urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps.auth import ensure_dev_bypass_user
from app.config import (
    get_allowed_email_domain,
    get_azure_ad_client_id,
    get_azure_ad_client_secret,
    get_azure_ad_redirect_uri,
    get_azure_ad_tenant_id,
    is_dev_auth_bypass_enabled,
)
from app.db import get_db
from app.repositories.users import get_user_by_id, upsert_user_by_oid
from app.services.microsoft_oidc import (
    decode_and_validate_id_token,
    exchange_code_for_tokens,
    pick_email_claim,
)

router = APIRouter(tags=["auth"])


def _authorize_base_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"


def _login_redirect_url(error_code: str) -> str:
    return f"/login.html?error={quote(error_code)}"


def _email_domain_allowed(email: str, domain: str | None) -> bool:
    if not domain:
        return True
    suffix = "@" + domain.lower().strip()
    return email.lower().endswith(suffix)


@router.get("/auth/login")
def login(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    if is_dev_auth_bypass_enabled():
        user = ensure_dev_bypass_user(db)
        request.session["user_id"] = user.id
        request.session["email"] = user.email
        return RedirectResponse(url="/index.html", status_code=302)

    tenant_id = get_azure_ad_tenant_id()
    client_id = get_azure_ad_client_id()
    redirect_uri = get_azure_ad_redirect_uri()
    if not tenant_id or not client_id or not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="authentication_is_not_configured",
        )

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": "openid profile email",
        "state": state,
    }
    url = _authorize_base_url(tenant_id) + "?" + urlencode(params)
    return RedirectResponse(url=url, status_code=302)


@router.get("/auth/callback")
def auth_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    if error:
        # OAuth error from IdP (user cancelled, policy, etc.)
        return RedirectResponse(
            url=_login_redirect_url("oauth_error"),
            status_code=302,
        )

    tenant_id = get_azure_ad_tenant_id()
    client_id = get_azure_ad_client_id()
    client_secret = get_azure_ad_client_secret()
    redirect_uri = get_azure_ad_redirect_uri()

    if not all([tenant_id, client_id, client_secret, redirect_uri, code, state]):
        return RedirectResponse(url=_login_redirect_url("invalid_request"), status_code=302)

    expected = request.session.pop("oauth_state", None)
    if not expected or state != expected:
        return RedirectResponse(url=_login_redirect_url("invalid_state"), status_code=302)

    try:
        tokens = exchange_code_for_tokens(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )
        id_token = tokens.get("id_token")
        if not id_token:
            return RedirectResponse(url=_login_redirect_url("no_id_token"), status_code=302)

        claims = decode_and_validate_id_token(
            tenant_id=tenant_id,
            client_id=client_id,
            id_token=id_token,
        )

        token_tid = claims.get("tid")
        if token_tid and str(token_tid).lower() != str(tenant_id).lower():
            return RedirectResponse(url=_login_redirect_url("wrong_tenant"), status_code=302)

        email = pick_email_claim(claims)
        sub = claims.get("sub")
        if not email or not sub:
            return RedirectResponse(url=_login_redirect_url("missing_identity"), status_code=302)

        allowed_domain = get_allowed_email_domain()
        if not _email_domain_allowed(email, allowed_domain):
            return RedirectResponse(url=_login_redirect_url("email_not_allowed"), status_code=302)

        user = upsert_user_by_oid(db, azure_oid=str(sub), email=email)
        request.session["user_id"] = user.id
        request.session["email"] = user.email

        return RedirectResponse(url="/index.html", status_code=302)
    except (httpx.HTTPError, jwt.exceptions.PyJWTError, KeyError, ValueError):
        return RedirectResponse(url=_login_redirect_url("sign_in_failed"), status_code=302)


@router.get("/auth/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login.html", status_code=302)


@router.get("/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    if is_dev_auth_bypass_enabled():
        user = ensure_dev_bypass_user(db)
        request.session["user_id"] = user.id
        request.session["email"] = user.email
        return {
            "authenticated": True,
            "email": user.email,
            "user_id": user.id,
            "dev_bypass": True,
        }

    uid = request.session.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user = get_user_by_id(db, int(uid))
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="not_authenticated")
    return {
        "authenticated": True,
        "email": user.email,
        "user_id": user.id,
    }
