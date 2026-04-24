from os import getenv
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _get_required_env(key: str, cast: type = str) -> Any:
    value = getenv(key, None)
    if value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return cast(value)


class DataDir:
    """Root directory for all runtime data files."""

    root: Path = Path(getenv("DATA_DIR", "data"))


# Path constants derived from DataDir.root
FILES_DIR = DataDir.root / "files"
PLANS_DIR = DataDir.root / "plans"
MONITOR_DIR = DataDir.root / "monitor"
CACHE_DIR = DataDir.root / "cache"
LESSONS_FILE = DataDir.root / "lessons.json"


class Database:
    url: str = getenv(
        "DATABASE_URL",
        "mysql+mysqlconnector://news48:news48@localhost:3306/news48",
    )


class Services:
    @classmethod
    def byparr(cls) -> str:
        """Lazy access to BYPARR_API_URL so web container
        doesn't crash on import."""
        return _get_required_env("BYPARR_API_URL", str)


class Web:
    """Web server configuration."""

    host: str = getenv("WEB_HOST", "0.0.0.0")

    @classmethod
    def get_port(cls) -> int:
        """Parse WEB_PORT safely, falling back to 8000 on bad input."""
        try:
            return int(getenv("WEB_PORT", "8000"))
        except (ValueError, TypeError):
            return 8000


class Redis:
    """Redis configuration for Dramatiq."""

    url: str = getenv("REDIS_URL", "redis://localhost:6379/0")
