"""Database connection, session factory, and ORM base class."""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    def to_dict(self) -> dict:
        """Convert model instance to a plain dict."""
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}


def _get_database_url() -> str:
    """Read DATABASE_URL from environment with a sensible default."""
    return os.getenv(
        "DATABASE_URL",
        "mysql+mysqlconnector://news48:news48@localhost:3306/news48",
    )


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _hours_ago_iso(hours: int = 48) -> str:
    """Return ISO 8601 timestamp for N hours ago in UTC."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


# Module-level engine and session factory
_database_url = _get_database_url()
_is_sqlite = _database_url.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        _database_url,
        echo=False,
    )
else:
    engine = create_engine(
        _database_url,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
    )

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Get a new database session. Caller is responsible for closing."""
    return SessionLocal()
