from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import DEV_AUTH_AZURE_OID, get_dev_auth_email, is_dev_auth_bypass_enabled
from app.db import get_db
from app.models.user import User
from app.repositories.users import get_user_by_id, upsert_user_by_oid


def ensure_dev_bypass_user(db: Session) -> User:
    """Stable local dev user (no Microsoft Entra)."""
    return upsert_user_by_oid(
        db,
        azure_oid=DEV_AUTH_AZURE_OID,
        email=get_dev_auth_email(),
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    if is_dev_auth_bypass_enabled():
        uid = request.session.get("user_id")
        if uid is not None:
            user = get_user_by_id(db, int(uid))
            if user is not None:
                return user
        user = ensure_dev_bypass_user(db)
        request.session["user_id"] = user.id
        request.session["email"] = user.email
        return user

    uid = request.session.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user = get_user_by_id(db, int(uid))
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="session_invalid")
    return user
