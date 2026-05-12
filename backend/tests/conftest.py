"""Pytest fixtures: auth override and shared FastAPI test client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.deps.auth import get_current_user
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """API client with authentication bypassed for routes that depend on ``get_current_user``."""

    def _fake_user():
        return SimpleNamespace(id=1, email="ci@example.test", azure_oid="ci-test-oid")

    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
