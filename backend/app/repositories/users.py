from sqlalchemy.orm import Session

from app.models.user import User
from app.services.user_profile import display_name_from_email


def upsert_user_by_oid(
    db: Session,
    azure_oid: str,
    email: str,
    *,
    display_name: str | None = None,
    profile_picture_url: str | None = None,
) -> User:
    """Create or update a user row keyed by Entra object id (JWT ``sub``)."""
    normalized_email = email.strip().lower()
    resolved_name = (display_name or "").strip() or display_name_from_email(normalized_email)
    picture = (profile_picture_url or "").strip() or None

    existing = db.query(User).filter(User.azure_oid == azure_oid).one_or_none()
    if existing:
        if existing.email != normalized_email:
            existing.email = normalized_email
        existing.display_name = resolved_name
        if picture is not None:
            existing.profile_picture_url = picture
        db.commit()
        db.refresh(existing)
        return existing

    user = User(
        azure_oid=azure_oid,
        email=normalized_email,
        display_name=resolved_name,
        profile_picture_url=picture,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).one_or_none()
