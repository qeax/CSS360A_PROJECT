from sqlalchemy.orm import Session

from app.models.user import User


def upsert_user_by_oid(db: Session, azure_oid: str, email: str) -> User:
    """Create or update a user row keyed by Entra object id (JWT ``sub``)."""
    normalized_email = email.strip().lower()
    existing = db.query(User).filter(User.azure_oid == azure_oid).one_or_none()
    if existing:
        if existing.email != normalized_email:
            existing.email = normalized_email
        db.commit()
        db.refresh(existing)
        return existing

    user = User(azure_oid=azure_oid, email=normalized_email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).one_or_none()
