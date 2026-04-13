"""Database connection, schema, and initialization."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _hours_ago_iso(hours: int = 48) -> str:
    """Return ISO 8601 timestamp for N hours ago in UTC."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


@contextmanager
def get_connection(db_path: Path):
    """Get a database connection with proper configuration.

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        A sqlite3 connection object with foreign keys and WAL mode enabled.
    """
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA busy_timeout = 5000")
        yield db
    finally:
        db.close()


CREATE_FEEDS_TABLE = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    description TEXT,
    last_fetched_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
)
"""

CREATE_FETCHES_TABLE = """
CREATE TABLE IF NOT EXISTS fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    feeds_fetched INTEGER DEFAULT 0,
    articles_found INTEGER DEFAULT 0
)
"""

CREATE_ARTICLES_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_id INTEGER NOT NULL,
    feed_id INTEGER NOT NULL,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    summary TEXT,
    content TEXT,
    author TEXT,
    published_at DATETIME,
    parsed_at DATETIME,
    sentiment TEXT,
    categories TEXT,
    tags TEXT,
    download_failed INTEGER NOT NULL DEFAULT 0,
    download_error TEXT,
    parse_failed INTEGER NOT NULL DEFAULT 0,
    parse_error TEXT,
    countries TEXT,
    fact_check_status TEXT,
    fact_check_result TEXT,
    fact_checked_at DATETIME,
    processing_status TEXT,
    processing_owner TEXT,
    processing_started_at DATETIME,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (fetch_id) REFERENCES fetches(id),
    FOREIGN KEY (feed_id) REFERENCES feeds(id)
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)",
    "CREATE INDEX IF NOT EXISTS idx_articles_fetch_id ON articles(fetch_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_download_failed "
        "ON articles(download_failed)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_parse_failed "
        "ON articles(parse_failed)"
    ),
    # NEW — critical for 48h queries
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_published_at "
        "ON articles(published_at)"
    ),
    ("CREATE INDEX IF NOT EXISTS idx_articles_created_at " "ON articles(created_at)"),
    ("CREATE INDEX IF NOT EXISTS idx_articles_sentiment " "ON articles(sentiment)"),
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_fact_check_status "
        "ON articles(fact_check_status)"
    ),
    ("CREATE INDEX IF NOT EXISTS idx_articles_is_featured " "ON articles(is_featured)"),
    ("CREATE INDEX IF NOT EXISTS idx_articles_is_breaking " "ON articles(is_breaking)"),
    ("CREATE INDEX IF NOT EXISTS idx_articles_parsed_at " "ON articles(parsed_at)"),
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_processing "
        "ON articles(processing_status, processing_started_at)"
    ),
    # Partial index for unparsed articles ready for parsing
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_unparsed "
        "ON articles(created_at ASC) "
        "WHERE content IS NOT NULL AND parsed_at IS NULL AND parse_failed = 0"
    ),
    # Partial index for empty articles needing download
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_empty "
        "ON articles(created_at ASC) "
        "WHERE content IS NULL AND download_failed = 0"
    ),
    # Composite index for the most common website query
    (
        "CREATE INDEX IF NOT EXISTS idx_articles_48h "
        "ON articles(created_at DESC, published_at DESC)"
    ),
]


# Migrations for existing databases that lack newer columns.
_MIGRATIONS = [
    # --- existing ---
    "ALTER TABLE articles ADD COLUMN fact_check_status TEXT",
    "ALTER TABLE articles ADD COLUMN fact_check_result TEXT",
    "ALTER TABLE articles ADD COLUMN fact_checked_at DATETIME",
    "ALTER TABLE articles ADD COLUMN processing_status TEXT",
    "ALTER TABLE articles ADD COLUMN processing_owner TEXT",
    "ALTER TABLE articles ADD COLUMN processing_started_at DATETIME",
    # --- NEW — media ---
    "ALTER TABLE articles ADD COLUMN image_url TEXT",
    "ALTER TABLE feeds ADD COLUMN icon_url TEXT",
    "ALTER TABLE feeds ADD COLUMN favicon_url TEXT",
    # --- NEW — editorial ---
    ("ALTER TABLE articles ADD COLUMN view_count " "INTEGER NOT NULL DEFAULT 0"),
    ("ALTER TABLE articles ADD COLUMN is_featured " "INTEGER NOT NULL DEFAULT 0"),
    ("ALTER TABLE articles ADD COLUMN is_breaking " "INTEGER NOT NULL DEFAULT 0"),
    # --- NEW — denormalized source ---
    "ALTER TABLE articles ADD COLUMN source_name TEXT",
    # --- NEW — language ---
    "ALTER TABLE articles ADD COLUMN language TEXT DEFAULT 'en'",
    "ALTER TABLE feeds ADD COLUMN language TEXT DEFAULT 'en'",
    # --- NEW — feed category ---
    "ALTER TABLE feeds ADD COLUMN category TEXT",
]

# FTS5 virtual table for full-text search
CREATE_ARTICLES_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title,
    summary,
    content,
    tags,
    categories,
    content=articles,
    content_rowid=id
)
"""

# Triggers to keep FTS in sync
CREATE_ARTICLES_FTS_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS articles_fts_insert
    AFTER INSERT ON articles BEGIN
        INSERT INTO articles_fts(
            rowid, title, summary, content, tags, categories
        ) VALUES (
            new.id, new.title, new.summary,
            new.content, new.tags, new.categories
        );
    END""",
    """CREATE TRIGGER IF NOT EXISTS articles_fts_delete
    AFTER DELETE ON articles BEGIN
        INSERT INTO articles_fts(
            articles_fts, rowid, title, summary,
            content, tags, categories
        ) VALUES (
            'delete', old.id, old.title, old.summary,
            old.content, old.tags, old.categories
        );
    END""",
    """CREATE TRIGGER IF NOT EXISTS articles_fts_update
    AFTER UPDATE ON articles BEGIN
        INSERT INTO articles_fts(
            articles_fts, rowid, title, summary,
            content, tags, categories
        ) VALUES (
            'delete', old.id, old.title, old.summary,
            old.content, old.tags, old.categories
        );
        INSERT INTO articles_fts(
            rowid, title, summary, content, tags, categories
        ) VALUES (
            new.id, new.title, new.summary,
            new.content, new.tags, new.categories
        );
    END""",
]

_VALID_PROCESSING_ACTIONS = {"download", "parse", "fact_check"}
_CLAIM_TIMEOUT_MINUTES = 30


def _claim_cutoff(minutes: int = _CLAIM_TIMEOUT_MINUTES) -> str:
    """Return the cutoff timestamp for stale processing claims."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def init_database(db_path: Path) -> None:
    """Initialize the database with required tables and indexes.

    Also applies any pending migrations for existing databases.

    Args:
        db_path: Path to the SQLite database file.
    """
    with get_connection(db_path) as db:
        db.execute(CREATE_FEEDS_TABLE)
        db.execute(CREATE_FETCHES_TABLE)
        db.execute(CREATE_ARTICLES_TABLE)
        # Apply migrations first so new columns exist before indexing
        for migration in _MIGRATIONS:
            try:
                db.execute(migration)
            except sqlite3.OperationalError:
                pass  # Column already exists
        for index_sql in CREATE_INDEXES:
            db.execute(index_sql)
        # Create FTS5 virtual table and sync triggers
        db.execute(CREATE_ARTICLES_FTS_TABLE)
        for trigger_sql in CREATE_ARTICLES_FTS_TRIGGERS:
            db.execute(trigger_sql)
        db.commit()
