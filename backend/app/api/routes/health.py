from fastapi import APIRouter
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    database_connected = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            database_connected = True
    except Exception:
        database_connected = False

    return {
        "status": "ok",
        "service": "CSS360 Backend",
        "database_connected": database_connected,
    }
