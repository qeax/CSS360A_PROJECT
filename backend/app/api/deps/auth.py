from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.repositories.users import get_user_by_id


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    uid = request.session.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user = get_user_by_id(db, int(uid))
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="session_invalid")
    return user
