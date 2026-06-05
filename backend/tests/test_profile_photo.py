"""Profile photo storage and avatar endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.profile_photo import (
    avatar_public_path,
    fetch_profile_photo_from_graph,
    load_profile_photo_bytes,
    pack_profile_photo,
)
from app.services.user_profile import user_profile_payload


def test_pack_and_load_roundtrip():
    raw = b"\xff\xd8\xff\xe0"
    stored = pack_profile_photo(raw, "image/jpeg")
    loaded = load_profile_photo_bytes(stored)
    assert loaded is not None
    assert loaded[0] == raw
    assert loaded[1] == "image/jpeg"


def test_user_profile_payload_exposes_avatar_endpoint():
    stored = pack_profile_photo(b"abc", "image/png")
    user = SimpleNamespace(
        id=1,
        email="u@example.com",
        display_name="User",
        profile_picture_url=stored,
    )
    payload = user_profile_payload(user)
    assert payload["profile_picture_url"] == avatar_public_path()


@patch("app.services.profile_photo.httpx.Client")
def test_fetch_profile_photo_from_graph(mock_client_cls):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.content = b"\xff\xd8\xff"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_response
    mock_client_cls.return_value = mock_client

    stored = fetch_profile_photo_from_graph("token")
    assert stored is not None
    assert stored.startswith("store:image/jpeg:")
    assert load_profile_photo_bytes(stored) is not None


def test_auth_avatar_requires_session():
    with TestClient(app) as client:
        response = client.get("/auth/avatar")
    assert response.status_code == 401
