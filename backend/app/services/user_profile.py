"""Helpers for user display fields."""

from __future__ import annotations

from app.services.notifications import unread_count
from app.services.profile_photo import avatar_public_path, has_stored_profile_photo


def display_name_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0].strip()
    if not local:
        return "User"
    return local.replace(".", " ").replace("_", " ").title()


def user_profile_payload(user, db=None) -> dict:
    email = user.email or ""
    display_name = (user.display_name or "").strip() or display_name_from_email(email)
    picture_url = None
    if has_stored_profile_photo(user.profile_picture_url):
        picture_url = avatar_public_path()

    payload = {
        "authenticated": True,
        "email": email,
        "user_id": user.id,
        "display_name": display_name,
        "profile_picture_url": picture_url,
    }
    if db is not None:
        try:
            payload["notifications_unread_count"] = unread_count(db, int(user.id))
        except Exception:
            payload["notifications_unread_count"] = 0
    return payload
