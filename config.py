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

    @classmethod
    def path(cls) -> Path:
        p = cls.root
        p.mkdir(parents=True, exist_ok=True)
        return p


# Path constants derived from DataDir.root
FILES_DIR = DataDir.root / "files"
LOGS_DIR = DataDir.root / "logs"
PLANS_DIR = DataDir.root / "plans"
MONITOR_DIR = DataDir.root / "monitor"
METRICS_DIR = DataDir.root / "metrics"
CACHE_DIR = DataDir.root / "cache"
STATE_FILE = DataDir.root / "orchestrator.json"
HEARTBEAT_FILE = DataDir.root / "orchestrator.heartbeat"
PID_FILE = DataDir.root / "orchestrator.pid"
LESSONS_FILE = DataDir.root / "lessons.json"


class Database:
    path: Path = Path(getenv("DATABASE_PATH", str(DataDir.root / "news48.db")))


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
