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


def _get_optional_env(key: str, cast: type = str) -> Any | None:
    """Get an optional environment variable, returning None if not set."""
    value = getenv(key, None)
    if value is None:
        return None
    return cast(value)


class _LazyEnv:
    """Descriptor that defers env-var lookup until first attribute access."""

    def __init__(self, key: str, cast: type = str, required: bool = True):
        self._key = key
        self._cast = cast
        self._required = required

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr = f"_lazy_{name}"

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        sentinel = object()
        cached = getattr(objtype, self._attr, sentinel)
        if cached is not sentinel:
            return cached
        if self._required:
            value = _get_required_env(self._key, self._cast)
        else:
            value = _get_optional_env(self._key, self._cast)
        setattr(objtype, self._attr, value)
        return value


class Database:
    path = _LazyEnv("DATABASE_PATH", Path, required=True)


class Services:
    byparr = _LazyEnv("BYPARR_API_URL", str, required=True)
