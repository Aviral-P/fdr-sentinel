"""SQLAlchemy engine and request-scoped session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with SQLite-specific options when needed."""
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        engine_options: dict[str, object] = {"connect_args": connect_args}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options["poolclass"] = StaticPool
        engine = create_engine(database_url, **engine_options)

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


engine = create_database_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session per request and always close it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
