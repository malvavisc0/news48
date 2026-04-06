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


class Database:
    path: Path = Path(_get_required_env("DATABASE_PATH", Path))


class Services:
    byparr: str = _get_required_env("BYPARR_API_URL", str)
