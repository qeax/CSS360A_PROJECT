"""Dev auth bypass only when Entra OIDC env is missing."""

import pytest
from fastapi.testclient import TestClient

from app.config import is_azure_ad_configured, is_dev_auth_bypass_enabled
from app.main import app

_AZURE_ENV_KEYS = (
    "AZURE_AD_TENANT_ID",
    "AZURE_AD_CLIENT_ID",
    "AZURE_AD_CLIENT_SECRET",
    "AZURE_AD_REDIRECT_URI",
)


@pytest.fixture
def clear_azure_env(monkeypatch):
    for key in _AZURE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_is_azure_ad_configured_when_all_vars_set(monkeypatch):
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "client-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AZURE_AD_REDIRECT_URI", "http://localhost/api/auth/callback")
    assert is_azure_ad_configured() is True


def test_is_azure_ad_not_configured_when_any_var_missing(monkeypatch, clear_azure_env):
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "tenant-id")
    assert is_azure_ad_configured() is False


def test_dev_bypass_disabled_when_azure_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "client-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AZURE_AD_REDIRECT_URI", "http://localhost/api/auth/callback")
    assert is_dev_auth_bypass_enabled() is False


def test_dev_bypass_enabled_without_azure(monkeypatch, clear_azure_env):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    assert is_dev_auth_bypass_enabled() is True


def test_cars_use_real_auth_when_azure_configured_without_bypass(monkeypatch, clear_azure_env):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("AZURE_AD_TENANT_ID", "tenant-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_ID", "client-id")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "secret")
    monkeypatch.setenv("AZURE_AD_REDIRECT_URI", "http://localhost/api/auth/callback")

    with TestClient(app) as bare_client:
        response = bare_client.get("/cars")

    assert response.status_code == 401
