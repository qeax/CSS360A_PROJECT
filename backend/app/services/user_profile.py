"""Helpers for user display fields."""

from __future__ import annotations


def display_name_from_email(email: str) -> str:
    local = (email or "").split("@", 1)[0].strip()
    if not local:
        return "User"
    return local.replace(".", " ").replace("_", " ").title()


def user_profile_payload(user) -> dict:
    email = user.email or ""
    display_name = (user.display_name or "").strip() or display_name_from_email(email)
    return {
        "authenticated": True,
        "email": email,
        "user_id": user.id,
        "display_name": display_name,
        "profile_picture_url": user.profile_picture_url or None,
    }
