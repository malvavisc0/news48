"""MCP API key authentication backed by Redis.

Keys are stored in a Redis SET (mcp:keys) for O(1) lookup.
Metadata (label, created_at) stored in companion hashes.
"""

import secrets
from datetime import datetime

import redis

from news48.core.config import Redis as RedisConfig


def _get_redis() -> redis.Redis:
    """Get a Redis connection from the configured URL."""
    return redis.from_url(RedisConfig.url, decode_responses=True)


MCP_KEYS_SET = "mcp:keys"


def verify_key(api_key: str) -> bool:
    """Check if an API key is valid (exists in Redis SET)."""
    r = _get_redis()
    return r.sismember(MCP_KEYS_SET, api_key)


def create_key(label: str | None = None) -> str:
    """Generate a new API key and store it in Redis.

    Returns the generated key string.
    """
    key = f"n48-{secrets.token_urlsafe(32)}"
    r = _get_redis()
    r.sadd(MCP_KEYS_SET, key)
    metadata: dict[str, str] = {
        "created_at": datetime.now().isoformat(),
    }
    if label:
        metadata["label"] = label
    r.hset(f"mcp:key:{key}", mapping=metadata)
    return key


def revoke_key(api_key: str) -> bool:
    """Remove an API key from Redis. Returns True if it existed."""
    r = _get_redis()
    removed = r.srem(MCP_KEYS_SET, api_key)
    r.delete(f"mcp:key:{api_key}")
    return removed > 0


def list_keys() -> list[dict]:
    """List all active MCP API keys with metadata.

    Returns masked keys only — full keys are never exposed.
    """
    r = _get_redis()
    keys = r.smembers(MCP_KEYS_SET)
    result = []
    for key in sorted(keys):
        meta = r.hgetall(f"mcp:key:{key}") or {}
        masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else key
        result.append({"key": masked, **meta})
    return result
