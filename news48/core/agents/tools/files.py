"""File system tool for the agent.

Provides a unified read_file tool that replaces the previous
get_file_info, get_file_content, read_file_chunk, and list_directory tools.
"""

import stat
from datetime import datetime
from itertools import islice
from pathlib import Path

from ._helpers import _is_binary, _safe_json

_BINARY_SAMPLE_SIZE = 4096


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
    - `file_path` (str): Path to the file
    - `offset` (int | None): Line offset for partial reads (default: None = start from beginning)
    - `limit` (int | None): Max lines for partial reads (default: None = read all)
    - `metadata_only` (bool): Return only file metadata (default: False)

    ## Behavior
    - metadata_only=True: Returns file size, type, timestamps
    - offset=None and limit=None: Read entire file
    - offset and limit provided: Read a chunk of lines

    ## Returns
    JSON with:
    - `result`: File content, metadata dict, or chunk depending on mode
    - `error`: Empty on success, or error description
    """
    try:
        file = Path(file_path)

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
