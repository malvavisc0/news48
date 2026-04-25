"""File system tool for the agent.

Provides a unified read_file tool that replaces the previous
get_file_info, get_file_content, read_file_chunk, and list_directory tools.

Security: File reads are restricted to the project root, data directory,
and /tmp to prevent access to sensitive system files, credentials, etc.
"""

import logging
import stat
from datetime import datetime
from itertools import islice
from pathlib import Path

from news48.core import config

from ._helpers import _is_binary, _safe_json

logger = logging.getLogger(__name__)

_BINARY_SAMPLE_SIZE = 4096

# Allowed root directories for file reads.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DATA_ROOT = Path(config.DataDir.root).resolve()
_TMP_ROOT = Path("/tmp")

_ALLOWED_ROOTS = [_PROJECT_ROOT, _DATA_ROOT, _TMP_ROOT]

# Sensitive file patterns that are always blocked.
_SENSITIVE_PATTERNS = (
    ".env",
    ".env.",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credentials",
    "secret",
    "password",
    ".htpasswd",
    "shadow",
    "passwd",
)


def _validate_file_path(file_path: str) -> Path | str:
    """Validate that a file path is within allowed directories.

    Returns the resolved Path on success, or error message on failure.
    """
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError) as exc:
        return f"Invalid path: {exc}"

    # Check if the resolved path is within any allowed root
    allowed = False
    for root in _ALLOWED_ROOTS:
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue

    if not allowed:
        return (
            f"Access denied: '{file_path}' is outside allowed directories. "
            f"Allowed roots: {', '.join(str(r) for r in _ALLOWED_ROOTS)}"
        )

    # Check for sensitive file patterns in the filename
    name_lower = resolved.name.lower()
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in name_lower:
            return (
                f"Access denied: '{resolved.name}' matches " "a sensitive file pattern"
            )

    # Block access to /proc, /sys, /dev via symlink resolution
    resolved_str = str(resolved)
    if any(resolved_str.startswith(p) for p in ("/proc/", "/sys/", "/dev/", "/etc/")):
        return "Access denied: system directory access is not permitted"

    return resolved


def read_file(
    reason: str,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    metadata_only: bool = False,
) -> str:
    """Read file contents, metadata, or a chunk of a file.

    ## When to Use
    Use this tool when you need to read file contents, check file metadata,
    or read a portion of a large file. For directory listing, use
    `run_shell_command` with `ls` instead.

    ## Why to Use
    - Read configuration files, source code, documentation
    - Check file existence, size, and type before processing
    - Read large files in chunks to avoid memory issues
    - Inspect temp files created by the parse command

    ## Parameters
    - `reason` (str): Why you need to read this file
    - `file_path` (str): Path to the file (must be within allowed dirs)
    - `offset` (int | None): Line offset for partial reads
    - `limit` (int | None): Max lines for partial reads
    - `metadata_only` (bool): Return only file metadata (default: False)

    ## Behavior
    - metadata_only=True: Returns file size, type, timestamps
    - offset=None and limit=None: Read entire file
    - offset and limit provided: Read a chunk of lines

    ## Security
    File reads are restricted to the project root, data directory, and /tmp.
    Sensitive files (.env, credentials, keys) are blocked.

    ## Returns
    JSON with:
    - `result`: File content, metadata dict, or chunk depending on mode
    - `error`: Empty on success, or error description
    """
    # Validate path before any file operations
    validated = _validate_file_path(file_path)
    if isinstance(validated, str):
        logger.warning("Blocked file read: %s — %s", file_path, validated)
        return _safe_json({"result": "", "error": validated})

    file = validated

    try:
        if not file.exists():
            return _safe_json({"result": "", "error": "File not found"})

        if metadata_only:
            return _safe_json({"result": _get_file_metadata(file), "error": ""})

        # Check for binary file
        with open(file, "rb") as f:
            sample = f.read(_BINARY_SAMPLE_SIZE)

        if _is_binary(sample):
            return _safe_json({"result": "", "error": "Binary file not supported"})

        # Read file content
        if offset is not None and limit is not None:
            # Chunk read
            with file.open("r", encoding="utf-8") as f:
                rows = list(islice(f, offset, offset + limit))
            content = "".join(rows)
            # Count total lines
            with file.open("r", encoding="utf-8") as f:
                total_lines = sum(1 for _ in f)
            return _safe_json(
                {
                    "result": {
                        "content": content,
                        "offset": offset,
                        "lines": len(rows),
                        "total_lines": total_lines,
                    },
                    "error": "",
                }
            )
        else:
            # Full read
            with file.open("r", encoding="utf-8") as f:
                content = f.read()
            return _safe_json(
                {
                    "result": {
                        "content": content,
                        "line_count": content.count("\n") + 1,
                        "size_bytes": file.stat().st_size,
                    },
                    "error": "",
                }
            )

    except PermissionError:
        return _safe_json({"result": "", "error": "Permission denied"})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def _get_file_metadata(file: Path) -> dict:
    """Get filesystem metadata for a file.

    Args:
        file: Path to the file.

    Returns:
        A dict with file metadata.
    """
    info = file.lstat()
    modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    created = datetime.fromtimestamp(info.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "name": file.name,
        "size_bytes": info.st_size,
        "size_mb": info.st_size / (1024 * 1024),
        "modified": modified,
        "created": created,
        "is_directory": stat.S_ISDIR(info.st_mode),
        "is_file": stat.S_ISREG(info.st_mode),
        "is_symlink": stat.S_ISLNK(info.st_mode),
    }
