"""Microsoft Graph profile photo fetch at login."""

from unittest.mock import patch

from app.services.microsoft_oidc import GRAPH_LOGIN_SCOPES, resolve_profile_picture_url
from app.services.profile_photo import pack_profile_photo


def test_graph_login_scopes_include_user_read():
    assert "User.Read" in GRAPH_LOGIN_SCOPES


@patch("app.services.microsoft_oidc.fetch_profile_photo_from_graph")
def test_resolve_profile_picture_prefers_graph(mock_fetch):
    mock_fetch.return_value = pack_profile_photo(b"img", "image/jpeg")
    claims = {"picture": "https://legacy.example/photo.jpg"}
    tokens = {"access_token": "tok"}

    result = resolve_profile_picture_url(claims, tokens)
    assert result is not None
    assert result.startswith("store:")
    mock_fetch.assert_called_once_with("tok")


@patch("app.services.microsoft_oidc.fetch_profile_photo_from_graph")
def test_resolve_profile_picture_falls_back_to_claim(mock_fetch):
    mock_fetch.return_value = None
    claims = {"picture": "https://legacy.example/photo.jpg"}
    tokens = {"access_token": "tok"}

    assert resolve_profile_picture_url(claims, tokens) == "https://legacy.example/photo.jpg"
