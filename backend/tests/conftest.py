"""Pytest configuration for backend tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import create_database_engine, get_db
from app.core.config import get_settings
import app.models as model_registry  # noqa: F401 - registers model metadata for test schema creation


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_session_factory():
    engine = create_database_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        # This is a disposable in-memory database; closing it avoids SQLite's
        # refusal to DROP a self-referencing table while FK enforcement is on.
        engine.dispose()


@pytest.fixture
def auth_client(monkeypatch, test_session_factory):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-signing-key-never-use-outside-tests-123456")
    get_settings.cache_clear()

    def override_get_db():
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
