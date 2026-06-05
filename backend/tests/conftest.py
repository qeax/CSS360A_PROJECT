"""Pytest fixtures: isolated SQLite DB, auth override, and FastAPI test client."""

from __future__ import annotations

import os
from collections.abc import Generator
from types import SimpleNamespace

# Must be set before ``app.db`` is first imported (single in-memory DB for all connections).
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db as db_module
import app.models  # noqa: F401 — register ORM tables on Base
from app.api.deps.auth import get_current_user
from app.db import Base, get_db
from app.demo_seed import insert_generated_demo_cars
from app.main import app
from app.models.car import Car
from app.repositories.cars import invalidate_in_memory_demo_cache

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_test_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

db_module.engine = _test_engine
db_module.SessionLocal = _test_session_factory


def clear_inventory(db: Session) -> None:
    """Remove all rows from every table (no re-seed)."""
    from sqlalchemy import delete

    for table in reversed(Base.metadata.sorted_tables):
        db.execute(delete(table))
    db.commit()
    invalidate_in_memory_demo_cache()


def reset_demo_inventory(db: Session) -> None:
    """Clear all tables and re-insert deterministic demo cars (for tests that empty inventory)."""
    clear_inventory(db)
    insert_generated_demo_cars(db, count=30)
    db.commit()
    invalidate_in_memory_demo_cache()


def _ensure_schema_and_seed() -> None:
    Base.metadata.create_all(bind=_test_engine)
    with _test_session_factory() as db:
        if db.scalar(select(func.count()).select_from(Car)) == 0:
            insert_generated_demo_cars(db, count=30)
            db.commit()
    invalidate_in_memory_demo_cache()


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> Generator[None, None, None]:
    _ensure_schema_and_seed()
    yield


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = _test_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """API client with auth bypassed and a shared DB session per test."""

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    def _fake_user():
        return SimpleNamespace(id=1, email="ci@example.test", azure_oid="ci-test-oid")

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
