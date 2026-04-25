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
import news48.core.database.models  # noqa: F401, E402
from news48.core.database import connection as db_connection  # noqa: E402


def _patch_database_modules(test_engine):
    """Replace SessionLocal in all database modules."""
    test_session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    db_connection.SessionLocal = test_session_factory

    from news48.core.database import articles, claims, feeds, fetches, retention
    from news48.core.database.articles import (
        _browsing,
        _claims,
        _mutations,
        _queries,
        _stats,
    )

    for mod in (
        articles,
        claims,
        fetches,
        feeds,
        retention,
        _browsing,
        _claims,
        _mutations,
        _queries,
        _stats,
    ):
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


@pytest.fixture
def planner_db(tmp_path, monkeypatch):
    """Provide a fresh temp SQLite DB for planner tests.

    - Redirects PLANS_DB to a temp directory
    - Closes any existing connection before the test
    - Resets the connection cache after the test
    - Temp files are automatically cleaned up by pytest's tmp_path
    """
    from news48.core import config
    from news48.core.agents.tools.planner._db import _close_conn

    # Close any existing connection first
    _close_conn()

    # Redirect to temp DB
    db_path = tmp_path / "test_plans.db"
    monkeypatch.setattr(config, "PLANS_DB", db_path)

    yield db_path

    # Close connection so temp files can be deleted
    _close_conn()
