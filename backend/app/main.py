from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, cars, health
from app.config import (
    get_auth_session_secret,
    get_cors_origins,
    is_production,
    require_auth_env_at_startup,
)

require_auth_env_at_startup()

_docs_disabled = is_production()
app = FastAPI(
    title="CSS360 Car Flip Analyzer",
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
)

_session_secret = get_auth_session_secret() or "dev-only-insecure-session-secret"
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="session",
    max_age=14 * 24 * 3600,
    same_site="lax",
    https_only=is_production(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Traefik strips `/api`; browsers call `/api/cars` and `/api/auth/*`. Register routes once at canonical paths.
app.include_router(auth.router)
app.include_router(cars.router)
app.include_router(cars.router, prefix="/api")
app.include_router(health.router)
app.include_router(health.router, prefix="/api")
