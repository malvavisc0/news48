"""Test configuration for SQLite-based tests.

All tests run against an in-memory SQLite database. Each test gets a
fresh database that is discarded after the test completes.
"""

import os

# Override DATABASE_URL before any database module is imported.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# Import all models so they are registered on Base.metadata
import database.models  # noqa: F401, E402
from database import connection as db_connection  # noqa: E402


def _patch_database_modules(test_engine):
    """Replace SessionLocal in all database modules."""
    test_session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    db_connection.SessionLocal = test_session_factory

    from database import articles, claims, feeds, fetches, retention

    for mod in (articles, claims, fetches, feeds, retention):
        mod.SessionLocal = test_session_factory  # type: ignore[attr-defined]


@pytest.fixture
def engine():
    """Provide a fresh database engine for each test."""
    test_engine = create_engine("sqlite:///:memory:")
    db_connection.Base.metadata.create_all(test_engine)
    _patch_database_modules(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine):
    """Provide a database session for each test.

    The session is committed normally. The entire database is
    discarded after the test since each test gets a fresh engine.
    """
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
