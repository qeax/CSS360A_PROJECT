"""Tests for /auth/me profile fields."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.microsoft_oidc import pick_display_name, pick_profile_picture_url
from app.services.user_profile import display_name_from_email, user_profile_payload


def test_pick_display_name_from_name_claim():
    assert pick_display_name({"name": "Jane Doe"}) == "Jane Doe"


def test_pick_display_name_from_given_family():
    claims = {"given_name": "Jane", "family_name": "Doe"}
    assert pick_display_name(claims) == "Jane Doe"


def test_pick_profile_picture_url():
    url = "https://graph.microsoft.com/v1.0/me/photo/$value"
    assert pick_profile_picture_url({"picture": url}) == url


def test_display_name_from_email():
    assert display_name_from_email("dev.user@localhost") == "Dev User"


def test_user_profile_payload_falls_back_to_email_local_part():
    from types import SimpleNamespace

    user = SimpleNamespace(
        id=7,
        email="jane.doe@example.com",
        display_name=None,
        profile_picture_url=None,
    )
    payload = user_profile_payload(user)
    assert payload["display_name"] == "Jane Doe"
    assert payload["profile_picture_url"] is None


def test_auth_me_dev_bypass_includes_profile_fields(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("DEV_AUTH_EMAIL", "dev.user@localhost")
    for key in (
        "AZURE_AD_TENANT_ID",
        "AZURE_AD_CLIENT_ID",
        "AZURE_AD_CLIENT_SECRET",
        "AZURE_AD_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)

    with TestClient(app) as bare_client:
        response = bare_client.get("/auth/me")

    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["email"] == "dev.user@localhost"
    assert data["display_name"] == "Dev User"
    assert "profile_picture_url" in data
    assert data.get("dev_bypass") is True
